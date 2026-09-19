"""
Feedback API — Farm-scoped feedback on ML predictions & anomaly alerts
======================================================================
  - POST /api/v1/feedback/predictions     → Prediction feedback (farm-scoped)
  - POST /api/v1/feedback/alerts/{alert_id} → Alert feedback (farm-scoped)
  - GET  /api/v1/feedback/stats           → Stats scoped to user's farms
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.user import User
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.alert import Alert
from app.models.feedback import PredictionFeedback, AlertFeedback
from app.schemas.feedback import (
    PredictionFeedbackCreate,
    PredictionFeedbackResponse,
    AlertFeedbackCreate,
    AlertFeedbackResponse,
    FeedbackStatsResponse,
)
from app.core.dependencies import get_current_user
from app.core.access import (
    require_animal_access,
    require_farm,
    get_accessible_farm_ids,
)
from app.core.timezone import ensure_utc, to_utc_naive
from app.services.telemetry_quality import eligible_clause, feedback_eligible_clause

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ============================================================
# POST /api/v1/feedback/predictions
# ============================================================

@router.post(
    "/predictions",
    response_model=PredictionFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback on an ML behavioral prediction",
)
def submit_prediction_feedback(
    payload: PredictionFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Confirm ('correct') or reject ('incorrect') an ML prediction.
    Requires give_feedback permission on the animal's farm.
    """
    # Farm access check
    animal = require_animal_access(current_user, payload.animal_id, "give_feedback", db)

    # Find matching telemetry
    query = db.query(Telemetry).filter(Telemetry.animal_id == payload.animal_id)
    if payload.telemetry_time:
        target_time = ensure_utc(payload.telemetry_time)
        candidates = query.filter(
            Telemetry.time >= target_time - timedelta(seconds=5),
            Telemetry.time <= target_time + timedelta(seconds=5),
        ).all()
        telemetry = min(
            candidates,
            key=lambda item: abs((ensure_utc(item.time) - target_time).total_seconds()),
            default=None,
        )
        if telemetry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No telemetry found within 5 seconds of the requested timestamp",
            )
    else:
        telemetry = query.order_by(Telemetry.time.desc()).first()

    if telemetry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No telemetry found for animal {payload.animal_id}",
        )

    if not db.query(Telemetry).filter(Telemetry.animal_id == telemetry.animal_id,
                                     Telemetry.time == telemetry.time, eligible_clause()).first():
        raise HTTPException(409, "This measurement is excluded from animal behavior")
    predicted_behavior = telemetry.predicted_behavior
    confidence = telemetry.behavior_confidence
    telemetry_time = to_utc_naive(telemetry.time)

    # Upsert by (user_id, animal_id, telemetry_time)
    existing_fb = (
        db.query(PredictionFeedback)
        .filter(
            PredictionFeedback.user_id == current_user.id,
            PredictionFeedback.animal_id == payload.animal_id,
            PredictionFeedback.telemetry_time == telemetry_time,
        )
        .first()
    )

    if existing_fb:
        existing_fb.verdict = payload.verdict
        existing_fb.correction = payload.correction
        existing_fb.predicted_behavior = predicted_behavior
        existing_fb.confidence = confidence
        existing_fb.created_at = datetime.utcnow()
        feedback = existing_fb
        logger.info(f"🔄 PredictionFeedback updated #{feedback.id} by User #{current_user.id}")
    else:
        feedback = PredictionFeedback(
            animal_id=payload.animal_id,
            user_id=current_user.id,
            telemetry_time=telemetry_time,
            predicted_behavior=predicted_behavior,
            confidence=confidence,
            verdict=payload.verdict,
            correction=payload.correction,
            created_at=datetime.utcnow(),
        )
        db.add(feedback)
        logger.info(f"✨ PredictionFeedback created by User #{current_user.id} for Animal #{payload.animal_id}")

    db.commit()
    db.refresh(feedback)
    return feedback


# ============================================================
# POST /api/v1/feedback/alerts/{alert_id}
# ============================================================

