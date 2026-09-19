"""Undated archive contracts on a disposable PostgreSQL database."""

import csv
import io
import struct
from datetime import timedelta, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core import binary_protocol as protocol
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.timezone import utc_now, TARGET_TZ
from app.db.database import get_db
from app.api.v1 import telemetry, reports, devices
from app.models.telemetry import Telemetry
from app.models.untimed_telemetry import UntimedTelemetry
from app.models.telemetry_quality import DeviceLossPeriod
from app.models.daily_summary import DailyBehaviorSummary
from app.models.alert import Alert
from app.services import binary_telemetry as decoder, ml_inference
from app.services.untimed_telemetry import classify_pending
from app.services.daily_summary import aggregate_daily_behavior
from test_binary_protocol import REFERENCE

URL = '/api/v1/telemetry/binary'


def packet(session=1, sequence=0, elapsed=15000, reason=1, gps=True):
    old = list(struct.unpack(protocol.PACKET_FORMAT, REFERENCE)[3:])
    if not gps:
        old[:3] = [protocol.GPS_ABSENT, protocol.GPS_ABSENT, 0]
    return struct.pack(protocol.UNTIMED_FORMAT, 3, 1, session, sequence, elapsed, reason, *old)


@pytest.fixture
def client(binary_case, monkeypatch):
    app = FastAPI()
    for router in (telemetry.router, reports.router, devices.router):
        app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: binary_case.db
    app.dependency_overrides[get_current_user] = lambda: binary_case.user
    monkeypatch.setattr(settings, 'BINARY_V3_ENABLED', True)
    monkeypatch.setattr(ml_inference, '_profiles', {})
    with TestClient(app) as value:
        value.headers.update({'Content-Type': 'application/octet-stream', 'X-Device-Secret': binary_case.secret})
        yield value


def test_wire_identity_and_v2_feature_equivalence():
    raw = packet(session=2**63 - 1, sequence=2**32 - 1, elapsed=2**32 - 1)
    assert len(raw) == 58
    decoded = decoder.decode_untimed_payload(raw)
    assert decoded['session_id'] == 2**63 - 1 and 'timestamp' not in decoded
    old = decoder.decode_binary_payload(REFERENCE)
    for name in (*protocol.FEATURE_NAMES, 'activity', 'activity_std', 'latitude', 'longitude'):
        assert old[name] == decoded[name]
    assert decoder.decode_untimed_payload(packet(gps=False))['latitude'] is None


@pytest.mark.parametrize('kwargs', [{'session': 0}, {'session': 2**63}, {'reason': 0}, {'reason': 5}, {'elapsed': 14999}])
def test_invalid_v3_identity_or_reason(kwargs):
    with pytest.raises(decoder.BinaryMeasurementError):
        decoder.decode_untimed_payload(packet(**kwargs))


@pytest.mark.parametrize('length,status', [(57, 400), (59, 413), (100000, 413)])
def test_v3_body_is_bounded(client, length, status):
    raw = (packet() + bytes(length))[:length]
    assert client.post(URL, content=raw).status_code == status


def test_archive_preserves_unknown_time_without_model(binary_case, client):
    case = binary_case
    result = client.post(URL, content=packet(session=2**62))
    assert result.status_code == 201, result.text
    assert result.json()['session_id'] == str(2**62)
    assert result.json()['measured_at'] is None and result.json()['time_reliable'] is False
    row = case.db.query(UntimedTelemetry).one()
    assert row.classification_status == 'pending_model' and row.predicted_behavior is None
    assert row.animal_id_at_reception == case.animal.id and row.farm_id_at_reception == case.farm.id
    assert row.attribution_status == 'unknown' and row.received_at <= utc_now()
    assert case.device.last_seen is None and case.device.battery_capacity is None
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 0
    assert client.get('/api/v1/telemetry/latest', params={'animal_id': case.animal.id}).json() == []
    assert client.get(f'/api/v1/telemetry/history/{case.animal.id}').json() == []


def test_predictions_are_diagnostic_and_never_feed_summaries(binary_case, client, monkeypatch):
    case = binary_case
    monkeypatch.setattr(ml_inference, 'profile_ready', lambda _: True)
    monkeypatch.setattr(ml_inference, 'get_profile_fingerprint', lambda _: 'a' * 64)
    case.prediction.return_value = ('Active', .8)
    assert client.post(URL, content=packet()).status_code == 201
    row = case.db.query(UntimedTelemetry).one()
    assert row.predicted_behavior == 'Active' and row.model_sha256 == 'a' * 64
    assert aggregate_daily_behavior(case.db, case.animal.id, utc_now().astimezone(TARGET_TZ).date()) is None
    assert case.db.query(DailyBehaviorSummary).count() == case.db.query(Alert).count() == 0
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 0


