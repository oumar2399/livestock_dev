"""
Modèle Telemetry - Données capteurs (GPS, activité, température)
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, DECIMAL
from geoalchemy2 import Geography
from datetime import datetime
from app.db.database import Base

class Telemetry(Base):
    """
    Table telemetry (hypertable TimescaleDB) - Données capteurs temps réel
    """
    __tablename__ = "telemetry"
    
    # Clé primaire composite (animal_id + time)
    time = Column(DateTime, primary_key=True, nullable=False)
    animal_id = Column(Integer, ForeignKey("animals.id"), primary_key=True, nullable=False)
    device_id = Column(String, nullable=False, index=True)
    
    # GPS (PostGIS)
    location = Column(Geography(geometry_type='POINT', srid=4326))
    latitude = Column(DECIMAL(10, 8))   # Précision ~1cm
    longitude = Column(DECIMAL(11, 8))
    altitude = Column(DECIMAL(7, 2))    # Mètres
    speed = Column(DECIMAL(5, 2))       # km/h
    satellites = Column(Integer)
    
    # Activité
    activity = Column(DECIMAL(5, 3))    # g (gravité)
    activity_state = Column(String(20)) # walking, standing, lying, running
    
    # Santé
    temperature = Column(DECIMAL(4, 2)) # °C (ex: 38.50)
    
    # Système
    battery_level = Column(Integer)     # 0-100%
    signal_strength = Column(Integer)   # dBm