"""
Modèle User - Représente un utilisateur (fermier, propriétaire, vétérinaire)
"""
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class User(Base):
    """
    Table users - Utilisateurs du système
    """
    __tablename__ = "users"
    
    # Colonnes
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255))
    role = Column(String(50), default="farmer")  # farmer, owner, vet, admin
    phone = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relations (foreign keys inverses)
    farms = relationship("Farm", back_populates="owner", cascade="all, delete-orphan")
    memberships = relationship(
        "FarmMembership",
        foreign_keys="FarmMembership.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
    )
