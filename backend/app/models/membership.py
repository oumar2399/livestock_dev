"""
FarmMembership — per-farm role and access for a user.
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base


class FarmMembership(Base):
    __tablename__ = "farm_memberships"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farm_id = Column(
        Integer,
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    invited_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="memberships",
    )
    farm = relationship("Farm", back_populates="memberships")
    invited_by = relationship(
        "User",
        foreign_keys=[invited_by_id],
    )

    __table_args__ = (
        UniqueConstraint("user_id", "farm_id", name="uq_user_farm_membership"),
        CheckConstraint(
            "role IN ('owner', 'farmer', 'vet')",
            name="ck_farm_membership_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'revoked')",
            name="ck_farm_membership_status",
        ),
    )
