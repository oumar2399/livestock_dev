"""Phase 3, group 1 (acceptance test 2026-10-07): roles per farm, closed registration,
admin-only farm creation, scripts/create_admin.py.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1 import alerts, animals, auth, farms, feedback, geofences, memberships, veterinary
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.security import verify_password
from app.db import database
from app.db.database import get_db
from app.models.user import User
from test_b2_provenance_and_access import world  # noqa: F401  (fixture reuse)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import create_admin  # noqa: E402


@pytest.fixture
def api(world):  # noqa: F811
    app = FastAPI()
    for module in (alerts, animals, auth, farms, feedback, geofences, memberships, veterinary):
        app.include_router(module.router, prefix="/api/v1")
    state = {"user": world.owner_b.id}
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["user"])

    def as_user(user):
        state["user"] = user.id
        return client

    with TestClient(app) as client:
        client.as_user = as_user
        yield client


SQUARE = [{"latitude": 0, "longitude": 0}, {"latitude": 0, "longitude": 1}, {"latitude": 1, "longitude": 1}]


def _call(client, world, action):  # noqa: F811
    if action == "create geofence":
        return client.post("/api/v1/geofences/", json={
            "farm_id": world.farm_b.id, "name": "Zone", "type": "pasture", "points": SQUARE})
    if action == "acknowledge alert":
        return client.patch(f"/api/v1/alerts/{world.alert_b.id}",
                            json={"acknowledged_at": datetime.now(timezone.utc).isoformat()})
    if action == "alert feedback":
        return client.post(f"/api/v1/feedback/alerts/{world.alert_b.id}", json={"verdict": "false_alarm"})
    if action == "edit animal":
        return client.put(f"/api/v1/animals/{world.animal.id}", json={"weight": 410})
    if action == "invite member":
        return client.post(f"/api/v1/farms/{world.farm_b.id}/members", json={
            "user_email": f"invited-{uuid4().hex[:8]}@example.com", "password": "secret123", "role": "vet"})
    if action == "read vet cases":
        return client.get(f"/api/v1/farms/{world.farm_b.id}/veterinary-cases")
    raise AssertionError(action)


# owner = all rights incl. user management; farmer = operational, no user management;
# vet = view + veterinary, no alert handling, no feedback (decisions 3.1, Phase 3).
MATRIX = {
    "create geofence":   {"owner_b": True,  "farmer_b": True,  "vet_b": False},
    "acknowledge alert": {"owner_b": True,  "farmer_b": True,  "vet_b": False},
    "alert feedback":    {"owner_b": True,  "farmer_b": True,  "vet_b": False},
    "edit animal":       {"owner_b": True,  "farmer_b": True,  "vet_b": False},
    "invite member":     {"owner_b": True,  "farmer_b": False, "vet_b": False},
    "read vet cases":    {"owner_b": True,  "farmer_b": True,  "vet_b": True},
}


@pytest.mark.parametrize("action,role", [(a, r) for a, roles in MATRIX.items() for r in roles])
def test_permission_matrix(world, api, action, role):  # noqa: F811
    response = _call(api.as_user(getattr(world, role)), world, action)
    if MATRIX[action][role]:
        assert response.status_code in (200, 201), (action, role, response.text)
    else:
        assert response.status_code == 403, (action, role, response.text)


def test_registration_is_closed_by_default(world, api):  # noqa: F811
    assert settings.PUBLIC_REGISTRATION_ENABLED is False
    response = api.post("/api/v1/auth/register", json={
        "email": f"public-{uuid4().hex[:8]}@example.com", "password": "secret123", "name": "Public"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Registration is closed: accounts are created by invitation."


def test_development_switch_reopens_registration(world, api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "PUBLIC_REGISTRATION_ENABLED", True)
    response = api.post("/api/v1/auth/register", json={
        "email": f"dev-{uuid4().hex[:8]}@example.com", "password": "secret123", "name": "Dev"})
    assert response.status_code == 201


@pytest.mark.parametrize("role", ["owner_b", "farmer_b", "vet_b"])
def test_only_the_admin_creates_farms(world, api, role):  # noqa: F811
    assert api.as_user(getattr(world, role)).post("/api/v1/farms/", json={"name": "Mine"}).status_code == 403
    created = api.as_user(world.admin).post("/api/v1/farms/", json={"name": f"Admin farm {uuid4().hex[:6]}"})
    assert created.status_code == 201
    assert created.json()["owner_id"] is None


# ── scripts/create_admin.py on the disposable database ──────────────────────

@pytest.fixture
def admin_db():
    url = database.engine.url.render_as_string(hide_password=False)
    email = f"script-admin-{uuid4().hex[:8]}@example.com"
    yield url, email
    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email LIKE 'script-%@example.com'"))


def _prompt(*answers):
    replies = iter(answers)
    return lambda _label: next(replies)


def _user_by_email(email):
    session = database.SessionLocal()
    try:
        return session.query(User).filter(User.email == email).first()
    finally:
        session.close()


def test_create_admin_creates_a_platform_admin(admin_db):
    url, email = admin_db
    assert create_admin.main(["--database-url", url, "--email", email, "--name", "First"],
                             prompt=_prompt("long-enough-pw", "long-enough-pw")) == 0
    user = _user_by_email(email)
    assert user.role == "admin" and user.name == "First"
    assert verify_password("long-enough-pw", user.password_hash)


def test_create_admin_refuses_an_existing_email_and_promotes_on_request(admin_db):
    url, email = admin_db
    create_admin.main(["--database-url", url, "--email", email], prompt=_prompt("long-enough-pw", "long-enough-pw"))
    with pytest.raises(SystemExit, match="already exists"):
        create_admin.main(["--database-url", url, "--email", email], prompt=_prompt("x" * 8, "x" * 8))
    session = database.SessionLocal()
    try:
        session.query(User).filter(User.email == email).update({"role": "farmer"})
        session.commit()
    finally:
        session.close()
    assert create_admin.main(["--database-url", url, "--email", email, "--promote"]) == 0
    assert _user_by_email(email).role == "admin"


@pytest.mark.parametrize("answers,message", [
    (("short", "short"), "at least 8"),
    (("long-enough-pw", "different-pw"), "do not match"),
])
def test_create_admin_rejects_weak_or_mismatched_passwords(admin_db, answers, message):
    url, email = admin_db
    with pytest.raises(SystemExit, match=message):
        create_admin.main(["--database-url", url, "--email", email], prompt=_prompt(*answers))
    assert _user_by_email(email) is None


def test_create_admin_never_accepts_a_password_argument(admin_db):
    url, email = admin_db
    with pytest.raises(SystemExit):
        create_admin.main(["--database-url", url, "--email", email, "--password", "on-the-command-line"])
