"""
Pydantic schemas for PredictionFeedback & AlertFeedback
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


# ─── Behaviour correction values ──────────────────────────────────────────────

# Stable codes sent by the app since Phase 4 (2026-10); the app shows English labels.
CORRECTION_CODES = ('active', 'resting', 'grazing', 'walking', 'lying', 'running')

# Values stored before Phase 4 (the app sent its displayed text). Still accepted so an
# older app build keeps working; stored rows are not migrated. Mapping to the codes:
# mobile-app/src/utils/feedbackLabels.ts (LEGACY_CORRECTION_CODES).
LEGACY_CORRECTIONS = (
    'Active', 'Resting', 'Grazing (Pâturage)', 'Walking (Marche)', 'Lying (Couché)', 'Running (Course)',
)

ALLOWED_CORRECTIONS = frozenset(CORRECTION_CODES + LEGACY_CORRECTIONS)


# ─── Prediction Feedback ──────────────────────────────────────────────────────

class PredictionFeedbackCreate(BaseModel):
    animal_id          : int
    telemetry_time     : Optional[datetime] = None
    verdict            : Literal['correct', 'incorrect']
    correction         : Optional[str] = Field(
        None, max_length=50,
        description="True behaviour if known: one of " + ", ".join(CORRECTION_CODES)
        + " (values stored before Phase 4 are still accepted)",
    )

    @field_validator('correction')
    @classmethod
    def correction_is_known(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in ALLOWED_CORRECTIONS:
            raise ValueError('correction must be one of: ' + ', '.join(CORRECTION_CODES))
        return value


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


# Aliases kept for backward compatibility
FeedbackCreate = PredictionFeedbackCreate
FeedbackResponse = PredictionFeedbackResponse


# ─── Alert Feedback ───────────────────────────────────────────────────────────

class AlertFeedbackCreate(BaseModel):
    verdict : Literal['confirmed_issue', 'false_alarm'] = Field(
        ...,
        description="'confirmed_issue' if the abnormal behaviour matches a real problem, 'false_alarm' otherwise."
    )
    notes   : Optional[str] = Field(None, max_length=500, description="Optional field observations or remarks")


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
