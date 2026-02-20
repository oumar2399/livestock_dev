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

# À ajouter plus tard :
# from app.models.farm import Farm
# from app.models.geofence import Geofence
# from app.models.device import Device

__all__ = [
    "Base",
    "User",
    "Farm",
    "Animal", 
    "Telemetry",
    "Alert"
]