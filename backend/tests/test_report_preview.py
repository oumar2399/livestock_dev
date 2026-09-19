"""Report contract tests without a database connection or application startup."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from app.api.v1 import reports
from app.core.config import TARGET_TIMEZONE
from app.core.dependencies import get_current_user
from app.core.timezone import UTC
from app.db.database import get_db
from app.models.alert import Alert
from app.models.daily_summary import DailyBehaviorSummary
from app.models.feedback import AlertFeedback, PredictionFeedback
from app.models.telemetry import Telemetry
from app.models.untimed_telemetry import UntimedTelemetry
from app.schemas.report import ReportDataset
from app.services.csv_export import HEADERS, preview_dataset, stream_dataset


def sample_row(dataset):
    stamp = datetime(2026, 9, 4, 15, tzinfo=UTC)
    if dataset == ReportDataset.UNTIMED_TELEMETRY:
        return UntimedTelemetry(id=1, device_id='=Animal name', received_at=stamp,
            farm_id_at_reception=3, animal_id_at_reception=7, session_id=2**62,
            measured_at=None, time_reliable=False, attribution_status='unknown')
    records = {
        ReportDataset.TELEMETRY: Telemetry(animal_id=7, time=stamp, device_id='M5-test', altitude=Decimal('12.30')),
        ReportDataset.DAILY_SUMMARIES: DailyBehaviorSummary(animal_id=7, date=date(2026, 9, 5), pct_active=60, created_at=stamp),
        ReportDataset.ALERTS: Alert(id=1, animal_id=7, triggered_at=stamp, title='=SUM(1,2)',
            message='Line 1,"quoted"\nLine 2', alert_metadata={'note': 'quoted,"value"'}),
        ReportDataset.PREDICTION_FEEDBACKS: PredictionFeedback(id=1, animal_id=7, user_id=2, created_at=stamp,
            telemetry_time=stamp, verdict='incorrect', correction='Resting'),
        ReportDataset.ALERT_FEEDBACKS: AlertFeedback(id=1, animal_id=7, user_id=2, created_at=stamp, notes='@unsafe'),
    }
    row = (records[dataset], '=Animal name', 3, 'Farm, name\nSecond line')
    if dataset in (ReportDataset.PREDICTION_FEEDBACKS, ReportDataset.ALERT_FEEDBACKS):
        row += ('user@example.com',)
    return row + (True,) if dataset in (ReportDataset.TELEMETRY, ReportDataset.PREDICTION_FEEDBACKS, ReportDataset.ALERT_FEEDBACKS) else row


@pytest.fixture
def query_stub(monkeypatch):
    state = SimpleNamespace(rows=[], queries=[])

    def iterate(query):
        state.queries.append(query.statement.compile(dialect=postgresql.dialect()))
        limit = query._limit_clause.value if query._limit_clause is not None else None
        return iter(state.rows[:limit])

    # Real ORM query construction, but iteration never reaches a database.
    monkeypatch.setattr(Query, '__iter__', iterate)
    return state


@pytest.mark.parametrize('dataset', list(ReportDataset))
def test_preview_matches_csv_cells_and_uses_a_sql_limit(dataset, query_stub):
    query_stub.rows = [sample_row(dataset)] * 25
    with Session() as db:
        filters = dict(db=db, dataset=dataset, farm_id=3, animal_id=7,
            date_from=date(2026, 9, 5), date_to=date(2026, 9, 5), resolved=False)
        preview = preview_dataset(**filters, limit=20)
        exported = list(csv.reader(io.StringIO(''.join(stream_dataset(**filters)).lstrip('\ufeff'))))
    assert preview.columns == exported[0] == list(HEADERS[dataset])
    assert preview.rows == exported[1:21]
    assert len(exported) == 26  # Preview never limits the subsequent full export.
    assert preview.has_more is True
    assert preview.target_timezone == TARGET_TIMEZONE
    assert preview.generated_at.tzinfo is not None
    assert "'=Animal name" in preview.rows[0]
    assert all(len(row) == len(preview.columns) for row in preview.rows)
    preview_sql, export_sql = query_stub.queries
    assert 'LIMIT' in str(preview_sql)
    assert 'LIMIT' not in str(export_sql)
    assert 21 in preview_sql.params.values()
    assert 'ORDER BY' in str(preview_sql)
    assert 3 in preview_sql.params.values() and 7 in preview_sql.params.values()
    if dataset == ReportDataset.ALERTS:
        assert 'alerts.resolved_at IS NULL' in str(preview_sql)
    if dataset != ReportDataset.DAILY_SUMMARIES:
        timestamps = [value for value in preview_sql.params.values() if isinstance(value, datetime)]
        assert [value.replace(tzinfo=UTC) for value in timestamps] == [
            datetime(2026, 9, 4, 15, tzinfo=UTC), datetime(2026, 9, 5, 15, tzinfo=UTC)]


@pytest.mark.parametrize('row_count,has_more', [(0, False), (1, False), (20, False), (21, True)])
def test_preview_truncation_and_empty_state(row_count, has_more, query_stub):
    query_stub.rows = [sample_row(ReportDataset.ALERTS)] * row_count
    with Session() as db:
        preview = preview_dataset(db, ReportDataset.ALERTS, None, None, None, None, None)
    assert len(preview.rows) == min(row_count, 20)
    assert preview.has_more is has_more
    assert preview.columns


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(reports.router, prefix='/api/v1')
    db = MagicMock()
    user = SimpleNamespace(id=1, role='admin')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client, db, user, app


@pytest.mark.parametrize('path', ['preview', 'export'])
@pytest.mark.parametrize('role', ['farmer', 'owner', 'vet'])
def test_both_routes_remain_admin_only(path, role, api_client):
    client, db, user, _ = api_client
    user.role = role
    response = client.get(f'/api/v1/reports/{path}/alerts')
    assert response.status_code == 403
    db.query.assert_not_called()


@pytest.mark.parametrize('path', ['preview', 'export'])
def test_missing_authentication_is_rejected(path, api_client):
    client, db, _, app = api_client
    del app.dependency_overrides[get_current_user]
    assert client.get(f'/api/v1/reports/{path}/alerts').status_code in (401, 403)
    db.query.assert_not_called()


@pytest.mark.parametrize('path', ['preview', 'export'])
@pytest.mark.parametrize('dataset,query,expected', [
    ('telemetry', '', 400),
    ('alerts', '?date_from=2026-09-05&date_to=2026-09-04', 400),
    ('alerts', '?date_from=2026-02-30', 422),
    ('alerts', '?farm_id=0', 422),
    ('missing', '', 422),
])
def test_shared_filter_validation(path, dataset, query, expected, api_client):
    client, _, _, _ = api_client
    assert client.get(f'/api/v1/reports/{path}/{dataset}{query}').status_code == expected


@pytest.mark.parametrize('limit', [0, 51, -1])
def test_preview_limit_is_bounded(limit, api_client):
    client, _, _, _ = api_client
    assert client.get(f'/api/v1/reports/preview/alerts?limit={limit}').status_code == 422


@pytest.mark.parametrize('path', ['preview', 'export'])
def test_missing_farm_and_cross_farm_animal_are_rejected(path, api_client):
    client, db, _, _ = api_client
    db.query.return_value.filter.return_value.first.return_value = None
    assert client.get(f'/api/v1/reports/{path}/alerts?farm_id=3').status_code == 404
    db.query.return_value.filter.return_value.first.side_effect = [(3,), SimpleNamespace(farm_id=4)]
    assert client.get(f'/api/v1/reports/{path}/alerts?farm_id=3&animal_id=7').status_code == 400


@pytest.mark.parametrize('dataset', list(ReportDataset))
def test_preview_response_contract(dataset, query_stub, api_client):
    client, _, _, app = api_client
    query_stub.rows = [sample_row(dataset)]
    with Session() as db:
        app.dependency_overrides[get_db] = lambda: db
        response = client.get(f'/api/v1/reports/preview/{dataset.value}?date_from=2026-09-05&date_to=2026-09-05')
    assert response.status_code == 200
    body = response.json()
    assert body['dataset'] == dataset.value
    assert body['columns'] == list(HEADERS[dataset])
    assert len(body['rows']) == 1 and body['has_more'] is False
    assert all(isinstance(value, str) for value in body['rows'][0])