def test_raw_archive_survives_inference_failure(binary_case, client, monkeypatch):
    monkeypatch.setattr(ml_inference, 'profile_ready', lambda _: True)
    monkeypatch.setattr(ml_inference, 'get_profile_fingerprint', lambda _: 'a' * 64)
    binary_case.prediction.side_effect = RuntimeError('model failure')
    assert client.post(URL, content=packet()).status_code == 201
    assert binary_case.db.query(UntimedTelemetry).one().classification_status == 'inference_failed'


@pytest.mark.parametrize('device_status,loss', [('lost', False), ('maintenance', False), ('active', True)])
def test_lost_or_uncertain_device_is_not_classified(binary_case, client, monkeypatch, device_status, loss):
    case = binary_case
    case.device.status = device_status
    if loss:
        now = utc_now()
        case.db.add(DeviceLossPeriod(device_id=case.device.id, started_at=now - timedelta(days=2),
            ended_at=now - timedelta(days=1), declared_at=now, audit=[]))
    case.db.commit()
    assert client.post(URL, content=packet()).status_code == 201
    assert case.db.query(UntimedTelemetry).one().classification_status == 'excluded_context'
    case.prediction.assert_not_called()


def test_orphan_and_snapshot_after_transfer(binary_case, client):
    case = binary_case
    case.animal.assigned_device = None
    case.db.commit()
    assert client.post(URL, content=packet()).status_code == 201
    row = case.db.query(UntimedTelemetry).one()
    assert row.animal_id_at_reception is None
    stamp = row.received_at
    case.device.farm_id = case.other_farm.id
    case.db.commit()
    assert client.post(URL, content=packet()).status_code == 200
    case.db.refresh(row)
    assert row.farm_id_at_reception == case.farm.id and row.received_at == stamp


def test_dedupe_is_not_content_hash_or_reception_time(binary_case, client, monkeypatch):
    assert client.post(URL, content=packet()).status_code == 201
    assert client.post(URL, content=packet(sequence=1)).status_code == 201
    monkeypatch.setattr(settings, 'BINARY_V3_ENABLED', False)
    assert client.post(URL, content=packet()).status_code == 200
    assert client.post(URL, content=packet(reason=2)).status_code == 409
    assert client.post(URL, content=packet(sequence=2)).status_code == 503
    assert binary_case.db.query(UntimedTelemetry).count() == 2


def test_auth_precedes_decoding_and_revocation_precedes_replay(binary_case, client):
    with patch.object(decoder, 'decode_untimed_payload', side_effect=AssertionError('must not decode')):
        assert client.post(URL, content=packet(), headers={'X-Device-Secret': 'wrong'}).status_code == 401
    assert client.post(URL, content=packet()).status_code == 201
    binary_case.device.ingestion_revoked_at = utc_now()
    binary_case.db.commit()
    assert client.post(URL, content=packet()).status_code == 401


def test_no_acknowledgement_when_commit_fails(binary_case, client, monkeypatch):
    with monkeypatch.context() as change:
        change.setattr(binary_case.db, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('database failure')))
        with pytest.raises(RuntimeError, match='database failure'):
            client.post(URL, content=packet())
    binary_case.db.rollback()
    assert binary_case.db.query(UntimedTelemetry).count() == 0


def test_bounded_explicit_classification_not_on_replay(binary_case, client, monkeypatch):
    case = binary_case
    assert client.post(URL, content=packet()).status_code == 201
    monkeypatch.setattr(ml_inference, 'profile_ready', lambda _: True)
    monkeypatch.setattr(ml_inference, 'get_profile_fingerprint', lambda _: 'a' * 64)
    assert client.post(URL, content=packet()).status_code == 200
    case.prediction.assert_not_called()
    assert classify_pending(case.db, limit=1) == {'predicted': 1}
    case.prediction.assert_called_once()
    assert classify_pending(case.db) == {}


@pytest.mark.parametrize('path', ['preview', 'export'])
@pytest.mark.parametrize('role', ['farmer', 'vet'])
def test_archives_are_admin_only(binary_case, client, path, role):
    binary_case.user.role = role
    binary_case.db.commit()
    assert client.get(f'/api/v1/reports/{path}/untimed_telemetry').status_code == 403


def test_preview_and_csv_use_reception_dates_and_snapshot_filters(binary_case, client):
    assert client.post(URL, content=packet()).status_code == 201
    assert client.post(URL, content=packet(sequence=1)).status_code == 201
    case = binary_case
    rows = case.db.query(UntimedTelemetry).order_by(UntimedTelemetry.id).all()
    stamp = datetime(2026, 9, 13, 0, tzinfo=TARGET_TZ)
    for row in rows:
        row.received_at = stamp
    case.device.farm_id = case.other_farm.id
    case.db.commit()
    params = dict(date_from='2026-09-13', date_to='2026-09-13', farm_id=case.farm.id, device_id=case.device.id)
    preview = client.get('/api/v1/reports/preview/untimed_telemetry', params=params)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    csv_response = client.get('/api/v1/reports/export/untimed_telemetry', params=params)
    exported = list(csv.reader(io.StringIO(csv_response.text.lstrip('\ufeff'))))
    assert body['rows'] == exported[1:] and len(body['rows']) == 2
    assert 'measured_at_utc' in body['columns'] and 'raw_packet' not in body['columns']
    assert not any('secret' in col for col in body['columns'])
    params['date_to'] = params['date_from'] = '2026-09-12'
    assert client.get('/api/v1/reports/preview/untimed_telemetry', params=params).json()['rows'] == []
    assert client.get('/api/v1/reports/preview/untimed_telemetry').status_code == 400


