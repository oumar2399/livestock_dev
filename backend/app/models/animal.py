"""
Modèle Animal - Représente un animal (vache, mouton, etc.)
"""
from sqlalchemy import Column, Integer, String, Text, CHAR, Date, DateTime, ForeignKey, DECIMAL, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class Animal(Base):
    """
    Table animals - Animaux suivis
    """
    __tablename__ = "animals"
    
    # Colonnes
    id = Column(Integer, primary_key=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    official_id = Column(String(50), unique=True)  # Numéro boucle oreille
    species = Column(String(50), default="bovine")
    breed = Column(String(100))
    sex = Column(CHAR(1))  # 'M' ou 'F'
    birth_date = Column(Date)
    weight = Column(DECIMAL(6, 2))  # 9999.99 kg max
    photo_url = Column(Text)
    assigned_device = Column(String(50))  # ID M5Stack
    status = Column(String(50), default="active")  # active, sick, sold, deceased
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    farm = relationship("Farm", back_populates="animals")
    alerts = relationship("Alert", back_populates="animal", cascade="all, delete-orphan")
    # Si animal supprimé → ses alertes aussi

    __table_args__ = (
        Index("idx_animals_farm", "farm_id"),
        Index("uq_animals_assigned_device", "assigned_device", unique=True),
        Index("idx_animals_status", "status"),
    )
