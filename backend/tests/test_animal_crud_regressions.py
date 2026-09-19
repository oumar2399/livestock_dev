"""Animal writes, retention and bounded farm-scoped reads on PostgreSQL."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.v1 import animals
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.animal import Animal
from app.models.alert import Alert
from app.models.daily_summary import DailyBehaviorSummary
from app.models.feedback import AlertFeedback, PredictionFeedback
from app.models.membership import FarmMembership
from app.models.telemetry import Telemetry


@pytest.fixture
def animal_client(binary_case):
    app = FastAPI()
    app.include_router(animals.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: binary_case.db
    app.dependency_overrides[get_current_user] = lambda: binary_case.user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("payload", [
    {"birth_date": (date.today() + timedelta(days=1)).isoformat()},
    {"name": None}, {"name": ""}, {"status": None}, {"status": "invalid"},
    {"official_id": "x" * 51}, {"breed": "x" * 101},
    {"assigned_device": "x" * 51}, {"weight": 10000},
])
def test_invalid_update_does_not_persist_or_break_list(binary_case, animal_client, payload):
    case = binary_case
    original = animal_client.get(f"/api/v1/animals/{case.animal.id}").json()
    response = animal_client.put(f"/api/v1/animals/{case.animal.id}", json=payload)
    assert response.status_code == 422
    assert animal_client.get(f"/api/v1/animals/{case.animal.id}").json() == original
    response = animal_client.get("/api/v1/animals/", params={"farm_id": case.farm.id})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_update_omissions_and_nullable_fields(binary_case, animal_client):
    url = f"/api/v1/animals/{binary_case.animal.id}"
    response = animal_client.put(url, json={"birth_date": date.today().isoformat(),
                                          "breed": "Holstein", "name": "Updated"})
    assert response.status_code == 200
    response = animal_client.put(url, json={"birth_date": None, "breed": None,
                                          "assigned_device": None})
    assert response.status_code == 200
    assert response.json()["birth_date"] is None
    assert response.json()["breed"] is None
    assert response.json()["assigned_device"] is None
    assert response.json()["name"] == "Updated"
    assert response.json()["status"] == "active"
    assert animal_client.put(url, json={}).status_code == 200


@pytest.mark.parametrize("loaded", [False, True])
def test_delete_cascades_dependents_but_retains_raw_telemetry(binary_case, animal_client, loaded):
    case = binary_case
    db, animal_id = case.db, case.animal.id
    other = Animal(farm_id=case.farm.id, name="Keep me")
    db.add(other)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add_all([
        Telemetry(animal_id=animal_id, time=now, device_id=case.device.id),
        DailyBehaviorSummary(animal_id=animal_id, date=date.today(), pct_active=20,
                             pct_resting=80, n_predictions=10),
        DailyBehaviorSummary(animal_id=other.id, date=date.today(), pct_active=40,
                             pct_resting=60, n_predictions=10),
        PredictionFeedback(animal_id=animal_id, user_id=case.user.id,
                           telemetry_time=now.replace(tzinfo=None), verdict="correct"),
    ])
    alert = Alert(animal_id=animal_id, type="battery", severity="warning")
    db.add(alert)
    db.flush()
    db.add(AlertFeedback(alert_id=alert.id, animal_id=animal_id, user_id=case.user.id,
                         alert_type="battery", verdict="false_alarm"))
    db.commit()
    if loaded:
        assert len(case.animal.daily_behavior_summaries) == 1
        assert len(case.animal.alerts) == 1
    else:
        db.expire(case.animal)
    response = animal_client.delete(f"/api/v1/animals/{animal_id}")
    assert response.status_code == 204, response.text
    assert db.query(Animal).filter_by(id=animal_id).count() == 0
    for model in (DailyBehaviorSummary, Alert, PredictionFeedback, AlertFeedback):
        assert db.query(model).filter_by(animal_id=animal_id).count() == 0
    assert db.query(Telemetry).filter_by(animal_id=animal_id).count() == 1
    assert db.query(DailyBehaviorSummary).filter_by(animal_id=other.id).count() == 1
    assert db.query(Animal).filter_by(id=other.id).count() == 1


def test_list_batches_latest_positions_with_stable_pagination(binary_case, animal_client):
    case = binary_case
    herd = [case.animal] + [Animal(farm_id=case.farm.id, name=f"Animal {n}") for n in range(11)]
    outsider = Animal(farm_id=case.other_farm.id, name="Private animal")
    case.db.add_all(herd[1:] + [outsider])
    case.db.flush()
    now = datetime.now(timezone.utc)
    for animal in herd[:-1] + [outsider]:
        for offset, latitude in ((-1, 5.0), (0, 6.0)):
            case.db.add(Telemetry(animal_id=animal.id, time=now + timedelta(seconds=offset),
                                  device_id=case.device.id, latitude=latitude, longitude=-4.0))
    case.user.role = "farmer"
    case.db.add(FarmMembership(user_id=case.user.id, farm_id=case.farm.id,
                               role="owner", status="active"))
    case.db.commit()
    ids = [animal.id for animal in herd]
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    # Load expired fixture objects before counting the endpoint's SQL.
    farm_id = case.farm.id
    _ = case.user.role
    connection = case.db.connection()
    event.listen(connection, "before_cursor_execute", capture)
    try:
        response = animal_client.get("/api/v1/animals/", params={"farm_id": farm_id})
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    assert len(statements) == 4  # Memberships, count, page, latest positions.
    assert sum("FROM telemetry" in sql for sql in statements) == 1
    rows = response.json()["animals"]
    assert [row["id"] for row in rows] == sorted(ids)
    assert rows[-1]["last_update"] is None
    assert rows[-1]["last_latitude"] is None
    assert all(row["last_latitude"] == 6.0 for row in rows[:-1])
    pages = [animal_client.get("/api/v1/animals/", params={"page": page, "page_size": 5}).json()
             for page in (1, 2, 3)]
    assert [row["id"] for page in pages for row in page["animals"]] == sorted(ids)
    assert animal_client.get("/api/v1/animals/", params={"farm_id": case.other_farm.id}).status_code == 403
    assert animal_client.delete(f"/api/v1/animals/{outsider.id}").status_code == 403
    assert animal_client.put(f"/api/v1/animals/{outsider.id}", json={"name": "No"}).status_code == 403


def test_empty_page_keeps_total(binary_case, animal_client):
    response = animal_client.get("/api/v1/animals/", params={"farm_id": binary_case.farm.id, "page": 100})
    assert response.status_code == 200
    assert response.json()["animals"] == []
    assert response.json()["total"] == 1
