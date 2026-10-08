"""
Farm-scoped access checks (memberships + role_defaults).
Used by FastAPI dependencies and route handlers.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.role_defaults import role_has_permission
from app.models.animal import Animal
from app.models.device import Device
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.user import User


def is_platform_admin(user: User) -> bool:
    return user.role == "admin"


def get_accessible_farm_ids(user: User, db: Session) -> list[int]:
    if is_platform_admin(user):
        return [row[0] for row in db.query(Farm.id).all()]
    rows = (
        db.query(FarmMembership.farm_id)
        .filter(
            FarmMembership.user_id == user.id,
            FarmMembership.status == "active",
        )
        .all()
    )
    return [row[0] for row in rows]


def get_active_membership(
    user: User, farm_id: int, db: Session
) -> Optional[FarmMembership]:
    if is_platform_admin(user):
        return None
    return (
        db.query(FarmMembership)
        .filter(
            FarmMembership.user_id == user.id,
            FarmMembership.farm_id == farm_id,
            FarmMembership.status == "active",
        )
        .first()
    )


def has_permission(user: User, farm_id: int, permission: str, db: Session) -> bool:
    if is_platform_admin(user):
        return True
    membership = get_active_membership(user, farm_id, db)
    if not membership:
        return False
    return role_has_permission(membership.role, permission)


def require_farm(
    user: User,
    farm_id: int,
    permission: Optional[str],
    db: Session,
) -> Farm:
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Farm not found",
        )
    if is_platform_admin(user):
        return farm
    membership = get_active_membership(user, farm_id, db)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this farm denied",
        )
    if permission and not role_has_permission(membership.role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission}",
        )
    return farm


def require_animal_access(
    user: User,
    animal_id: int,
    permission: str,
    db: Session,
) -> Animal:
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Animal not found",
        )
    require_farm(user, animal.farm_id, permission, db)
    return animal


def require_device_farm_patch(
    user: User,
    device: Device,
    new_farm_id: Optional[int],
    db: Session,
) -> None:
    """
    Permission rules for PATCH /devices/{id} when farm_id may change (§10b).
    """
    if is_platform_admin(user):
        if new_farm_id is not None:
            require_farm(user, new_farm_id, None, db)
        return

    current = device.farm_id

    if current is None:
        if new_farm_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        require_farm(user, new_farm_id, "manage_devices", db)
        return

    if new_farm_id is None:
        require_farm(user, current, "manage_devices", db)
        return

    if new_farm_id == current:
        require_farm(user, current, "manage_devices", db)
        return

    require_farm(user, current, "manage_devices", db)
    require_farm(user, new_farm_id, "manage_devices", db)


def resolve_farm_scope(
    user: User,
    db: Session,
    farm_id: Optional[int],
) -> list[int]:
    """
    Farm ids allowed for list filters.
    If farm_id query is set, it must be in the user's accessible set.
    """
    accessible = get_accessible_farm_ids(user, db)
    if farm_id is not None:
        if farm_id not in accessible:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this farm denied",
            )
        return [farm_id]
    return accessible


def assert_device_visible(user: User, device: Device, db: Session) -> None:
    if device.farm_id is None:
        if not is_platform_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        return
    accessible = get_accessible_farm_ids(user, db)
    if device.farm_id not in accessible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


def effective_permissions(user: User, farm_id: int, db: Session) -> list[str]:
    from app.core.role_defaults import ROLE_DEFAULT_PERMISSIONS, permissions_for_role

    if is_platform_admin(user):
        # The admin passes every check (has_permission), so the app must show every
        # action too: the union of all farm roles, in a stable order.
        return sorted({perm for perms in ROLE_DEFAULT_PERMISSIONS.values() for perm in perms})
    membership = get_active_membership(user, farm_id, db)
    if not membership:
        return []
    return permissions_for_role(membership.role)
