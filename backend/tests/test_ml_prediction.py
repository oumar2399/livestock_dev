"""Validation tests for the authenticated ML prediction request contract."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.api.v1.predict import PredictRequest


VALID_FEATURES = {
    "accel_x_mean": 0.012,
    "accel_x_std": 0.023,
    "accel_x_min": -0.050,
    "accel_x_max": 0.080,
    "accel_y_mean": -0.003,
    "accel_y_std": 0.019,
    "accel_y_min": -0.040,
    "accel_y_max": 0.060,
    "accel_z_mean": -0.992,
    "accel_z_std": 0.015,
    "accel_z_min": -1.030,
    "accel_z_max": -0.960,
}


def test_predict_request_accepts_numeric_animal_context():
    request = PredictRequest(**VALID_FEATURES, animal_id=7, device_id="M5-001")
    assert request.animal_id == 7


def test_predict_request_rejects_non_numeric_animal_context():
    with pytest.raises(ValidationError):
        PredictRequest(**VALID_FEATURES, animal_id="cow1")