def test_schema_and_constraints(binary_case, client):
    assert client.post(URL, content=packet()).status_code == 201
    db = binary_case.db
    columns = {col['name']: col for col in inspect(db.bind).get_columns('untimed_telemetry')}
    assert columns['measured_at']['nullable'] and str(columns['sequence']['type']) == 'BIGINT'
    for assignment in ("time_reliable=true", "sequence=-1", "measured_at=now()", "latitude=NULL", "classification_status='predicted'"):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text('UPDATE untimed_telemetry SET ' + assignment))


def test_real_staged_model_agrees_with_dated_features(binary_case, client, monkeypatch):
    from test_binary_telemetry_api import REAL_PREDICT
    artifact = ml_inference._load_artifact(Path(__file__).resolve().parents[1] / 'ml/models/behavior_classifier_v3_staged.pkl', (10, 150))
    assert artifact is not None
    monkeypatch.setattr(ml_inference, '_profiles', {(10, 150): artifact})
    monkeypatch.setattr(ml_inference, 'predict_with_confidence', REAL_PREDICT)
    expected = REAL_PREDICT(decoder.decode_untimed_payload(packet()))
    assert client.post(URL, content=packet()).status_code == 201
    row = binary_case.db.query(UntimedTelemetry).one()
    assert (row.predicted_behavior, row.behavior_confidence) == expected
    assert row.model_sha256 == artifact['artifact_sha256']


@pytest.fixture
def concurrent_api(binary_engine, monkeypatch):
    from sqlalchemy.orm import Session
    from app.models.device import Device
    from app.core.security import generate_device_secret, hash_device_secret

    secret = generate_device_secret()
    device_id = 'UNTIMED-CONCURRENT'
    with Session(binary_engine) as db:
        db.add(Device(id=device_id, transport_id=40001, device_secret=hash_device_secret(secret), status='active'))
        db.commit()
    monkeypatch.setattr(settings, 'BINARY_V3_ENABLED', True)
    monkeypatch.setattr(ml_inference, '_profiles', {})
    app = FastAPI()
    app.include_router(telemetry.router, prefix='/api/v1')
    def session():
        with Session(binary_engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    raw = bytearray(packet())
    struct.pack_into('<H', raw, 1, 40001)
    def send(payload=bytes(raw)):
        with TestClient(app) as client:
            return client.post(URL, content=payload, headers={
                'Content-Type': 'application/octet-stream', 'X-Device-Secret': secret})
    try:
        yield send, bytes(raw), device_id
    finally:
        with Session(binary_engine) as db:
            db.query(UntimedTelemetry).filter_by(device_id=device_id).delete()
            db.query(Device).filter_by(id=device_id).delete()
            db.commit()


@pytest.mark.parametrize('conflict', [False, True])
def test_concurrent_archive_identity(binary_engine, concurrent_api, conflict):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    send, raw, device_id = concurrent_api
    barrier = Barrier(2)
    def request(payload):
        barrier.wait(timeout=10)
        return send(payload).status_code
    second = bytearray(raw)
    if conflict:
        second[19] = 2
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(request, value) for value in (raw, bytes(second))]
        assert sorted(f.result(timeout=20) for f in futures) == ([201, 409] if conflict else [200, 201])
    with Session(binary_engine) as db:
        assert db.query(UntimedTelemetry).filter_by(device_id=device_id).count() == 1


@pytest.mark.parametrize('replay', [False, True])
def test_committed_revocation_wins_over_waiting_archive(binary_engine, concurrent_api, monkeypatch, replay):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy.orm import Session
    from app.models.device import Device
    send, raw, device_id = concurrent_api
    if replay:
        assert send().status_code == 201
    entered = Event()
    authenticate = telemetry._authenticated_device
    def waiting(*args, **kwargs):
        entered.set()
        return authenticate(*args, **kwargs)
    monkeypatch.setattr(telemetry, '_authenticated_device', waiting)
    with ThreadPoolExecutor(max_workers=1) as workers:
        with Session(binary_engine) as db:
            device = db.query(Device).filter_by(id=device_id).with_for_update().one()
            future = workers.submit(send)
            assert entered.wait(timeout=10)
            device.ingestion_revoked_at = utc_now()
            db.commit()
        assert future.result(timeout=20).status_code == 401
