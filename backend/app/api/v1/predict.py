"""
app/api/v1/predict.py — Real-time behavior inference endpoint
=============================================================
Exposes a POST endpoint that classifies cattle behavior from 12 accelerometer
features sent by the M5Stack firmware v2.0, powered by the ml_inference service.

Auth:
  POST /predict     → JWT required. If animal_id provided, 403 before ML if out of scope.
  GET  /model/info  → JWT required (any authenticated user).
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.services import ml_inference
from app.core.dependencies import get_current_user
from app.core.access import require_animal_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["predict"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    """
    The 12 statistical features computed by the M5Stack firmware v2.0
    over a 50-sample (5-second) window at 10 Hz.

    All values are in g (gravitational acceleration units).
    Physical range for cattle: approximately [-6, 6] g.
    """

    # ── X axis (fore-aft) ────────────────────────────────────────────────────
    accel_x_mean: float = Field(..., ge=-6.0, le=6.0, description="AccX mean (g)")
    accel_x_std:  float = Field(..., ge=0.0,  le=6.0, description="AccX std deviation (g)")
    accel_x_min:  float = Field(..., ge=-6.0, le=6.0, description="AccX minimum (g)")
    accel_x_max:  float = Field(..., ge=-6.0, le=6.0, description="AccX maximum (g)")

    # ── Y axis (lateral) ─────────────────────────────────────────────────────
    accel_y_mean: float = Field(..., ge=-6.0, le=6.0, description="AccY mean (g)")
    accel_y_std:  float = Field(..., ge=0.0,  le=6.0, description="AccY std deviation (g)")
    accel_y_min:  float = Field(..., ge=-6.0, le=6.0, description="AccY minimum (g)")
    accel_y_max:  float = Field(..., ge=-6.0, le=6.0, description="AccY maximum (g)")

    # ── Z axis (vertical — gravity component) ─────────────────────────────────
    accel_z_mean: float = Field(..., ge=-6.0, le=6.0, description="AccZ mean (g)")
    accel_z_std:  float = Field(..., ge=0.0,  le=6.0, description="AccZ std deviation (g)")
    accel_z_min:  float = Field(..., ge=-6.0, le=6.0, description="AccZ minimum (g)")
    accel_z_max:  float = Field(..., ge=-6.0, le=6.0, description="AccZ maximum (g)")

    # ── Optional context ─────────────────────────────────────────────────────
    animal_id:  Optional[int] = Field(None, gt=0, description="Animal ID for access-scoped context")
    device_id:  Optional[str] = Field(None, description="Device ID for traceability")

    @model_validator(mode="after")
    def validate_axis_ranges(self):
        for axis in ("x", "y", "z"):
            mean = getattr(self, f"accel_{axis}_mean")
            minimum = getattr(self, f"accel_{axis}_min")
            maximum = getattr(self, f"accel_{axis}_max")
            if minimum > mean:
                raise ValueError(f"accel_{axis}_min must be <= accel_{axis}_mean")
            if maximum < mean:
                raise ValueError(f"accel_{axis}_max must be >= accel_{axis}_mean")
        return self


class ClassScore(BaseModel):
    """Probability score for one behavior class."""
    label:       str
    probability: float


class PredictResponse(BaseModel):
    """
    Inference result returned for each 5-second window.
    """
    model_config = ConfigDict(protected_namespaces=())

    behavior:   str
    confidence: float
    all_scores: list[ClassScore]
    model_info: dict


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/predict",
    response_model=PredictResponse,
    summary="Classify cattle behavior from 12 accelerometer features",
    description=(
        "Receives the 12 statistical features computed by the M5Stack firmware "
        "and returns the predicted behavior class with confidence score. "
        "This diagnostic endpoint never changes telemetry data. "
        "Requires JWT. If animal_id is provided, 403 before ML if animal is out of scope."
    ),
)
def predict_behavior(
    payload: PredictRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Main inference endpoint — JWT required.
    If animal_id is provided, farm access is verified BEFORE running ML.
    The result is returned only and is never persisted to telemetry.
    """
    # If animal_id is provided, verify access BEFORE inference (§4 predict.py)
    if payload.animal_id:
        require_animal_access(current_user, payload.animal_id, "view_animals", db)

    # Run ML inference
    pred_label, confidence = ml_inference.predict_with_confidence(payload.model_dump())

    if pred_label is None or confidence is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded or features missing. Check that behavior_classifier.pkl exists.",
        )

    info = ml_inference.get_model_info() or {}

    # Build response class scores
    classes = info.get("classes", ["Active", "Resting"])
    all_scores = [
        ClassScore(
            label=c,
            probability=round(confidence if c == pred_label else (1.0 - confidence), 4),
        )
        for c in classes
    ]

    logger.info(
        f"Prediction: {pred_label} ({confidence:.2%}) | "
        f"animal={payload.animal_id or 'unknown'}"
    )

    return PredictResponse(
        behavior   = pred_label,
        confidence = round(confidence, 4),
        all_scores = all_scores,
        model_info = {
            "overall_balanced_accuracy": info.get("loao_metrics", {}).get("mean_accuracy", "N/A"),
            "classes": classes,
        },
    )


@router.get(
    "/model/info",
    summary="Get model metadata and LOAO validation results",
)
def model_info(
    current_user: User = Depends(get_current_user),
):
    """
    Exposes the LOAO validation metrics and model configuration.
    Requires JWT (any authenticated user).
    """
    info = ml_inference.get_model_info()
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded.",
        )

    loao = info.get("loao_metrics", {})
    return {
        "classes":                   info.get("classes"),
        "features":                  info.get("features"),
        "window_samples":            info.get("window_samples", 50),
        "target_freq_hz":            info.get("target_freq", 10),
        "profiles":                  ml_inference.get_profile_status(),
        "overall_balanced_accuracy": loao.get("mean_accuracy"),
        "mean_per_fold_accuracy":    loao.get("mean_accuracy"),
        "std_per_fold_accuracy":     loao.get("std_accuracy"),
        "ci_95_low":                 loao.get("ci_95", [None, None])[0],
        "ci_95_high":                loao.get("ci_95", [None, None])[1],
    }
