"""
Tests d'intégration pour les routes API de localisation et d'historique GPS (Lot B).
GET /farms/{farm_id}/locations/latest
GET /farms/{farm_id}/locations/{animal_id}
GET /farms/{farm_id}/locations/{animal_id}/history
"""
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement

from app.api.v1 import locations
from app.core.dependencies import get_current_user
from app.core.timezone import UTC, utc_now
from app.db.database import get_db
from app.models.animal import Animal
from app.models.device import Device
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.provenance import AnimalTrackingPeriod
from app.models.telemetry import Telemetry
from app.models.user import User


@pytest.fixture
def loc_api_env(binary_db):
    db = binary_db
    suffix = uuid4().hex[:6]
    owner = User(email=f"owner-{suffix}@test.com", password_hash="hash", name="Owner", role="farmer")
    outsider = User(email=f"outsider-{suffix}@test.com", password_hash="hash", name="Outsider", role="farmer")

    db.add_all([owner, outsider])
    db.commit()

    farm1 = Farm(name=f"Ferme Alpha {suffix}", owner_id=owner.id)
    farm2 = Farm(name=f"Ferme Autre {suffix}", owner_id=outsider.id)
    db.add_all([farm1, farm2])
    db.commit()

    m_owner = FarmMembership(farm_id=farm1.id, user_id=owner.id, role="owner", status="active")
    db.add(m_owner)
    db.commit()

    # Animal sur Ferme 1
    device1 = Device(id=f"DEV-{suffix}-1", farm_id=farm1.id, model="M5Stack", status="active")
    db.add(device1)
    db.commit()

    animal1 = Animal(name="Vache 1", species="cattle", farm_id=farm1.id, status="active", assigned_device=device1.id)
    db.add(animal1)
    db.commit()

    # Animal sur Ferme 2
    animal2 = Animal(name="Vache Autre", species="cattle", farm_id=farm2.id, status="active")
    db.add(animal2)
    db.commit()

    now = utc_now()
    tracking1 = AnimalTrackingPeriod(
        animal_id=animal1.id,
        device_id=device1.id,
        farm_id=farm1.id,
        valid_from=now - timedelta(days=2),
        valid_to=None,
        source="collar_assignment",
    )
    db.add(tracking1)

    # Télémétrie avec position
    telem = Telemetry(
        animal_id=animal1.id,
        time=now - timedelta(minutes=5),
        device_id=device1.id,
        latitude=45.5,
        longitude=6.5,
        location=WKTElement("POINT(6.5 45.5)", srid=4326),
        speed=1.0,
        satellites=7,
    )
    db.add(telem)
    db.commit()

    app = FastAPI()
    app.include_router(locations.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app, raise_server_exceptions=False)

    return {
        "client": client,
        "app": app,
        "owner": owner,
        "outsider": outsider,
        "farm1": farm1,
        "farm2": farm2,
        "animal1": animal1,
        "animal2": animal2,
    }


def test_list_farm_locations_authorized(loc_api_env):
    client = loc_api_env["client"]
    app = loc_api_env["app"]
    owner = loc_api_env["owner"]
    farm1 = loc_api_env["farm1"]

    app.dependency_overrides[get_current_user] = lambda: owner

    resp = client.get(f"/api/v1/farms/{farm1.id}/locations/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["animal_id"] == loc_api_env["animal1"].id
    assert data[0]["latitude"] == pytest.approx(45.5)
    assert data[0]["longitude"] == pytest.approx(6.5)


def test_list_farm_locations_forbidden(loc_api_env):
    client = loc_api_env["client"]
    app = loc_api_env["app"]
    outsider = loc_api_env["outsider"]
    farm1 = loc_api_env["farm1"]

    # Utilisateur sans accès à la ferme 1
    app.dependency_overrides[get_current_user] = lambda: outsider

    resp = client.get(f"/api/v1/farms/{farm1.id}/locations/latest")
    assert resp.status_code == 403


def test_get_animal_location(loc_api_env):
    client = loc_api_env["client"]
    app = loc_api_env["app"]
    owner = loc_api_env["owner"]
    farm1 = loc_api_env["farm1"]
    animal1 = loc_api_env["animal1"]

    app.dependency_overrides[get_current_user] = lambda: owner

    resp = client.get(f"/api/v1/farms/{farm1.id}/locations/{animal1.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["animal_id"] == animal1.id
    assert data["position_is_animal"] is True
    assert data["latitude"] == pytest.approx(45.5)


def test_get_animal_location_wrong_farm(loc_api_env):
    client = loc_api_env["client"]
    app = loc_api_env["app"]
    owner = loc_api_env["owner"]
    farm1 = loc_api_env["farm1"]
    animal2 = loc_api_env["animal2"]  # Animal de Ferme 2

    app.dependency_overrides[get_current_user] = lambda: owner

    # Tente d'accéder à animal2 via farm1
    resp = client.get(f"/api/v1/farms/{farm1.id}/locations/{animal2.id}")
    assert resp.status_code in (403, 404)


def test_get_animal_history(loc_api_env):
    client = loc_api_env["client"]
    app = loc_api_env["app"]
    owner = loc_api_env["owner"]
    farm1 = loc_api_env["farm1"]
    animal1 = loc_api_env["animal1"]

    app.dependency_overrides[get_current_user] = lambda: owner

    resp = client.get(f"/api/v1/farms/{farm1.id}/locations/{animal1.id}/history?hours=24")
    assert resp.status_code == 200
    data = resp.json()
    assert data["animal_id"] == animal1.id
    assert "segments" in data
    assert "gaps" in data
    assert data["total_points"] >= 1


def test_get_animal_history_invalid_dates(loc_api_env):
    client = loc_api_env["client"]
    app = loc_api_env["app"]
    owner = loc_api_env["owner"]
    farm1 = loc_api_env["farm1"]
    animal1 = loc_api_env["animal1"]

    app.dependency_overrides[get_current_user] = lambda: owner

    # start après end
    resp = client.get(
        f"/api/v1/farms/{farm1.id}/locations/{animal1.id}/history"
        "?start=2026-09-22T12:00:00Z&end=2026-09-22T10:00:00Z"
    )
    assert resp.status_code == 422
