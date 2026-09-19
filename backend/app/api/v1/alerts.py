"""
Routes API Alerts - Farm-scoped alert management
Filters: active/resolved, severity (info/warning/critical)
Actions: Acknowledge, Resolve
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional

from app.db.database import get_db
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.user import User
from app.schemas.alert import (
    AlertResponse,
    AlertList,
    AlertUpdate,
    AlertSeverity
)
from app.core.dependencies import get_current_user
from app.core.access import require_farm, resolve_farm_scope

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"]
)

# ============================================================
# GET /api/v1/alerts - Liste alertes (farm-scoped)
# ============================================================

@router.get("/", response_model=AlertList)
def list_alerts(
    farm_id: Optional[int] = Query(None, description="Filter by farm"),
    resolved: Optional[bool] = Query(None, description="Filter resolved/unresolved"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter by severity"),
    animal_id: Optional[int] = Query(None, description="Filter by animal"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List alerts — only for animals in the user's accessible farms.
    """
    accessible = resolve_farm_scope(current_user, db, farm_id)

    # Base query with animal join — scoped to accessible farms
    query = db.query(
        Alert,
        Animal.name.label('animal_name')
    ).join(Animal, Alert.animal_id == Animal.id).filter(
        Animal.farm_id.in_(accessible)
    )

    # Filters
    if resolved is not None:
        if resolved:
            query = query.filter(Alert.resolved_at.isnot(None))
        else:
            query = query.filter(Alert.resolved_at.is_(None))

    if severity:
        query = query.filter(Alert.severity == severity.value)

    if animal_id:
        query = query.filter(Alert.animal_id == animal_id)

    # Order: unresolved first, then by date desc
    query = query.order_by(
        Alert.resolved_at.is_(None).desc(),
        Alert.triggered_at.desc()
    )

    results = query.limit(limit).all()

    # Count unresolved — scoped to accessible farms
    unresolved_count = db.query(Alert).join(
        Animal, Alert.animal_id == Animal.id
    ).filter(
        Animal.farm_id.in_(accessible),
        Alert.resolved_at.is_(None),
    ).count()

    # Format response
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
# PATCH /api/v1/alerts/{alert_id} - Acknowledge/Resolve
# ============================================================

@router.patch("/{alert_id}", response_model=AlertResponse)
def update_alert(
    alert_id: int,
    update_data: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Acknowledge or resolve an alert.
    Requires membership on the alert's animal's farm.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Farm access check via the animal
    animal = db.query(Animal).filter(Animal.id == alert.animal_id).first()
    if animal:
        require_farm(current_user, animal.farm_id, None, db)

    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(alert, field, value)

    db.commit()
    db.refresh(alert)

    # Attach animal name
    alert.animal_name = animal.name if animal else None

    return alert
