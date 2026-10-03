"""Durable, user-scoped farm creation receipts."""

from sqlalchemy import Column, ForeignKey, Integer, String
from app.db.database import Base


class FarmCreationRequest(Base):
    __tablename__ = "farm_creation_requests"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    request_id = Column(String(64), primary_key=True)
    fingerprint = Column(String(64), nullable=False)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="SET NULL"), nullable=True)
