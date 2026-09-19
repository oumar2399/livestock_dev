"""Shared transactional fixtures for backend integration tests."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest


backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import SessionLocal, engine
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.user import User


@pytest.fixture(scope="session")
def binary_engine():
    """Exercise real commits/concurrency only in a disposable PostgreSQL database."""
    import os
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    name = "livestock_binary_test_" + uuid4().hex
    maintenance = create_engine(engine.url.set(database="postgres"), hide_parameters=True)
    isolated = create_engine(engine.url.set(database=name), hide_parameters=True)
    previous = os.environ.get("DATABASE_URL")
    created = False
    try:
        with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        with isolated.begin() as connection:
            connection.exec_driver_sql((backend_dir / "app/db/init.sql").read_text(encoding="utf-8"))
        os.environ["DATABASE_URL"] = isolated.url.render_as_string(hide_password=False)
        config = Config(str(backend_dir / "alembic.ini"))
        config.set_main_option("script_location", str(backend_dir / "alembic"))
        command.upgrade(config, "head")
        yield isolated
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        isolated.dispose()
        if created:
            with maintenance.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        maintenance.dispose()


@pytest.fixture
def binary_db(binary_engine):
    from sqlalchemy.orm import Session

    with binary_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def binary_case(binary_db, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from app.core.security import generate_device_secret, hash_device_secret
    from app.models.device import Device
    from app.services import ml_inference

    db = binary_db
    user = User(email=f"binary-{uuid4().hex}@example.com", password_hash="test-only", name="Binary", role="admin")
    db.add(user)
    db.flush()
    farm = Farm(owner_id=user.id, name="Binary test farm")
    other_farm = Farm(owner_id=user.id, name="Other test farm")
    db.add_all([farm, other_farm])
    db.flush()
    secret = generate_device_secret()
    device = Device(id="BINARY-TEST", farm_id=farm.id, status="active", transport_id=1,
                    device_secret=hash_device_secret(secret))
    animal = Animal(farm_id=farm.id, name="Binary test animal", status="active", assigned_device=device.id)
    db.add_all([device, animal])
    db.commit()
    monkeypatch.setattr(ml_inference, "_artifact", None)
    prediction = MagicMock(return_value=("Resting", 0.9))
    monkeypatch.setattr(ml_inference, "predict_with_confidence", prediction)
    return SimpleNamespace(db=db, user=user, farm=farm, other_farm=other_farm,
                           device=device, animal=animal, secret=secret, prediction=prediction)


@pytest.fixture
def binary_client(binary_case):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1 import devices, telemetry
    from app.core.dependencies import get_current_user
    from app.db.database import get_db

    app = FastAPI()
    app.include_router(telemetry.router, prefix="/api/v1")
    app.include_router(devices.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: binary_case.db
    app.dependency_overrides[get_current_user] = lambda: binary_case.user
    with TestClient(app) as client:
        yield client


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def test_user(db):
    suffix = uuid4().hex[:10]
    user = User(
        email=f"pytest-{suffix}@example.com",
        password_hash="not-used-in-tests",
        name="Pytest User",
        role="farmer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_farm(db, test_user):
    farm = Farm(owner_id=test_user.id, name=f"Pytest Farm {uuid4().hex[:8]}")
    db.add(farm)
    db.commit()
    db.refresh(farm)

    membership = FarmMembership(
        user_id=test_user.id,
        farm_id=farm.id,
        role="owner",
        status="active",
    )
    db.add(membership)
    db.commit()
    return farm


@pytest.fixture
def test_animal(db, test_farm):
    suffix = uuid4().hex[:10]
    animal = Animal(
        farm_id=test_farm.id,
        name="Pytest Animal",
        official_id=f"PYTEST-{suffix}",
        species="bovine",
        assigned_device=f"PYTEST-DEVICE-{suffix}",
        status="active",
    )
    db.add(animal)
    db.commit()
    db.refresh(animal)
    return animal
