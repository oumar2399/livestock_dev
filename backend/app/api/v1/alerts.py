"""
Routes API Alerts - Gestion alertes système
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional

from app.db.database import get_db
from app.models.alert import Alert
from app.models.animal import Animal
from app.schemas.alert import (
    AlertResponse,
    AlertList,
    AlertUpdate,
    AlertSeverity
)

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"]
)

# ============================================================
# GET /api/v1/alerts - Liste alertes
# ============================================================

@router.get("/", response_model=AlertList)
async def list_alerts(
    resolved: Optional[bool] = Query(None, description="Filtrer résolues/non résolues"),
    severity: Optional[AlertSeverity] = Query(None, description="Filtrer par gravité"),
    animal_id: Optional[int] = Query(None, description="Filtrer par animal"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Liste alertes avec filtres
    
    **Dashboard affiche alertes actives en priorité**
    
    Query params:
    - resolved: true (résolues), false (actives), null (toutes)
    - severity: info, warning, critical
    - animal_id: Filtrer pour un animal
    - limit: Nombre max résultats
    
    Returns:
        Liste alertes + nombre non résolues
    """
    
    # Base query avec jointure animal
    query = db.query(
        Alert,
        Animal.name.label('animal_name')
    ).join(Animal, Alert.animal_id == Animal.id)
    
    # Filtres
    if resolved is not None:
        if resolved:
            query = query.filter(Alert.resolved_at.isnot(None))
        else:
            query = query.filter(Alert.resolved_at.is_(None))
    
    if severity:
        query = query.filter(Alert.severity == severity.value)
    
    if animal_id:
        query = query.filter(Alert.animal_id == animal_id)
    
    # Ordre : non résolues d'abord, puis par date desc
    query = query.order_by(
        Alert.resolved_at.is_(None).desc(),
        Alert.triggered_at.desc()
    )
    
    results = query.limit(limit).all()
    
    # Compter non résolues
    unresolved_count = db.query(Alert).filter(
        Alert.resolved_at.is_(None)
    ).count()
    
    # Formater réponse
    alerts = []
    for alert, animal_name in results:
        alert_dict = alert.__dict__.copy()
        alert_dict['animal_name'] = animal_name
        alerts.append(AlertResponse(**alert_dict))
    
    return AlertList(
        total=len(alerts),
        alerts=alerts,
        unresolved_count=unresolved_count
    )

# ============================================================
# PATCH /api/v1/alerts/{alert_id} - Acquitter/Résoudre
# ============================================================

@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    update_data: AlertUpdate,
    db: Session = Depends(get_db)
):
    """
    Acquitter ou résoudre une alerte
    
    **Fermier clique "J'ai vu" ou "Résolu"**
    
    Body JSON:
```json
    {
      "acknowledged_at": "2026-02-20T10:30:00Z",
      "acknowledged_by": 1,
      "resolved_at": "2026-02-20T14:00:00Z"
    }
```
    
    Returns:
        Alerte mise à jour
    """
    
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Mise à jour champs fournis
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(alert, field, value)
    
    db.commit()
    db.refresh(alert)
    
    # Ajouter nom animal
    animal = db.query(Animal).filter(Animal.id == alert.animal_id).first()
    alert.animal_name = animal.name if animal else None
    
    return alert