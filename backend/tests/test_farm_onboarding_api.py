"""Unit and integration tests for Lot A: Farm Onboarding and Idempotency."""

import pytest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import farms
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.user import User


@pytest.fixture
def farm_test_context(db):
    suffix = uuid4().hex[:8]
    user = User(
        email=f"onboarding-{suffix}@example.com",
        password_hash="dummy-hash",
        name="Onboarding User",
        role="farmer",  # Regular user
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    app = FastAPI()
    app.include_router(farms.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app, raise_server_exceptions=False)
    return {"user": user, "client": client, "db": db}


def test_create_farm_auto_membership(farm_test_context):
    client = farm_test_context["client"]
    db = farm_test_context["db"]
    user = farm_test_context["user"]

    payload = {
        "name": "Ferme du Pilote",
        "address": "123 Chemin du Val",
        "size_hectares": 45.5,
    }
    res = client.post("/api/v1/farms/", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Ferme du Pilote"
    assert data["owner_id"] == user.id
    assert data["membership_role"] == "owner"
    assert "manage_farm" in data["permissions"]
    assert "edit_animals" in data["permissions"]

    # Verify in DB
    membership = (
        db.query(FarmMembership)
        .filter(FarmMembership.farm_id == data["id"], FarmMembership.user_id == user.id)
        .first()
    )
    assert membership is not None
    assert membership.role == "owner"
    assert membership.status == "active"


def test_create_farm_idempotency_retry(farm_test_context):
    client = farm_test_context["client"]
    db = farm_test_context["db"]
    user = farm_test_context["user"]

    req_id = f"req-{uuid4().hex}"
    payload = {
        "name": "Ferme Idempotente",
        "address": "456 Route Verte",
        "size_hectares": 20.0,
        "client_request_id": req_id,
    }

    # First attempt
    res1 = client.post("/api/v1/farms/", json=payload)
    assert res1.status_code == 201
    data1 = res1.json()

    # Second attempt (same payload + same client_request_id)
    res2 = client.post("/api/v1/farms/", json=payload)
    assert res2.status_code in (200, 201)
    data2 = res2.json()

    assert data1["id"] == data2["id"]
    assert data1["name"] == data2["name"]

    # Verify no duplicate farm in DB
    farms_count = db.query(Farm).filter(Farm.name == "Ferme Idempotente", Farm.owner_id == user.id).count()
    assert farms_count == 1


def test_create_farm_idempotency_conflict_on_mismatch(farm_test_context):
    client = farm_test_context["client"]

    req_id = f"req-{uuid4().hex}"
    payload1 = {
        "name": "Ferme Initiale",
        "client_request_id": req_id,
    }
    res1 = client.post("/api/v1/farms/", json=payload1)
    assert res1.status_code == 201

    # Retry with same req_id but different name
    payload2 = {
        "name": "Ferme Modifiée",
        "client_request_id": req_id,
    }
    res2 = client.post("/api/v1/farms/", json=payload2)
    assert res2.status_code == 409
    assert "idempotency key already exists with different parameters" in res2.json()["detail"]


def test_list_and_get_farm(farm_test_context):
    client = farm_test_context["client"]

    # Create farm
    create_res = client.post("/api/v1/farms/", json={"name": "Ferme Test Get"})
    assert create_res.status_code == 201
    farm_id = create_res.json()["id"]

    # List farms
    list_res = client.get("/api/v1/farms/")
    assert list_res.status_code == 200
    farms_list = list_res.json()
    assert any(f["id"] == farm_id for f in farms_list)

    # Get farm detail
    get_res = client.get(f"/api/v1/farms/{farm_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == farm_id
    assert get_res.json()["membership_role"] == "owner"
    assert "manage_farm" in get_res.json()["permissions"]
