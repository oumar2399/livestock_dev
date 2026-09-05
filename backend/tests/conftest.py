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