@router.post(
    "/alerts/{alert_id}",
    response_model=AlertFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback on a behavioral deviation alert",
)
def submit_alert_feedback(
    alert_id: int,
    payload: AlertFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Annotate a deviation alert:
      - 'confirmed_issue': the anomaly matches a real problem.
      - 'false_alarm': benign/explainable behavior.
    Requires give_feedback permission on the alert's animal's farm.
    """
    # Get alert
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert #{alert_id} not found",
        )

    # Farm access check via the animal
    animal = db.query(Animal).filter(Animal.id == alert.animal_id).first()
    if not animal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Animal #{alert.animal_id} not found for alert #{alert_id}",
        )
    require_farm(current_user, animal.farm_id, "give_feedback", db)

    # Extract z_score from metadata if present
    z_score = None
    if alert.alert_metadata and isinstance(alert.alert_metadata, dict):
        z_score = alert.alert_metadata.get("z_score")

    # Upsert by (user_id, alert_id)
    existing_fb = (
        db.query(AlertFeedback)
        .filter(
            AlertFeedback.user_id == current_user.id,
            AlertFeedback.alert_id == alert_id,
        )
        .first()
    )

    if existing_fb:
        existing_fb.verdict = payload.verdict
        existing_fb.notes = payload.notes
        existing_fb.alert_type = alert.type
        existing_fb.z_score = z_score
        existing_fb.created_at = datetime.utcnow()
        feedback = existing_fb
        logger.info(f"🔄 AlertFeedback updated #{feedback.id} by User #{current_user.id} for Alert #{alert_id}")
    else:
        feedback = AlertFeedback(
            alert_id=alert_id,
            animal_id=alert.animal_id,
            user_id=current_user.id,
            alert_type=alert.type,
            z_score=z_score,
            verdict=payload.verdict,
            notes=payload.notes,
            created_at=datetime.utcnow(),
        )
        db.add(feedback)
        logger.info(f"✨ AlertFeedback created by User #{current_user.id} for Alert #{alert_id}")

    db.commit()
    db.refresh(feedback)
    return feedback


# ============================================================
# GET /api/v1/feedback/stats (farm-scoped)
# ============================================================

@router.get(
    "/stats",
    response_model=FeedbackStatsResponse,
    summary="Feedback statistics scoped to user's accessible farms",
)
def get_feedback_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns ML prediction accuracy (% correct) and alert confirmation rate,
    scoped to the user's accessible farms.
    """
    accessible = get_accessible_farm_ids(current_user, db)

    # Prediction stats — scoped to animals in accessible farms
    pred_base = (
        db.query(PredictionFeedback)
        .join(Animal, PredictionFeedback.animal_id == Animal.id)
        .filter(Animal.farm_id.in_(accessible), feedback_eligible_clause())
    )
    total_pred = pred_base.count()
    correct_pred = pred_base.filter(PredictionFeedback.verdict == "correct").count()
    pred_accuracy = (correct_pred / total_pred * 100.0) if total_pred > 0 else 0.0

    # Alert stats — scoped to animals in accessible farms
    alert_base = (
        db.query(AlertFeedback)
        .join(Animal, AlertFeedback.animal_id == Animal.id)
        .join(Alert, Alert.id == AlertFeedback.alert_id)
        .filter(Alert.alert_metadata["quality_invalidated_at"].astext.is_(None))
        .filter(Animal.farm_id.in_(accessible))
    )
    total_alert = alert_base.count()
    confirmed_alert = alert_base.filter(AlertFeedback.verdict == "confirmed_issue").count()
    alert_accuracy = (confirmed_alert / total_alert * 100.0) if total_alert > 0 else 0.0

    return FeedbackStatsResponse(
        total_prediction_feedbacks=total_pred,
        prediction_accuracy_pct=round(pred_accuracy, 2),
        total_alert_feedbacks=total_alert,
        confirmed_alert_pct=round(alert_accuracy, 2),
    )
