"""Focused regression tests for data-integrity hardening."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.api.v1.activity import _build_budget, _build_hourly
from app.api.v1.auth import delete_user, update_me
from app.api.v1.feedback import submit_prediction_feedback
from app.api.v1.predict import PredictRequest, predict_behavior
from app.models.animal import Animal
from app.models.device import Device
from app.schemas.auth import UserUpdate
from app.schemas.feedback import PredictionFeedbackCreate
from app.services.device_assignment import validate_device_assignment


def _user(user_id: int = 1, role: str = "owner") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


@patch("app.services.device_assignment.require_farm")
def test_device_assignment_rejects_cross_farm(mock_require_farm):
    db = MagicMock()
    device_query = MagicMock()
    device_query.filter.return_value.first.return_value = Device(id="M5-X", farm_id=2)
    db.query.return_value = device_query

    with pytest.raises(HTTPException) as exc:
        validate_device_assignment(db, _user(), 1, "M5-X")

    assert exc.value.status_code == 409
    mock_require_farm.assert_called_once()


@patch("app.services.device_assignment.require_farm")
def test_device_assignment_rejects_duplicate(mock_require_farm):
    db = MagicMock()
    device_query = MagicMock()
    device_query.filter.return_value.first.return_value = Device(id="M5-X", farm_id=1)
    animal_query = MagicMock()
    animal_query.filter.return_value.first.return_value = Animal(id=9, farm_id=1, name="A")
    db.query.side_effect = [device_query, animal_query]

    with pytest.raises(HTTPException) as exc:
        validate_device_assignment(db, _user(), 1, "M5-X")

    assert exc.value.status_code == 409


def test_activity_budget_uses_each_window_duration():
    records = [
        SimpleNamespace(
            predicted_behavior="Active",
            activity_state=None,
            sample_rate=10,
            window_samples=50,
        ),
        SimpleNamespace(
            predicted_behavior="Resting",
            activity_state=None,
            sample_rate=10,
            window_samples=100,
        ),
    ]

    budget = _build_budget(records)

    assert budget.Active.minutes == 0.1
    assert budget.Active.percentage == 33.3
    assert budget.Resting.minutes == 0.2
    assert budget.Resting.percentage == 66.7


def test_activity_budget_ignores_unknown_model_classes():
    records = [
        SimpleNamespace(
            predicted_behavior="Active",
            activity_state=None,
            sample_rate=10,
            window_samples=50,
        ),
        SimpleNamespace(
            predicted_behavior="UnknownClass",
            activity_state=None,
            sample_rate=10,
            window_samples=50,
        ),
    ]

    budget = _build_budget(records)

    assert budget.Active.percentage == 100.0
    assert budget.Resting.percentage == 0.0


def test_hourly_breakdown_converts_utc_to_tokyo():
    record = SimpleNamespace(
        time=datetime(2026, 9, 1, 15, 30, tzinfo=timezone.utc),
        predicted_behavior="Active",
        activity_state=None,
        activity=0.9,
    )

    hourly = _build_hourly([record])

    assert hourly[0].record_count == 1
    assert hourly[15].record_count == 0


@patch("app.api.v1.predict.require_animal_access")
@patch("app.api.v1.predict.ml_inference.get_model_info")
@patch("app.api.v1.predict.ml_inference.predict_with_confidence")
def test_predict_endpoint_does_not_write_telemetry(mock_predict, mock_info, mock_access):
    mock_predict.return_value = ("Active", 0.8)
    mock_info.return_value = {"classes": ["Active", "Resting"], "loao_metrics": {}}
    db = MagicMock()
    payload = PredictRequest(
        accel_x_mean=0,
        accel_x_std=0.1,
        accel_x_min=-0.1,
        accel_x_max=0.1,
        accel_y_mean=0,
        accel_y_std=0.1,
        accel_y_min=-0.1,
        accel_y_max=0.1,
        accel_z_mean=1,
        accel_z_std=0.1,
        accel_z_min=0.9,
        accel_z_max=1.1,
        animal_id=3,
    )

    result = predict_behavior(payload=payload, db=db, current_user=_user())

    assert result.behavior == "Active"
    mock_access.assert_called_once()
    db.query.assert_not_called()
    db.commit.assert_not_called()


@patch("app.api.v1.feedback.require_animal_access")
def test_feedback_rejects_missing_requested_telemetry(mock_access):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = []
    db.query.return_value = query
    payload = PredictionFeedbackCreate(
        animal_id=4,
        telemetry_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
        verdict="correct",
    )

    with pytest.raises(HTTPException) as exc:
        submit_prediction_feedback(payload=payload, db=db, current_user=_user())

    assert exc.value.status_code == 404
    db.commit.assert_not_called()


@patch("app.api.v1.auth.verify_password", return_value=False)
def test_password_change_requires_current_password(mock_verify):
    db = MagicMock()
    user = _user()
    user.password_hash = "hashed"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_me(
                data=UserUpdate(password="new-password", current_password="wrong"),
                current_user=user,
                db=db,
            )
        )

    assert exc.value.status_code == 400
    db.commit.assert_not_called()


def test_owner_account_cannot_be_deleted_while_it_owns_a_farm():
    db = MagicMock()
    user_query = MagicMock()
    user_query.filter.return_value.first.return_value = _user(user_id=7)
    farm_query = MagicMock()
    farm_query.filter.return_value.first.return_value = (11,)
    db.query.side_effect = [user_query, farm_query]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_user(user_id=7, current_user=_user(user_id=1, role="admin"), db=db))

    assert exc.value.status_code == 409
    db.delete.assert_not_called()


def test_last_membership_owner_cannot_be_deleted():
    db = MagicMock()
    user_query = MagicMock()
    user_query.filter.return_value.first.return_value = _user(user_id=7)
    farm_query = MagicMock()
    farm_query.filter.return_value.first.return_value = None
    membership_query = MagicMock()
    membership_query.filter.return_value.all.return_value = [SimpleNamespace(farm_id=12)]
    other_owner_query = MagicMock()
    other_owner_query.filter.return_value.count.return_value = 0
    db.query.side_effect = [
        user_query,
        farm_query,
        membership_query,
        other_owner_query,
    ]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_user(user_id=7, current_user=_user(user_id=1, role="admin"), db=db))

    assert exc.value.status_code == 409
    db.delete.assert_not_called()
