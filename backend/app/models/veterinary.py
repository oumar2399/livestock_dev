"""
Modèles pour le workflow vétérinaire :
- VeterinaryCase : dossier clinique d'un animal (et alerte optionnellement liée)
- VeterinaryEntry : journal append-only des observations, diagnostics humains et interventions
"""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class VeterinaryCase(Base):
    """
    Table veterinary_cases — Dossier clinique pour un animal.
    Garantit la neutralité clinique : aucun diagnostic automatique.
    """
    __tablename__ = "veterinary_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farm_id = Column(
        Integer,
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    animal_id = Column(
        Integer,
        ForeignKey("animals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    linked_alert_id = Column(
        Integer,
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(255), nullable=False)
    status = Column(String(20), default="provisional", nullable=False)
    opened_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relations
    farm = relationship("Farm")
    animal = relationship("Animal")
    alert = relationship("Alert")
    opener = relationship("User", foreign_keys=[opened_by])
    entries = relationship(
        "VeterinaryEntry",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="VeterinaryEntry.occurred_at.asc()",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('provisional', 'confirmed', 'ruled_out', 'closed')",
            name="ck_veterinary_case_status",
        ),
        Index("idx_vet_cases_farm_status", "farm_id", "status"),
        Index("idx_vet_cases_animal", "animal_id", "created_at"),
    )


class VeterinaryEntry(Base):
    """
    Table veterinary_entries — Entrée de journal clinique (append-only).
    Chaque note ou intervention est rattachée à son auteur praticien humain.
    """
    __tablename__ = "veterinary_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(
        Integer,
        ForeignKey("veterinary_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # observation, intervention, follow_up, assessment, note (written by people);
    # status_change (written by the system on every case status change).
    entry_type = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relations
    case = relationship("VeterinaryCase", back_populates="entries")
    author = relationship("User", foreign_keys=[author_user_id])

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('observation', 'intervention', 'follow_up', 'assessment', 'note', 'status_change')",
            name="ck_veterinary_entry_type",
        ),
        Index("idx_vet_entries_case_occurred", "case_id", "occurred_at"),
    )
