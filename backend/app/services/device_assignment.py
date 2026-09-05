"""Validation rules for assigning one physical device to one animal."""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.access import require_farm
from app.models.animal import Animal
from app.models.device import Device
from app.models.user import User


def validate_device_assignment(
    db: Session,
    current_user: User,
    farm_id: int,
    device_id: Optional[str],
    *,
    current_animal_id: Optional[int] = None,
) -> Optional[str]:
    """Return a normalized device id after validating ownership and uniqueness."""
    if device_id is None:
        return None

    normalized_id = device_id.strip()
    if not normalized_id:
        return None

    require_farm(current_user, farm_id, "manage_devices", db)

    device = db.query(Device).filter(Device.id == normalized_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {normalized_id} not found",
        )
    if device.farm_id != farm_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Device {normalized_id} must be claimed by farm {farm_id} "
                "before it can be assigned"
            ),
        )

    assignment_query = db.query(Animal).filter(Animal.assigned_device == normalized_id)
    if current_animal_id is not None:
        assignment_query = assignment_query.filter(Animal.id != current_animal_id)
    assigned_animal = assignment_query.first()
    if assigned_animal:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Device {normalized_id} is already assigned to animal "
                f"{assigned_animal.id}"
            ),
        )

    return normalized_id
