"""
Modèle Farm - Représente une ferme
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, DECIMAL, ForeignKey, Index
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from datetime import datetime
from app.db.database import Base

class Farm(Base):
    """
    Table farms - Fermes/exploitations agricoles
    """
    __tablename__ = "farms"
    
    # Colonnes
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    address = Column(Text)
    location = Column(Geography(geometry_type='POINT', srid=4326))  # PostGIS
    size_hectares = Column(DECIMAL(10, 2))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    owner = relationship("User", back_populates="farms")
    memberships = relationship(
        "FarmMembership",
        back_populates="farm",
        cascade="all, delete-orphan",
    )
    animals = relationship("Animal", back_populates="farm", cascade="all, delete-orphan")
    geofences = relationship("Geofence", back_populates="farm", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_farms_owner", "owner_id"),)
