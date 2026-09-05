"""
Pydantic schemas for FarmMembership CRUD.
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import datetime


# ─── Create ──────────────────────────────────────────────────────────────────

class MembershipCreate(BaseModel):
    """Invite a user to a farm."""
    user_email: EmailStr = Field(..., description="Email of the user to invite")
    name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(
        None,
        min_length=6,
        description="Required only when the account does not exist yet",
    )
    role: str = Field(
        ...,
        pattern="^(owner|farmer|vet)$",
        description="Farm role: owner | farmer | vet",
    )


# ─── Update ──────────────────────────────────────────────────────────────────

class MembershipUpdate(BaseModel):
    """Update role or status of a membership."""
    role: Optional[str] = Field(
        None,
        pattern="^(owner|farmer|vet)$",
        description="New role",
    )
    status: Optional[str] = Field(
        None,
        pattern="^(pending|active|revoked)$",
        description="New status",
    )


# ─── Response ────────────────────────────────────────────────────────────────

class MembershipResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    farm_id: int
    farm_name: Optional[str] = None
    role: str
    status: str
    permissions: list[str] = Field(default_factory=list)
    invited_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipListResponse(BaseModel):
    total: int
    members: list[MembershipResponse]
