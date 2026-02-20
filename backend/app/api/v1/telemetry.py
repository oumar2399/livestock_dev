"""
Routes API Telemetry - Réception et consultation données capteurs
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.database import get_db
from app.models.telemetry import Telemetry
from app.models.animal import Animal
from app.schemas.telemetry import TelemetryCreate, TelemetryResponse, TelemetryLatest

# Créer router (groupe de routes)
router = APIRouter(
    prefix="/telemetry",
    tags=["telemetry"]  # Pour grouper dans doc Swagger
)

# ============================================================
# POST /api/v1/telemetry - Recevoir données M5Stack
# ============================================================

@router.post("/", response_model=TelemetryResponse, status_code=201)
async def receive_telemetry(
    data: TelemetryCreate,
    db: Session = Depends(get_db)
):
    """
    Recevoir données capteur M5Stack
    
    **M5Stack envoie POST à cette route toutes les 10-30 secondes**
    
    Exemple requête:
```json
    {
      "device_id": "M5-001",
      "latitude": 48.856600,
      "longitude": 2.352200,
      "activity": 1.23,
      "battery": 78
    }
```
    
    Processus:
    1. Valide données (Pydantic automatique)
    2. Trouve animal assigné au device
    3. Calcule état activité
    4. Stocke en BDD (TimescaleDB)
    5. Déclenche alertes (TODO)
    
    Returns:
        Télémétrie enregistrée avec ID
    """
    
    # Trouver animal assigné à ce device
    animal = db.query(Animal).filter(
        Animal.assigned_device == data.device_id,
        Animal.status == "active"
    ).first()
    
    if not animal:
        raise HTTPException(
            status_code=404,
            detail=f"No active animal assigned to device {data.device_id}"
        )
    
    # Calculer état activité basé sur accéléromètre
    activity_state = calculate_activity_state(data.activity)
    
    # Créer point géographique PostGIS
    # Format WKT (Well-Known Text): POINT(longitude latitude)
    point_wkt = f'POINT({data.longitude} {data.latitude})'
    
    # Créer entrée télémétrie
    telemetry = Telemetry(
        time=datetime.utcnow(),
        animal_id=animal.id,
        device_id=data.device_id,
        location=point_wkt,
        latitude=data.latitude,
        longitude=data.longitude,
        altitude=data.altitude,
        speed=data.speed,
        satellites=data.satellites,
        activity=data.activity,
        activity_state=activity_state,
        temperature=data.temperature,
        battery_level=data.battery
    )
    
    db.add(telemetry)
    db.commit()
    db.refresh(telemetry)
    
    # TODO: Déclencher vérifications alertes
    # check_alerts(db, animal.id, telemetry)
    
    return telemetry

# ============================================================
# GET /api/v1/telemetry/latest - Dernières positions
# ============================================================

@router.get("/latest", response_model=List[TelemetryLatest])
async def get_latest_telemetry(
    limit: int = Query(10, ge=1, le=100, description="Nombre de résultats"),
    animal_id: Optional[int] = Query(None, description="Filtrer par animal"),
    db: Session = Depends(get_db)
):
    """
    Obtenir dernières positions des animaux
    
    **Utilisé par dashboard web/mobile pour carte temps réel**
    
    Query params:
    - limit: Nombre max résultats (défaut 10, max 100)
    - animal_id: Filtrer pour un animal spécifique (optionnel)
    
    Returns:
        Liste dernières positions avec infos animal
    """
    
    # Sous-requête : dernière mesure par animal
    subquery = db.query(
        Telemetry.animal_id,
        func.max(Telemetry.time).label('last_time')
    ).group_by(Telemetry.animal_id).subquery()
    
    # Requête principale avec jointure
    query = db.query(
        Telemetry,
        Animal.name.label('animal_name')
    ).join(
        Animal, Telemetry.animal_id == Animal.id
    ).join(
        subquery,
        (Telemetry.animal_id == subquery.c.animal_id) &
        (Telemetry.time == subquery.c.last_time)
    )
    
    # Filtre par animal si spécifié
    if animal_id:
        query = query.filter(Telemetry.animal_id == animal_id)
    
    # Limite résultats
    results = query.limit(limit).all()
    
    # Formater réponse
    return [
        TelemetryLatest(
            animal_id=t.animal_id,
            animal_name=animal_name,
            device_id=t.device_id,
            latitude=t.latitude,
            longitude=t.longitude,
            activity=t.activity,
            battery=t.battery_level,
            last_update=t.time
        )
        for t, animal_name in results
    ]

# ============================================================
# GET /api/v1/telemetry/history/{animal_id} - Historique
# ============================================================

@router.get("/history/{animal_id}", response_model=List[TelemetryResponse])
async def get_telemetry_history(
    animal_id: int,
    hours: int = Query(24, ge=1, le=168, description="Nombre d'heures historique (max 7 jours)"),
    db: Session = Depends(get_db)
):
    """
    Obtenir historique télémétrie d'un animal
    
    **Utilisé pour graphiques activité, trace GPS, analytics**
    
    Path params:
    - animal_id: ID de l'animal
    
    Query params:
    - hours: Nombre d'heures historique (défaut 24, max 168 = 7 jours)
    
    Returns:
        Liste mesures télémétrie ordonnées par temps
    """
    
    # Vérifier animal existe
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    
    # Requête télémétrie
    since = datetime.utcnow() - timedelta(hours=hours)
    
    telemetry_records = db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id,
        Telemetry.time >= since
    ).order_by(Telemetry.time.asc()).all()
    
    return telemetry_records

# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def calculate_activity_state(activity: float) -> str:
    """
    Détermine état activité basé sur valeur accéléromètre
    
    Valeurs typiques bovins:
    - Couché/repos : 0.0 - 0.5g
    - Debout calme : 0.5 - 1.2g
    - Marche : 1.2 - 2.5g
    - Course/panic : > 2.5g
    
    Args:
        activity: Valeur accéléromètre en g
    
    Returns:
        État: 'lying', 'standing', 'walking', 'running'
    """
    if activity < 0.5:
        return "lying"
    elif activity < 1.2:
        return "standing"
    elif activity < 2.5:
        return "walking"
    else:
        return "running"