"""
Import tous les modèles SQLAlchemy
IMPORTANT : Ce fichier doit importer tous les modèles
pour qu'Alembic (migrations) les détecte
"""
from app.db.database import Base
from app.models.user import User
from app.models.animal import Animal
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.alert import Alert
from app.models.farm import Farm
from app.models.geofence import Geofence
from app.models.feedback import PredictionFeedback, AlertFeedback
from app.models.daily_summary import DailyBehaviorSummary
from app.models.membership import FarmMembership
from app.models.job_run import DailyJobRun
from app.models.telemetry_quality import DeviceLossPeriod, BehaviorRebuild
from app.models.untimed_telemetry import UntimedTelemetry
from app.models.provenance import AnimalTrackingPeriod
from app.models.farm_creation import FarmCreationRequest
from app.models.notification import (
    PushDevice,
    NotificationPreference,
    NotificationDelivery,
)
from app.models.veterinary import (
    VeterinaryCase,
    VeterinaryEntry,
)

__all__ = [
    "Base",
    "User",
    "Farm",
    "FarmMembership",
    "Animal",
    "Device",
    "Telemetry",
    "UntimedTelemetry",
    "DeviceLossPeriod",
    "BehaviorRebuild",
    "Alert",
    "Geofence",
    "PredictionFeedback",
    "AlertFeedback",
    "DailyBehaviorSummary",
    "DailyJobRun",
    "AnimalTrackingPeriod",
    "FarmCreationRequest",
    "PushDevice",
    "NotificationPreference",
    "NotificationDelivery",
    "VeterinaryCase",
    "VeterinaryEntry",
]
