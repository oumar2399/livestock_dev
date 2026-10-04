"""
Routes API Notifications :
- Enregistrement / désactivation des tokens push
- Gestion des préférences par utilisateur / ferme
- Déclenchement du dispatcher (admin / job interne / tests)
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.access import require_farm, is_platform_admin
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.notification import PushDevice, NotificationPreference
from app.models.user import User
from app.schemas.notification import (
    PushDeviceCreate,
    PushDeviceResponse,
    NotificationPreferenceUpdate,
    NotificationPreferenceResponse,
    DispatchResult,
)
from app.services.notification_service import (
    dispatch_pending_notifications,
    get_user_preference,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/devices", response_model=PushDeviceResponse)
def register_device(
    payload: PushDeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enregistre ou réactive un token push pour l'utilisateur connecté.
    Si le token appartenait à un autre compte, il est réassigné au compte courant.
    """
    device = (
        db.query(PushDevice)
        .filter(PushDevice.push_token == payload.push_token)
        .first()
    )

    now = datetime.utcnow()
    if device:
        device.user_id = current_user.id
        device.provider = payload.provider
        device.platform = payload.platform or device.platform
        device.active = True
        device.last_seen_at = now
        device.updated_at = now
    else:
        device = PushDevice(
            user_id=current_user.id,
            provider=payload.provider,
            push_token=payload.push_token,
            platform=payload.platform,
            active=True,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )
        db.add(device)

    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{push_token}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_device(
    push_token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Désactive un token push (appelé typiquement au logout).
    N'affecte que le token s'il appartient à l'utilisateur connecté.
    """
    device = (
        db.query(PushDevice)
        .filter(
            PushDevice.push_token == push_token,
            PushDevice.user_id == current_user.id,
        )
        .first()
    )
    if device:
        device.active = False
        device.updated_at = datetime.utcnow()
        db.commit()
    return None


@router.get("/preferences", response_model=List[NotificationPreferenceResponse])
def get_preferences(
    farm_id: Optional[int] = Query(None, description="Filtrer par ferme optionnelle"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupère les préférences de notification du compte connecté.
    """
    query = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id
    )
    if farm_id is not None:
        query = query.filter(NotificationPreference.farm_id == farm_id)

    prefs = query.all()
    # Si aucune préférence explicite n'existe, on renvoie une valeur par défaut informative
    if not prefs and farm_id is None:
        return [
            NotificationPreferenceResponse(
                id=0,
                user_id=current_user.id,
                farm_id=None,
                categories=["geofence", "health", "battery", "offline"],
                min_severity="info",
                enabled=True,
                updated_at=datetime.utcnow(),
            )
        ]
    return prefs


@router.put("/preferences", response_model=NotificationPreferenceResponse)
def update_preferences(
    payload: NotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Crée ou met à jour les préférences de notification pour l'utilisateur.
    Si farm_id est renseigné, vérifie d'abord l'accès à la ferme.
    """
    if payload.farm_id is not None:
        require_farm(current_user, payload.farm_id, None, db)

    query = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id
    )
    if payload.farm_id is not None:
        query = query.filter(NotificationPreference.farm_id == payload.farm_id)
    else:
        query = query.filter(NotificationPreference.farm_id.is_(None))

    pref = query.first()
    now = datetime.utcnow()

    if pref:
        if payload.categories is not None:
            pref.categories = payload.categories
        if payload.min_severity is not None:
            pref.min_severity = payload.min_severity
        if payload.enabled is not None:
            pref.enabled = payload.enabled
        pref.updated_at = now
    else:
        pref = NotificationPreference(
            user_id=current_user.id,
            farm_id=payload.farm_id,
            categories=payload.categories if payload.categories is not None else ["geofence", "health", "battery", "offline"],
            min_severity=payload.min_severity or "info",
            enabled=payload.enabled if payload.enabled is not None else True,
            created_at=now,
            updated_at=now,
        )
        db.add(pref)

    db.commit()
    db.refresh(pref)
    return pref


@router.post("/dispatch", response_model=DispatchResult)
def trigger_dispatch(
    batch_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Déclenche manuellement un lot de dispatch des notifications en attente.
    Platform administrators only: the dispatch covers every farm.
    """
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform administrators can trigger the global dispatch",
        )

    return dispatch_pending_notifications(db=db, batch_size=batch_size)
