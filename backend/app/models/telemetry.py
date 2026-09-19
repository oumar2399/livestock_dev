"""
Modèle Telemetry - Données capteurs (GPS, activité, température)
"""
from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, Float, Index, desc, Boolean
from geoalchemy2 import Geography
from app.db.database import Base

class Telemetry(Base):
    __tablename__ = "telemetry"
    
    # Clé primaire composite
    animal_id = Column(Integer, primary_key=True, nullable=False)
    time      = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    device_id = Column(String(50), nullable=False)
    received_at = Column(DateTime(timezone=True))
    time_source = Column(String(24))
    protocol_version = Column(Integer)
    behavior_eligible = Column(Boolean)
    exclusion_reason = Column(String(50))
    
    # GPS
    location  = Column(Geography(geometry_type='POINT', srid=4326))
    latitude  = Column(Float)
    longitude = Column(Float)
    altitude  = Column(DECIMAL(7, 2))
    speed     = Column(DECIMAL(5, 2))
    satellites = Column(Integer)
    
    # Activité (rétrocompat)
    activity            = Column(DECIMAL(5, 3))
    activity_std        = Column(DECIMAL(5, 3))   # NEW : écart-type magnitude
    activity_state      = Column(String(20))
    predicted_behavior  = Column(String)
    behavior_confidence = Column(Float)

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

    __table_args__ = (
        Index("idx_telemetry_device", "device_id", desc("time")),
        Index("telemetry_time_idx", desc("time")),
    )
