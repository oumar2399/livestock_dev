"""
Modèle User - Représente un utilisateur (fermier, propriétaire, vétérinaire)
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class User(Base):
    """
    Table users - Utilisateurs du système
    """
    __tablename__ = "users"
    
    # Colonnes
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String)
    role = Column(String, default="farmer")  # farmer, owner, vet, admin
    phone = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relations (foreign keys inverses)
    farms = relationship("Farm", back_populates="owner", cascade="all, delete-orphan")
    # Si user supprimé → ses farms aussi (cascade)