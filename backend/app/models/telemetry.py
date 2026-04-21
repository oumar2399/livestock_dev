"""
Modèle Telemetry - Données capteurs (GPS, activité, température)
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, DECIMAL
from geoalchemy2 import Geography
from datetime import datetime
from app.db.database import Base

class Telemetry(Base):
    __tablename__ = "telemetry"
    
    # Clé primaire composite
    time      = Column(DateTime, primary_key=True, nullable=False)
    animal_id = Column(Integer, ForeignKey("animals.id"), primary_key=True, nullable=False)
    device_id = Column(String, nullable=False, index=True)
    
    # GPS
    location  = Column(Geography(geometry_type='POINT', srid=4326))
    latitude  = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    altitude  = Column(DECIMAL(7, 2))
    speed     = Column(DECIMAL(5, 2))
    satellites = Column(Integer)
    
    # Activité (rétrocompat)
    activity       = Column(DECIMAL(5, 3))
    activity_std   = Column(DECIMAL(5, 3))   # NEW : écart-type magnitude
    activity_state = Column(String(20))

    # ── Accéléromètre 3 axes (NEW) ──────────────────────────
    accel_x_mean = Column(DECIMAL(7, 4))
    accel_x_std  = Column(DECIMAL(7, 4))
    accel_x_min  = Column(DECIMAL(7, 4))
    accel_x_max  = Column(DECIMAL(7, 4))

    accel_y_mean = Column(DECIMAL(7, 4))
    accel_y_std  = Column(DECIMAL(7, 4))
    accel_y_min  = Column(DECIMAL(7, 4))
    accel_y_max  = Column(DECIMAL(7, 4))

    accel_z_mean = Column(DECIMAL(7, 4))
    accel_z_std  = Column(DECIMAL(7, 4))
    accel_z_min  = Column(DECIMAL(7, 4))
    accel_z_max  = Column(DECIMAL(7, 4))

    # Metadata fenêtre (NEW)
    sample_rate    = Column(Integer)   # Hz
    window_samples = Column(Integer)   # Nombre de samples réels
    # ────────────────────────────────────────────────────────

    # Santé
    temperature = Column(DECIMAL(4, 2))
    
    # Système
    battery_level   = Column(Integer)
    signal_strength = Column(Integer)