"""
Modèle Animal - Représente un animal (vache, mouton, etc.)
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class Animal(Base):
    """
    Table animals - Animaux suivis
    """
    __tablename__ = "animals"
    
    # Colonnes
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    official_id = Column(String, unique=True)  # Numéro boucle oreille
    species = Column(String, default="bovine")
    breed = Column(String)
    sex = Column(String(1))  # 'M' ou 'F'
    birth_date = Column(Date)
    weight = Column(DECIMAL(6, 2))  # 9999.99 kg max
    photo_url = Column(String)
    assigned_device = Column(String, index=True)  # ID M5Stack
    status = Column(String, default="active")  # active, sick, sold, deceased
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    farm = relationship("Farm", back_populates="animals")
    alerts = relationship("Alert", back_populates="animal", cascade="all, delete-orphan")
    # Si animal supprimé → ses alertes aussi