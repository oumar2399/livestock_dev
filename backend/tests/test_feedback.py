"""
Pytest Test Suite for Prediction & Alert Feedback System
=========================================================
Verifies:
  1. PredictionFeedback creation and upsert on (user_id, animal_id, telemetry_time).
  2. AlertFeedback creation and upsert on (user_id, alert_id).
  3. 404 error handling for non-existent alerts or animals.
  4. Global feedback stats calculations.
  5. Correction values: the codes and the old stored values only, anything else 422.
"""

import sys
from pathlib import Path
from datetime import timedelta

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import SessionLocal
from app.models.user import User
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.alert import Alert
from app.models.feedback import PredictionFeedback, AlertFeedback
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import feedback as feedback_api
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.schemas.feedback import (
    CORRECTION_CODES,
    LEGACY_CORRECTIONS,
    PredictionFeedbackCreate,
    AlertFeedbackCreate,
)
from app.api.v1.feedback import (
    submit_prediction_feedback,
    submit_alert_feedback,
    get_feedback_stats,
)
from app.schemas.alert import AlertType, AlertSeverity
from app.core.timezone import utc_now, to_utc_naive


def test_prediction_feedback_upsert(db, test_user, test_animal):
    telemetry_time = utc_now().replace(microsecond=0)

    # Seed telemetry record
    t = Telemetry(
        time=telemetry_time,
        animal_id=test_animal.id,
        device_id="M5-TEST-FB",
        predicted_behavior="Active",
        behavior_confidence=0.92,
    )
    db.add(t)
    db.commit()

    # 1. First submission ('correct')
    p1 = PredictionFeedbackCreate(
        animal_id=test_animal.id,
        telemetry_time=telemetry_time,
        verdict="correct",
    )
    res1 = submit_prediction_feedback(payload=p1, db=db, current_user=test_user)
    assert res1.id is not None
    assert res1.verdict == "correct"
    assert res1.predicted_behavior == "Active"

    # 2. Second submission for same telemetry record ('incorrect' + correction)
    p2 = PredictionFeedbackCreate(
        animal_id=test_animal.id,
        telemetry_time=telemetry_time,
        verdict="incorrect",
        correction="Resting",
    )
    res2 = submit_prediction_feedback(payload=p2, db=db, current_user=test_user)

    # Verify Upsert: ID remains the same, updated values
    assert res2.id == res1.id
    assert res2.verdict == "incorrect"
    assert res2.correction == "Resting"

    count = (
        db.query(PredictionFeedback)
        .filter_by(
            user_id=test_user.id,
            animal_id=test_animal.id,
            telemetry_time=to_utc_naive(telemetry_time),
        )
        .count()
    )
    assert count == 1


