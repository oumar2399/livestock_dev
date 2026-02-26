"""
Modèle Geofence - Zones géographiques (pâturages, zones interdites)
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from datetime import datetime
from app.db.database import Base

class Geofence(Base):
    """
    Table geofences - Zones géographiques définies
    """
    __tablename__ = "geofences"
    
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    polygon = Column(Geography(geometry_type='POLYGON', srid=4326))  # PostGIS
    type = Column(String(50))  # pasture, danger, building, water
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    farm = relationship("Farm", back_populates="geofences")