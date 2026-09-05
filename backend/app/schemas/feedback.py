"""
Schémas Pydantic pour PredictionFeedback & AlertFeedback
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Literal
from datetime import datetime


# ─── Prediction Feedback ──────────────────────────────────────────────────────

class PredictionFeedbackCreate(BaseModel):
    animal_id          : int
    telemetry_time     : Optional[datetime] = None
    verdict            : Literal['correct', 'incorrect']
    correction         : Optional[str] = Field(None, max_length=50, description="Vrai comportement si connu ('Active' | 'Resting')")


class PredictionFeedbackResponse(BaseModel):
    id                 : int
    animal_id          : int
    user_id            : int
    telemetry_time     : Optional[datetime]
    predicted_behavior : Optional[str]
    confidence         : Optional[float]
    verdict            : str
    correction         : Optional[str]
    created_at         : datetime

    model_config = ConfigDict(from_attributes=True)


# Alias pour rétrocompatibilité
FeedbackCreate = PredictionFeedbackCreate
FeedbackResponse = PredictionFeedbackResponse


# ─── Alert Feedback ───────────────────────────────────────────────────────────

class AlertFeedbackCreate(BaseModel):
    verdict : Literal['confirmed_issue', 'false_alarm'] = Field(
        ...,
        description="'confirmed_issue' si le comportement anormal correspond à un vrai problème, 'false_alarm' sinon."
    )
    notes   : Optional[str] = Field(None, max_length=500, description="Observations ou remarques terrain optionnelles")


class AlertFeedbackResponse(BaseModel):
    id         : int
    alert_id   : int
    animal_id  : int
    user_id    : int
    alert_type : str
    z_score    : Optional[float]
    verdict    : str
    notes      : Optional[str]
    created_at : datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Feedback Stats Summary ───────────────────────────────────────────────────

class FeedbackStatsResponse(BaseModel):
    total_prediction_feedbacks : int
    prediction_accuracy_pct    : float
    total_alert_feedbacks      : int
    confirmed_alert_pct        : float
