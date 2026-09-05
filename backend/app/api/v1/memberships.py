"""
Memberships API — Farm member management
=========================================
POST   /farms/{farm_id}/members       → Invite user (owner/admin)
GET    /farms/{farm_id}/members       → List members
PATCH  /farms/{farm_id}/members/{id}  → Update role/status (owner/admin)
DELETE /farms/{farm_id}/members/{id}  → Soft revoke (owner/admin)
GET    /memberships/mine              → My memberships across all farms
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.schemas.membership import (
    MembershipCreate,
    MembershipUpdate,
    MembershipResponse,
    MembershipListResponse,
)
from app.core.dependencies import get_current_user
from app.core.access import (
    require_farm,
    is_platform_admin,
    effective_permissions,
)
from app.core.role_defaults import FARM_MEMBERSHIP_ROLES
from app.core.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memberships"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_response(m: FarmMembership, db: Session) -> MembershipResponse:
    """Build a MembershipResponse from a FarmMembership ORM instance."""
    perms = effective_permissions(m.user, m.farm_id, db) if m.user else []
    return MembershipResponse(
        id=m.id,
        user_id=m.user_id,
        user_name=m.user.name if m.user else None,
        user_email=m.user.email if m.user else None,
        farm_id=m.farm_id,
        farm_name=m.farm.name if m.farm else None,
        role=m.role,
        status=m.status,
        permissions=perms,
        invited_by_id=m.invited_by_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _check_last_owner(db: Session, farm_id: int, exclude_membership_id: int) -> None:
    """Raise 400 if this would remove the last active owner from the farm."""
    other_owners = (
        db.query(FarmMembership)
        .filter(
            FarmMembership.farm_id == farm_id,
            FarmMembership.role == "owner",
            FarmMembership.status == "active",
            FarmMembership.id != exclude_membership_id,
        )
        .count()
    )
    if other_owners == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the last active owner of this farm",
        )


# ─── POST /farms/{farm_id}/members ───────────────────────────────────────────

@router.post(
    "/farms/{farm_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to a farm",
)
def invite_member(
    farm_id: int,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add a user to a farm. Requires invite_members permission (owner/admin).
    The membership is created with status=active (no pending flow for MVP).
    """
    # Check farm access + invite_members permission
    require_farm(current_user, farm_id, "invite_members", db)

    # Validate role
    if payload.role not in FARM_MEMBERSHIP_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(FARM_MEMBERSHIP_ROLES)}",
        )

    # Find the account, or create it as part of the invitation transaction.
    target_user = db.query(User).filter(User.email == payload.user_email).first()
    if not target_user:
        if not payload.password:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"User with email {payload.user_email} not found; "
                    "a password is required to create the account"
                ),
            )
        target_user = User(
            email=str(payload.user_email),
            password_hash=hash_password(payload.password),
            name=payload.name,
            role="farmer",
        )
        db.add(target_user)
        db.flush()

    # Check for existing membership
    existing = (
        db.query(FarmMembership)
        .filter(
            FarmMembership.user_id == target_user.id,
            FarmMembership.farm_id == farm_id,
        )
        .first()
    )

    if existing:
        if existing.status == "revoked":
            # Re-activate a revoked membership
            existing.role = payload.role
            existing.status = "active"
            existing.invited_by_id = current_user.id
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            logger.info(f"🔄 Membership #{existing.id} re-activated for User #{target_user.id} on Farm #{farm_id}")
            return _build_response(existing, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User {payload.user_email} is already a member of this farm",
            )

    # Create new membership (active)
    membership = FarmMembership(
        user_id=target_user.id,
        farm_id=farm_id,
        role=payload.role,
        status="active",
        invited_by_id=current_user.id,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    logger.info(f"✨ Membership created: User #{target_user.id} as {payload.role} on Farm #{farm_id}")
    return _build_response(membership, db)


# ─── GET /farms/{farm_id}/members ────────────────────────────────────────────

@router.get(
    "/farms/{farm_id}/members",
    response_model=MembershipListResponse,
    summary="List farm members",
)
def list_members(
    farm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all members of a farm. Requires membership on the farm."""
    require_farm(current_user, farm_id, None, db)

    members = (
        db.query(FarmMembership)
        .filter(FarmMembership.farm_id == farm_id)
        .order_by(FarmMembership.created_at.asc())
        .all()
    )

    return MembershipListResponse(
        total=len(members),
        members=[_build_response(m, db) for m in members],
    )


# ─── PATCH /farms/{farm_id}/members/{membership_id} ─────────────────────────

@router.patch(
    "/farms/{farm_id}/members/{membership_id}",
    response_model=MembershipResponse,
    summary="Update a member's role or status",
)
def update_member(
    farm_id: int,
    membership_id: int,
    payload: MembershipUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update role or status of a membership.
    Requires invite_members permission (owner/admin).
    Last owner guard: cannot change the last owner's role or revoke them.
    """
    require_farm(current_user, farm_id, "invite_members", db)

    membership = (
        db.query(FarmMembership)
        .filter(
            FarmMembership.id == membership_id,
            FarmMembership.farm_id == farm_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    # Last owner guard
    if membership.role == "owner" and membership.status == "active":
        # If changing role away from owner, or revoking
        new_role = payload.role or membership.role
        new_status = payload.status or membership.status
        if new_role != "owner" or new_status != "active":
            _check_last_owner(db, farm_id, membership.id)

    if payload.role is not None:
        if payload.role not in FARM_MEMBERSHIP_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {', '.join(FARM_MEMBERSHIP_ROLES)}",
            )
        membership.role = payload.role

    if payload.status is not None:
        membership.status = payload.status

    membership.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(membership)

    logger.info(f"📝 Membership #{membership.id} updated: role={membership.role}, status={membership.status}")
    return _build_response(membership, db)


# ─── DELETE /farms/{farm_id}/members/{membership_id} ─────────────────────────

@router.delete(
    "/farms/{farm_id}/members/{membership_id}",
    status_code=status.HTTP_200_OK,
    response_model=MembershipResponse,
    summary="Revoke a member (soft delete)",
)
def revoke_member(
    farm_id: int,
    membership_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft revoke: sets status='revoked', does NOT delete from DB.
    Last owner guard applies.
    """
    require_farm(current_user, farm_id, "invite_members", db)

    membership = (
        db.query(FarmMembership)
        .filter(
            FarmMembership.id == membership_id,
            FarmMembership.farm_id == farm_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    if membership.status == "revoked":
        raise HTTPException(status_code=400, detail="Membership is already revoked")

    # Last owner guard
    if membership.role == "owner":
        _check_last_owner(db, farm_id, membership.id)

    membership.status = "revoked"
    membership.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(membership)

    logger.info(f"🚫 Membership #{membership.id} revoked for User #{membership.user_id} on Farm #{farm_id}")
    return _build_response(membership, db)


# ─── GET /memberships/mine ───────────────────────────────────────────────────

@router.get(
    "/memberships/mine",
    response_model=List[MembershipResponse],
    summary="My memberships across all farms",
)
def my_memberships(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns all memberships for the current user.
    Used by the mobile app at login to build the farm picker.
    """
    memberships = (
        db.query(FarmMembership)
        .filter(FarmMembership.user_id == current_user.id)
        .order_by(FarmMembership.created_at.asc())
        .all()
    )

    return [_build_response(m, db) for m in memberships]