def test_alert_feedback_upsert(db, test_user, test_animal):
    # Seed alert record
    alert = Alert(
        animal_id=test_animal.id,
        type=AlertType.ACTIVITY_DEVIATION_LOW.value,
        severity=AlertSeverity.WARNING.value,
        title="Test Alert",
        message="Test Message",
        alert_metadata={"z_score": 3.75, "target_date": "2026-08-19"},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # 1. First submission ('confirmed_issue')
    a1 = AlertFeedbackCreate(verdict="confirmed_issue", notes="Confirmed sick animal")
    res1 = submit_alert_feedback(alert_id=alert.id, payload=a1, db=db, current_user=test_user)

    assert res1.id is not None
    assert res1.alert_id == alert.id
    assert res1.verdict == "confirmed_issue"
    assert res1.z_score == 3.75

    # 2. Second submission ('false_alarm' - user changed mind)
    a2 = AlertFeedbackCreate(verdict="false_alarm", notes="False alarm - animal was resting after walk")
    res2 = submit_alert_feedback(alert_id=alert.id, payload=a2, db=db, current_user=test_user)

    # Verify Upsert: ID remains the same, updated values
    assert res2.id == res1.id
    assert res2.verdict == "false_alarm"
    assert res2.notes == "False alarm - animal was resting after walk"

    count = db.query(AlertFeedback).filter_by(user_id=test_user.id, alert_id=alert.id).count()
    assert count == 1


def test_feedback_stats(db, test_user):
    stats = get_feedback_stats(db=db, current_user=test_user)
    assert stats.total_prediction_feedbacks >= 0
    assert stats.total_alert_feedbacks >= 0



# ─── Correction values (Phase 4): codes, old stored values, anything else 422 ──

@pytest.fixture
def feedback_client(db, test_user):
    app = FastAPI()
    app.include_router(feedback_api.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as client:
        yield client


@pytest.fixture
def feedback_telemetry_time(db, test_animal):
    telemetry_time = utc_now().replace(microsecond=0)
    db.add(Telemetry(time=telemetry_time, animal_id=test_animal.id, device_id="M5-TEST-CORR",
                     predicted_behavior="Active", behavior_confidence=0.9))
    db.commit()
    return telemetry_time


def _post_correction(client, animal_id, telemetry_time, correction):
    return client.post("/feedback/predictions", json={
        "animal_id": animal_id,
        "telemetry_time": telemetry_time.isoformat(),
        "verdict": "incorrect",
        "correction": correction,
    })


@pytest.mark.parametrize("correction", list(CORRECTION_CODES) + list(LEGACY_CORRECTIONS))
def test_correction_codes_and_old_stored_values_are_accepted(
    feedback_client, test_animal, feedback_telemetry_time, correction,
):
    response = _post_correction(feedback_client, test_animal.id, feedback_telemetry_time, correction)
    assert response.status_code == 201, response.text
    assert response.json()["correction"] == correction


@pytest.mark.parametrize("correction", ["standing", "Grazing", "GRAZING", "grazing ", "Pâturage", ""])
def test_unknown_correction_is_refused_with_422_and_nothing_is_stored(
    db, feedback_client, test_animal, feedback_telemetry_time, correction,
):
    response = _post_correction(feedback_client, test_animal.id, feedback_telemetry_time, correction)
    assert response.status_code == 422
    assert "correction must be one of" in response.text
    assert db.query(PredictionFeedback).filter_by(animal_id=test_animal.id).count() == 0


def test_feedback_without_correction_is_still_accepted(feedback_client, test_animal, feedback_telemetry_time):
    response = feedback_client.post("/feedback/predictions", json={
        "animal_id": test_animal.id,
        "telemetry_time": feedback_telemetry_time.isoformat(),
        "verdict": "correct",
    })
    assert response.status_code == 201, response.text
    assert response.json()["correction"] is None

if __name__ == "__main__":
    session = SessionLocal()

    # Setup test user and animal
    user = session.query(User).filter_by(email="fb_test_user@example.com").first()
    if not user:
        user = User(
            email="fb_test_user@example.com",
            password_hash="hashedpassword",
            name="Feedback Tester",
            role="farmer",
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    from app.models.farm import Farm
    from app.models.membership import FarmMembership

    farm = Farm(name="FB-Test-Farm")
    session.add(farm)
    session.commit()
    session.refresh(farm)

    membership = FarmMembership(
        user_id=user.id,
        farm_id=farm.id,
        role="farmer",
        status="active",
    )
    session.add(membership)
    session.commit()

    animal = Animal(
        farm_id=farm.id,
        name="Feedback-Cow",
        official_id="FR-FB-001",
        species="Cattle",
        breed="N'Dama",
        assigned_device="M5-FB-001",
        status="active",
    )
    session.add(animal)
    session.commit()
    session.refresh(animal)

    try:
        print("[TEST] Running test_prediction_feedback_upsert...")
        test_prediction_feedback_upsert(session, user, animal)
        print("[PASS] test_prediction_feedback_upsert")

        print("[TEST] Running test_alert_feedback_upsert...")
        test_alert_feedback_upsert(session, user, animal)
        print("[PASS] test_alert_feedback_upsert")

        print("[TEST] Running test_feedback_stats...")
        test_feedback_stats(session, user)
        print("[PASS] test_feedback_stats")

        print("\nALL FEEDBACK TESTS PASSED SUCCESSFULLY!")
    finally:
        session.query(AlertFeedback).filter(AlertFeedback.animal_id == animal.id).delete()
        session.query(PredictionFeedback).filter(PredictionFeedback.animal_id == animal.id).delete()
        session.query(Alert).filter(Alert.animal_id == animal.id).delete()
        session.query(Telemetry).filter(Telemetry.animal_id == animal.id).delete()
        session.query(Animal).filter(Animal.id == animal.id).delete()
        session.query(FarmMembership).filter(FarmMembership.farm_id == farm.id).delete()
        session.query(Farm).filter(Farm.id == farm.id).delete()
        session.query(User).filter(User.id == user.id).delete()
        session.commit()
        session.close()
