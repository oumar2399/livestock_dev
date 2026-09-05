"""Read-only, farm-scoped animal timeline."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.access import require_animal_access
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.timeline import TimelineEventType, TimelinePage
from app.services.timeline import build_timeline


router = APIRouter(prefix="/animals", tags=["history"])


@router.get("/{animal_id}/timeline", response_model=TimelinePage)
def get_animal_timeline(
    animal_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    event_type: Optional[list[TimelineEventType]] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_animal_access(current_user, animal_id, "view_animals", db)
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
    try:
        return build_timeline(
            db=db,
            animal_id=animal_id,
            event_types=event_type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            cursor_value=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
