"""
Import tous les modèles SQLAlchemy
IMPORTANT : Ce fichier doit importer tous les modèles
pour qu'Alembic (migrations) les détecte
"""
from app.db.database import Base
from app.models.user import User
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.alert import Alert
from app.models.farm import Farm
from app.models.geofence import Geofence
from app.models.feedback import PredictionFeedback, AlertFeedback
from app.models.daily_summary import DailyBehaviorSummary
from app.models.membership import FarmMembership
from app.models.job_run import DailyJobRun

__all__ = [
    "Base",
    "User",
    "Farm",
    "FarmMembership",
    "Animal",
    "Telemetry",
    "Alert",
    "Geofence",
    "PredictionFeedback",
    "AlertFeedback",
    "DailyBehaviorSummary",
    "DailyJobRun",
]
