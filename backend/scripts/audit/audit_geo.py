"""Read-only audit (session 2): ingestion, auth, revocation, v3, geofencing, locations.

Creates its own disposable PostgreSQL database livestock_audit_<uuid> on the server
named in backend/.env, migrates it, runs scenarios through the real routers, drops it.
Run from backend/ with the backend venv. Writes nothing to the repo.
"""
import importlib.util
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path.cwd()
REPO = BACKEND.parent
UTC = timezone.utc
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:160]))


def case(fn):
    only = os.environ.get('AUDIT_ONLY')
    if only and fn.__name__ != only:
        return fn
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        check(f"{fn.__name__} crashed", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    return fn


def run(db_name):
    sys.path.insert(0, str(BACKEND))
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import func

    from app.db.database import SessionLocal, engine, get_db
    assert engine.url.database == db_name, engine.url.database
    from app.api.v1 import locations as loc_api, telemetry as tel_api
    from app.core.config import settings
    from app.core.dependencies import get_current_user
    from app.core.security import generate_device_secret, hash_device_secret
    from app.models.alert import Alert
    from app.models.animal import Animal
    from app.models.device import Device
    from app.models.farm import Farm
    from app.models.geofence import Geofence
    from app.models.membership import FarmMembership
    from app.models.notification import NotificationDelivery
    from app.models.telemetry import Telemetry
    from app.models.telemetry_quality import DeviceLossPeriod
    from app.models.untimed_telemetry import UntimedTelemetry
    from app.models.user import User
    from app.services import geofence_engine, ml_inference, notification_service
    from app.services.provenance_service import record_tracking_period

    spec = importlib.util.spec_from_file_location("fw", REPO / "m5stack" / "b4_protocol.py")
    fw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fw)

    # ML is irrelevant to this area: keep the 15 s slot "ready" with a fixed answer.
    ml_inference._profiles = {(10, 150): {"artifact_sha256": "a" * 64}}
    ml_inference.predict_with_confidence = lambda features: ("Resting", 0.9)

    state = {"uid": None}
    app = FastAPI()
    app.include_router(tel_api.router, prefix="/api/v1")
    app.include_router(loc_api.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["uid"])
    client = TestClient(app, raise_server_exceptions=bool(os.environ.get('AUDIT_RAISE')))

    REAL_NOW = datetime.now(UTC).replace(microsecond=0)
    NOW = REAL_NOW - timedelta(hours=1)          # evaluation clock for geofencing
    geofence_engine.utc_now = lambda: NOW
    counter = {"tid": 100}

    # Geometry (lon, lat). Pasture square; danger square outside the pasture.
    PASTURE = "SRID=4326;POLYGON((135.000 34.000,135.010 34.000,135.010 34.010,135.000 34.010,135.000 34.000))"
    DANGER = "SRID=4326;POLYGON((135.020 34.000,135.025 34.000,135.025 34.005,135.020 34.005,135.020 34.000))"
    IN, OUT, DZ, BORDER = (34.005, 135.005), (34.005, 135.015), (34.002, 135.022), (34.005, 135.010)

    def new_farm(label):
        with SessionLocal() as s:
            user = User(email=f"{label}-{uuid.uuid4().hex[:8]}@audit.test", password_hash="x", name=label, role="farmer")
            s.add(user); s.flush()
            farm = Farm(owner_id=user.id, name=f"Audit {label}")
            s.add(farm); s.flush()
            s.add(FarmMembership(user_id=user.id, farm_id=farm.id, role="owner", status="active"))
            s.add_all([Geofence(farm_id=farm.id, name="pasture", type="pasture", polygon=PASTURE, active=True),
                       Geofence(farm_id=farm.id, name="danger", type="danger", polygon=DANGER, active=True)])
            s.commit()
            return farm.id, user.id

    FARM_A, USER_A = new_farm("A")
    FARM_B, USER_B = new_farm("B")

    def new_collar(farm_id=FARM_A, status="active", with_animal=True, provisioned=True, period_from=None):
        counter["tid"] += 1
        tid = counter["tid"]
        secret = generate_device_secret()
        with SessionLocal() as s:
            dev = Device(id=f"AUD-{tid}", transport_id=tid if provisioned else None,
                         device_secret=hash_device_secret(secret) if provisioned else None,
                         farm_id=farm_id, status=status)
            s.add(dev); s.flush()
            animal_id = None
            if with_animal:
                animal = Animal(farm_id=farm_id, name=f"Cow {tid}", status="active", assigned_device=dev.id)
                s.add(animal); s.flush()
                record_tracking_period(s, animal.id, farm_id, dev.id, "registration",
                                       valid_from=period_from or REAL_NOW - timedelta(days=10))
                animal_id = animal.id
            s.commit()
        return {"tid": tid, "secret": secret, "device": f"AUD-{tid}", "animal": animal_id}

    def packet(c, when, pos=None, sats=8, battery=70, accel=(0.0, 0.0, 1.0)):
        w = fw.Window()
        for _ in range(150):
            w.add(accel)
        gps = None if pos is None else (pos[0], pos[1], sats)
        return w.encode(c["tid"], int(when.timestamp()), gps, battery)

    def send(c, raw, secret=None, ctype="application/octet-stream"):
        headers = {"Content-Type": ctype}
        if secret is not False:
            headers["X-Device-Secret"] = secret or c["secret"]
        return client.post("/api/v1/telemetry/binary", content=raw, headers=headers)

    def alerts(animal_id):
        with SessionLocal() as s:
            rows = s.query(Alert).filter(Alert.animal_id == animal_id).order_by(Alert.id).all()
            return [(a.id, a.severity, (a.alert_metadata or {}).get("sub_type"), a.resolved_at,
                     (a.alert_metadata or {}).get("last_detected_at")) for a in rows]

    def deliveries(animal_id):
        with SessionLocal() as s:
            return s.query(func.count(NotificationDelivery.id)).join(Alert, Alert.id == NotificationDelivery.alert_id)\
                .filter(Alert.animal_id == animal_id).scalar()

    def telemetry_count(animal_id=None, device_id=None):
        with SessionLocal() as s:
            q = s.query(func.count()).select_from(Telemetry)
            if animal_id is not None:
                q = q.filter(Telemetry.animal_id == animal_id)
            if device_id is not None:
                q = q.filter(Telemetry.device_id == device_id)
            return q.scalar()

    def set_device(device_id, **values):
        with SessionLocal() as s:
            d = s.get(Device, device_id)
            for k, v in values.items():
                setattr(d, k, v)
            s.commit()

    # ── Ingestion / auth ────────────────────────────────────────────────────────
    @case
    def auth_and_envelope():
        c = new_collar()
        raw = packet(c, NOW - timedelta(seconds=10), IN)
        unknown = bytearray(raw); unknown[1:3] = (65000).to_bytes(2, "little")
        r = send(c, bytes(unknown)); check("A1 unknown transport_id -> 401", r.status_code == 401, r.status_code)
        r = send(c, raw, secret="0" * 64); check("A2 wrong secret -> 401", r.status_code == 401, r.status_code)
        r = send(c, raw, secret=False); check("A3 missing X-Device-Secret -> 401", r.status_code == 401, r.status_code)
        r = send(c, raw, secret="NOT-HEX"); check("A4 malformed secret -> 401", r.status_code == 401, r.status_code)
        check("A1-4 nothing persisted before auth", telemetry_count(c["animal"]) == 0)
        r = send(c, raw + b"\x00"); check("A5 46-byte v2 body -> 413", r.status_code == 413, r.status_code)
        r = send(c, raw, ctype="application/json"); check("A6 wrong content-type -> 415", r.status_code == 415, r.status_code)
        r = send(c, raw); check("A7 valid packet -> 201", r.status_code == 201, r.status_code)
        r = send(c, raw); check("A8 identical replay -> 200", r.status_code == 200, r.status_code)
        r = send(c, packet(c, NOW - timedelta(seconds=10), IN, battery=71))
        check("A9 same timestamp, different content -> 409", r.status_code == 409, r.status_code)
        check("A7-9 exactly one telemetry row", telemetry_count(c["animal"]) == 1, telemetry_count(c["animal"]))

    @case
    def device_without_animal():
        c = new_collar(with_animal=False)
        r = send(c, packet(c, NOW, IN))
        check("D1 binary, provisioned device without animal: rejected, no row",
              r.status_code >= 400 and telemetry_count(device_id=c["device"]) == 0, f"{r.status_code} {r.json().get('detail')}")
        body = {"device_id": f"JSON-UNKNOWN-{uuid.uuid4().hex[:6]}", "latitude": IN[0], "longitude": IN[1],
                "activity": 0.1, "battery": 50, "sample_rate": 10, "window_samples": 150}
        r = client.post("/api/v1/telemetry/", json=body)
        with SessionLocal() as s:
            created = s.get(Device, body["device_id"])
        check("D2 JSON unknown device without animal -> 404 (no telemetry)", r.status_code == 404, r.status_code)
        check("D3 JSON unknown device auto-registered as orphan Device row (unauthenticated)",
              created is not None, f"created={created is not None} farm={getattr(created, 'farm_id', None)}")
        # Animal assigned to a device id that has no Device row (legacy data shape).
        with SessionLocal() as s:
            dev_id = f"LEGACY-{uuid.uuid4().hex[:6]}"
            animal = Animal(farm_id=FARM_A, name="Legacy cow", status="active", assigned_device=dev_id)
            s.add(animal); s.commit(); legacy_animal = animal.id
        r = client.post("/api/v1/telemetry/", json={**body, "device_id": dev_id})
        check("D4 JSON for animal whose device row is missing: accepted with no secret",
              r.status_code == 201, r.status_code)
        c2 = new_collar()
        r = client.post("/api/v1/telemetry/", json={**body, "device_id": c2["device"]})
        check("D5 JSON for provisioned device without secret -> 401", r.status_code == 401, r.status_code)
        stamp = (NOW - timedelta(seconds=5)).isoformat()
        r1 = client.post("/api/v1/telemetry/", json={**body, "device_id": c2["device"], "timestamp": stamp},
                         headers={"X-Device-Secret": c2["secret"]})
        r2 = client.post("/api/v1/telemetry/", json={**body, "device_id": c2["device"], "timestamp": stamp},
                         headers={"X-Device-Secret": c2["secret"]})
        check("D6 JSON with secret -> 201", r1.status_code == 201, r1.status_code)
        check("D7 JSON identical replay status (binary gives 200)", r2.status_code == 200, r2.status_code)

    @case
    def revocation():
        for label, values in (("revoked", {"ingestion_revoked_at": REAL_NOW}), ("retired", {"status": "retired"})):
            c = new_collar()
            accepted = packet(c, NOW - timedelta(seconds=30), IN)
            check(f"R0 {label}: baseline 201", send(c, accepted).status_code == 201)
            set_device(c["device"], **values)
            r = send(c, packet(c, NOW - timedelta(seconds=10), IN)); check(f"R1 {label}: new binary -> 401", r.status_code == 401, r.status_code)
            r = send(c, accepted); check(f"R2 {label}: replay of accepted packet -> 401", r.status_code == 401, r.status_code)
            r = client.post("/api/v1/telemetry/", headers={"X-Device-Secret": c["secret"]},
                            json={"device_id": c["device"], "latitude": IN[0], "longitude": IN[1], "activity": 0.1,
                                  "battery": 50, "sample_rate": 10, "window_samples": 150})
            check(f"R3 {label}: JSON -> 401", r.status_code == 401, r.status_code)
            w = fw.Window()
            for _ in range(150):
                w.add((0.0, 0.0, 1.0))
            r = send(c, w.encode_untimed(c["tid"], 5, 1, 20000, 1, None, 50))
            check(f"R4 {label}: v3 -> 401", r.status_code == 401, r.status_code)

    @case
    def untimed_v3():
        c = new_collar()
        w = fw.Window()
        for _ in range(150):
            w.add((0.0, 0.0, 1.0))
        raw = w.encode_untimed(c["tid"], 77, 1, 20000, 1, IN + (7,), 60)
        before = telemetry_count()
        settings.BINARY_V3_ENABLED = False
        r = send(c, raw); check("V0 v3 new window with BINARY_V3_ENABLED=False -> 503", r.status_code == 503, r.status_code)
        settings.BINARY_V3_ENABLED = True
        r = send(c, raw); check("V1 v3 new window -> 201", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        r = send(c, raw); check("V2 v3 identical replay -> 200", r.status_code == 200, r.status_code)
        conflict = w.encode_untimed(c["tid"], 77, 1, 20000, 1, IN + (7,), 61)
        r = send(c, conflict); check("V3 v3 same session/sequence, different bytes -> 409", r.status_code == 409, r.status_code)
        settings.BINARY_V3_ENABLED = False
        r = send(c, raw); check("V4 v3 replay with flag off -> 200 (replay checked before the gate)", r.status_code == 200, r.status_code)
        settings.BINARY_V3_ENABLED = True
        with SessionLocal() as s:
            row = s.query(UntimedTelemetry).filter_by(device_id=c["device"]).one()
            check("V5 measured_at NULL, time_reliable False", row.measured_at is None and row.time_reliable is False)
            check("V6 lat/lon stored but no geography; attribution 'unknown'", row.attribution_status == "unknown",
                  row.attribution_status)
        check("V7 no Telemetry row created by v3", telemetry_count() == before, f"{before} -> {telemetry_count()}")
        check("V8 no geofence alert from v3 position", alerts(c["animal"]) == [])
        c2 = new_collar(with_animal=False)
        r = send(c2, w.encode_untimed(c2["tid"], 9, 1, 20000, 1, None, 60))
        check("V9 v3 from device without animal -> 201 (archived, animal_id_at_reception NULL)", r.status_code == 201, r.status_code)

    # ── Geofencing ──────────────────────────────────────────────────────────────
    @case
    def fix_age_boundary():
        for age, expect in ((299, True), (300, True), (301, False), (-1, False)):
            c = new_collar()
            r = send(c, packet(c, NOW - timedelta(seconds=age), DZ))
            got = any(a[1] == "critical" for a in alerts(c["animal"]))
            check(f"G1 danger fix aged {age:>4} s -> alert={expect}", r.status_code == 201 and got == expect, f"{r.status_code} alert={got}")

    @case
    def two_fix_boundary():
        for gap, expect in ((119, True), (120, True), (121, False)):
            c = new_collar()
            r1 = send(c, packet(c, NOW - timedelta(seconds=gap), OUT))
            first = alerts(c["animal"])
            r2 = send(c, packet(c, NOW, OUT))
            got = any(a[2] == "pasture_exit" for a in alerts(c["animal"]))
            check(f"G2 two outside fixes {gap} s apart -> exit alert={expect}",
                  r1.status_code == r2.status_code == 201 and first == [] and got == expect, f"alert={got} first={first}")

    @case
    def same_collar_and_border():
        c = new_collar()
        with SessionLocal() as s:
            other = Device(id=f"OTHER-{c['tid']}", farm_id=FARM_A, status="active")
            s.add(other); s.flush()
            when = NOW - timedelta(seconds=60)
            s.add(Telemetry(time=when, animal_id=c["animal"], device_id=other.id, received_at=REAL_NOW,
                            time_source="device_utc", protocol_version=2, behavior_eligible=True,
                            location=f"POINT({OUT[1]} {OUT[0]})", latitude=OUT[0], longitude=OUT[1], satellites=8,
                            activity=0.1, activity_state="lying", sample_rate=10, window_samples=150, battery_level=50))
            s.commit()
        send(c, packet(c, NOW, OUT))
        check("G3 prior outside fix from a different collar does not confirm exit", alerts(c["animal"]) == [], alerts(c["animal"]))
        c = new_collar()
        send(c, packet(c, NOW - timedelta(seconds=60), BORDER)); send(c, packet(c, NOW, BORDER))
        check("G4 two fixes exactly on pasture border -> no exit alert (ST_Covers)", alerts(c["animal"]) == [], alerts(c["animal"]))
        c = new_collar()
        send(c, packet(c, NOW - timedelta(seconds=60), OUT, sats=3)); send(c, packet(c, NOW, OUT))
        check("G5 first fix with 3 satellites does not count toward confirmation", alerts(c["animal"]) == [], alerts(c["animal"]))
        c = new_collar()
        send(c, packet(c, NOW, DZ, sats=3))
        check("G6 danger fix with 3 satellites ignored", alerts(c["animal"]) == [])

    @case
    def danger_and_resolution():
        c = new_collar()
        send(c, packet(c, NOW - timedelta(seconds=100), DZ))
        a = alerts(c["animal"])
        check("G7 single danger fix -> critical alert", len(a) == 1 and a[0][1] == "critical", a)
        check("G8 danger alert -> notification intent (delivery row)", deliveries(c["animal"]) >= 1, deliveries(c["animal"]))
        d0 = deliveries(c["animal"])
        send(c, packet(c, NOW - timedelta(seconds=80), DZ))
        check("G9 repeated danger fix -> no duplicate alert or delivery", 
              len(alerts(c["animal"])) == 1 and deliveries(c["animal"]) == d0, f"alerts={alerts(c['animal'])} deliveries={d0}->{deliveries(c['animal'])}")
        send(c, packet(c, NOW - timedelta(seconds=60), IN))
        check("G10 back in pasture: danger alert NOT auto-resolved", alerts(c["animal"])[0][3] is None, alerts(c["animal"]))
        c = new_collar()
        send(c, packet(c, NOW - timedelta(seconds=90), OUT)); send(c, packet(c, NOW - timedelta(seconds=30), OUT))
        a = alerts(c["animal"])
        check("G11 confirmed exit -> warning pasture_exit", len(a) == 1 and a[0][2] == "pasture_exit" and a[0][3] is None, a)
        send(c, packet(c, NOW, IN))
        check("G12 return to pasture -> exit alert auto-resolved", alerts(c["animal"])[0][3] is not None, alerts(c["animal"]))

    @case
    def replay_is_neutral():
        c = new_collar()
        out1 = packet(c, NOW - timedelta(seconds=200), OUT)
        send(c, out1)
        r = send(c, out1)
        check("G13 replay of first outside fix (200) does not create an alert", r.status_code == 200 and alerts(c["animal"]) == [])
        out2 = packet(c, NOW - timedelta(seconds=150), OUT)
        send(c, out2)
        snap = alerts(c["animal"]); d = deliveries(c["animal"])
        r = send(c, out2)
        check("G14 replay of confirming fix (200) leaves alert/delivery untouched",
              r.status_code == 200 and alerts(c["animal"]) == snap and deliveries(c["animal"]) == d, f"{snap} vs {alerts(c['animal'])}")
        in3 = packet(c, NOW - timedelta(seconds=120), IN)
        send(c, in3)
        resolved = alerts(c["animal"])
        send(c, packet(c, NOW - timedelta(seconds=60), OUT)); send(c, packet(c, NOW - timedelta(seconds=10), OUT))
        before = alerts(c["animal"])
        r = send(c, in3)
        check("G15 replay of an inside fix (200) does not resolve the reopened alert",
              r.status_code == 200 and alerts(c["animal"]) == before and before[-1][3] is None and resolved[0][3] is not None,
              f"before={before}")
        r = send(c, out2)
        check("G16 replay after resolution does not reopen/duplicate", r.status_code == 200 and alerts(c["animal"]) == before)

    @case
    def out_of_order_and_status():
        c = new_collar()
        send(c, packet(c, NOW, IN))
        r = send(c, packet(c, NOW - timedelta(seconds=60), DZ))
        check("G17 older fix arriving after a newer one -> stored (201), no alert",
              r.status_code == 201 and alerts(c["animal"]) == [], f"{r.status_code} {alerts(c['animal'])}")
        for status in ("lost", "maintenance"):
            c = new_collar(status=status)
            r = send(c, packet(c, NOW, DZ))
            with SessionLocal() as s:
                row = s.query(Telemetry).filter_by(animal_id=c["animal"]).first()
            check(f"G18 {status} collar: telemetry stored, no geofence alert",
                  r.status_code == 201 and alerts(c["animal"]) == [], f"{r.status_code} eligible={getattr(row, 'behavior_eligible', None)}")

    @case
    def failure_isolation():
        original = geofence_engine.get_covering_geofence_ids
        c = new_collar()
        def py_fail(*a, **k):
            raise RuntimeError("PostGIS geofence evaluation unavailable")
        geofence_engine.get_covering_geofence_ids = py_fail
        r = send(c, packet(c, NOW, DZ))
        check("G19 spatial error (Python) -> 201, telemetry kept, no alert",
              r.status_code == 201 and telemetry_count(c["animal"]) == 1 and alerts(c["animal"]) == [], r.status_code)
        c = new_collar()
        def sql_fail(db, *a, **k):
            db.execute(text("SELECT ST_Covers('NOT A GEOMETRY'::geometry, NULL::geometry)"))
        geofence_engine.get_covering_geofence_ids = sql_fail
        r = send(c, packet(c, NOW, DZ))
        check("G20 spatial error (SQL, aborts txn) -> savepoint keeps telemetry (201), no alert",
              r.status_code == 201 and telemetry_count(c["animal"]) == 1 and alerts(c["animal"]) == [], r.status_code)
        geofence_engine.get_covering_geofence_ids = original

        orig_enqueue = notification_service.enqueue_alert_notification
        c = new_collar()
        def enqueue_py(db, alert):
            raise RuntimeError("push outbox down")
        notification_service.enqueue_alert_notification = enqueue_py
        r = send(c, packet(c, NOW, DZ))
        check("N1 enqueue fails (Python): HTTP status / alert committed / deliveries",
              r.status_code == 201, f"http={r.status_code} alerts={len(alerts(c['animal']))} deliveries={deliveries(c['animal'])}")
        check("N1b alert exists with zero notification intents (no retry path)",
              len(alerts(c["animal"])) == 1 and deliveries(c["animal"]) == 0)
        c = new_collar()
        def enqueue_sql(db, alert):
            db.execute(text("SELECT 1/0"))
        notification_service.enqueue_alert_notification = enqueue_sql
        r = send(c, packet(c, NOW, DZ))
        rows, al = telemetry_count(c["animal"]), len(alerts(c["animal"]))
        check("N2 enqueue fails (SQL error): response code", r.status_code == 201,
              f"http={r.status_code} telemetry={rows} alerts={al} deliveries={deliveries(c['animal'])}")
        notification_service.enqueue_alert_notification = orig_enqueue
        r = send(c, packet(c, NOW, DZ))
        check("N3 device retry after N2 (replay) -> 200, still no notification intent",
              r.status_code == 200 and deliveries(c["animal"]) == 0, f"http={r.status_code} deliveries={deliveries(c['animal'])}")

    # ── Location / history ──────────────────────────────────────────────────────
    def insert_points(animal_id, device_id, points):
        with SessionLocal() as s:
            for when, pos, sats in points:
                s.add(Telemetry(time=when, animal_id=animal_id, device_id=device_id, received_at=REAL_NOW,
                                time_source="device_utc", protocol_version=2, behavior_eligible=True,
                                location=f"POINT({pos[1]} {pos[0]})", latitude=pos[0], longitude=pos[1], satellites=sats,
                                activity=0.1, activity_state="lying", sample_rate=10, window_samples=150, battery_level=50))
            s.commit()

    def history(farm_id, animal_id, uid, **params):
        state["uid"] = uid
        return client.get(f"/api/v1/farms/{farm_id}/locations/{animal_id}/history", params=params)

    @case
    def segmentation_and_quality():
        c = new_collar()
        t0 = REAL_NOW - timedelta(hours=3)
        insert_points(c["animal"], c["device"], [(t0, IN, 8), (t0 + timedelta(seconds=1800), IN, 8),
                                                 (t0 + timedelta(seconds=3601), IN, 3)])
        r = history(FARM_A, c["animal"], USER_A, hours=24).json()
        segs = [(len(s["points"]), s["quality"]) for s in r["segments"]]
        inner = [g["reason"] for g in r["gaps"]]
        check("L1 Δ = 1800 s stays in one segment; Δ = 1801 s splits", segs == [(2, "reliable"), (1, "degraded")], f"{segs} gaps={inner}")
        check("L2 gap reason 'no_data' (no loss period)", inner == ["no_data"], inner)
        r = history(FARM_A, c["animal"], USER_A, start=(REAL_NOW - timedelta(days=10)).isoformat()).json()
        span = (datetime.fromisoformat(r["period_end"].replace("Z", "+00:00")) -
                datetime.fromisoformat(r["period_start"].replace("Z", "+00:00"))).total_seconds() / 3600
        check("L3 history window clamped to 168 h", abs(span - 168) < 0.01, f"{span:.2f} h")
        insert_points(c["animal"], c["device"], [(t0 + timedelta(seconds=3700), IN, None)])
        r = history(FARM_A, c["animal"], USER_A, hours=24).json()
        check("L4 point with satellites=NULL counted as reliable", r["segments"][-1]["quality"] == "degraded"
              and r["segments"][-1]["points"][-1]["is_reliable"] is True, r["segments"][-1]["points"][-1])
        simplified = all(len(s["points"]) == n for s, n in zip(r["segments"], (2, 2)))
        check("L5 no path simplification (all points returned)", simplified, [len(s["points"]) for s in r["segments"]])

    @case
    def lost_equipment():
        c = new_collar()
        t0 = REAL_NOW - timedelta(hours=2)
        insert_points(c["animal"], c["device"], [(t0, IN, 8), (t0 + timedelta(minutes=10), IN, 8)])
        set_device(c["device"], status="lost")
        state["uid"] = USER_A
        cur = client.get(f"/api/v1/farms/{FARM_A}/locations/{c['animal']}").json()
        r = history(FARM_A, c["animal"], USER_A, hours=24).json()
        check("L6 lost collar: current location flagged position_is_animal=False",
              cur.get("position_is_animal") is False and cur.get("device_status") == "lost", cur)
        check("L7 lost collar: history quality 'uncertain' for ALL segments (incl. pre-loss)",
              [s["quality"] for s in r["segments"]] == ["uncertain"] and r["position_is_animal"] is False,
              [s["quality"] for s in r["segments"]])
        latest = client.get("/api/v1/telemetry/latest", params={"farm_id": FARM_A, "animal_id": c["animal"]}).json()
        check("L8 /telemetry/latest: lost collar position_is_animal=False", latest and latest[0]["position_is_animal"] is False, latest)

        c = new_collar()
        t0 = REAL_NOW - timedelta(hours=2)
        insert_points(c["animal"], c["device"], [(t0, IN, 8), (t0 + timedelta(minutes=10), OUT, 8),
                                                 (t0 + timedelta(minutes=20), IN, 8)])
        with SessionLocal() as s:
            s.add(DeviceLossPeriod(device_id=c["device"], started_at=t0 + timedelta(minutes=5),
                                   ended_at=t0 + timedelta(minutes=15), declared_at=REAL_NOW, audit=[]))
            s.commit()
        r = history(FARM_A, c["animal"], USER_A, hours=24).json()
        pts = sum(len(s["points"]) for s in r["segments"])
        check("L9 closed loss period (collar remounted): loss-window point still drawn as animal track",
              pts == 3 and {s["quality"] for s in r["segments"]} == {"reliable"},
              f"points={pts} qualities={[s['quality'] for s in r['segments']]}")

    @case
    def provenance_transfer():
        c = new_collar()
        t0 = REAL_NOW - timedelta(hours=2)
        insert_points(c["animal"], c["device"], [(t0, IN, 8), (t0 + timedelta(minutes=5), IN, 8)])
        with SessionLocal() as s:  # same writes as PUT /animals/{id} with a farm change
            a = s.get(Animal, c["animal"]); a.farm_id = FARM_B
            record_tracking_period(s, a.id, FARM_B, a.assigned_device, "farm_transfer")
            s.commit()
        state["uid"] = USER_B
        cur = client.get(f"/api/v1/farms/{FARM_B}/locations/{c['animal']}")
        check("P1 new farm: current location -> 404 (no proven position)", cur.status_code == 404, cur.status_code)
        r = history(FARM_B, c["animal"], USER_B, hours=24).json()
        check("P2 new farm: /locations history has 0 points from old farm", r["total_points"] == 0, r["total_points"])
        latest_b = client.get(f"/api/v1/farms/{FARM_B}/locations/latest").json()
        check("P3 new farm: /locations/latest excludes the transferred animal",
              all(p["animal_id"] != c["animal"] for p in latest_b))
        th = client.get(f"/api/v1/telemetry/history/{c['animal']}", params={"hours": 24})
        n = len(th.json()) if th.status_code == 200 else None
        check("P4 new farm: legacy /telemetry/history exposes old-farm rows", n == 0, f"http={th.status_code} rows={n}")
        tl = client.get("/api/v1/telemetry/latest", params={"farm_id": FARM_B, "animal_id": c["animal"]})
        lat = tl.json()[0]["latitude"] if tl.status_code == 200 and tl.json() else None
        check("P5 new farm: legacy /telemetry/latest exposes old-farm position", lat is None, f"http={tl.status_code} latitude={lat}")
        state["uid"] = USER_A
        r = client.get(f"/api/v1/farms/{FARM_A}/locations/{c['animal']}")
        check("P6 old farm loses access to the animal (403)", r.status_code == 403, r.status_code)

        # Device transfer: collar moves from animal P (farm A) to animal Q (farm B).
        p = new_collar()
        send(p, packet(p, NOW - timedelta(seconds=30), IN))
        with SessionLocal() as s:
            pa = s.get(Animal, p["animal"]); pa.assigned_device = None
            record_tracking_period(s, pa.id, FARM_A, None, "device_reassignment")
            s.flush()
            s.get(Device, p["device"]).farm_id = FARM_B
            q = Animal(farm_id=FARM_B, name="Cow Q", status="active", assigned_device=p["device"])
            s.add(q); s.flush()
            record_tracking_period(s, q.id, FARM_B, p["device"], "registration")
            s.commit(); q_id = q.id
        r = send(p, packet(p, NOW, IN))
        state["uid"] = USER_B
        th = client.get(f"/api/v1/telemetry/history/{q_id}", params={"hours": 24}).json()
        hist = history(FARM_B, q_id, USER_B, hours=24).json()
        check("P7 device transfer: new packet attributed to new animal; old readings stay with old animal",
              r.status_code == 201 and len(th) == 1 and hist["total_points"] <= 1, f"http={r.status_code} rows={len(th)} pts={hist['total_points']}")

    @case
    def gist_index():
        with SessionLocal() as s:
            idx = [r[0] for r in s.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename='geofences' AND indexdef ILIKE '%gist%'"))]
        check("G21 GiST index on geofences.polygon", bool(idx), idx)

    width = max(len(n) for n, _, _ in RESULTS)
    fails = 0
    for name, ok, detail in RESULTS:
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    print(f"\n{len(RESULTS) - fails}/{len(RESULTS)} expectations met")
    engine.dispose()


def main():
    base = make_url(dotenv_values(BACKEND / ".env")["DATABASE_URL"])
    name = "livestock_audit_" + uuid.uuid4().hex
    maintenance = create_engine(base.set(database="postgres"), hide_parameters=True)
    isolated_url = base.set(database=name)
    os.environ["DATABASE_URL"] = isolated_url.render_as_string(hide_password=False)
    os.environ["SCHEDULER_ENABLED"] = "false"
    created = False
    try:
        with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        print("disposable database:", name)
        iso = create_engine(isolated_url, hide_parameters=True)
        with iso.begin() as c:
            c.exec_driver_sql((BACKEND / "app/db/init.sql").read_text(encoding="utf-8"))
        iso.dispose()
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(cfg, "head")
        run(name)
    finally:
        if created:
            with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
                c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            print("dropped:", name)
        maintenance.dispose()


if __name__ == "__main__":
    main()
