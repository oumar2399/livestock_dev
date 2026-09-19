"""Archive of undated windows, deliberately separate from animal telemetry."""

import sqlalchemy as sa
from app.db.database import Base


class UntimedTelemetry(Base):
    __tablename__ = "untimed_telemetry"

    id = sa.Column(sa.BigInteger(), primary_key=True)
    device_id = sa.Column(sa.String(50), sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    transport_id_at_reception = sa.Column(sa.Integer(), nullable=False)
    session_id = sa.Column(sa.BigInteger(), nullable=False)
    sequence = sa.Column(sa.BigInteger(), nullable=False)
    window_end_elapsed_ms = sa.Column(sa.BigInteger(), nullable=False)
    protocol_version = sa.Column(sa.Integer(), nullable=False)
    measured_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    received_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    time_reliable = sa.Column(sa.Boolean(), nullable=False)
    time_uncertainty_reason = sa.Column(sa.String(32), nullable=False)
    raw_packet = sa.Column(sa.LargeBinary(), nullable=False)
    farm_id_at_reception = sa.Column(sa.Integer(), nullable=True)
    animal_id_at_reception = sa.Column(sa.Integer(), nullable=True)
    device_status_at_reception = sa.Column(sa.String(50), nullable=False)
    attribution_status = sa.Column(sa.String(32), nullable=False)
    latitude = sa.Column(sa.Float(), nullable=True)
    longitude = sa.Column(sa.Float(), nullable=True)
    satellites = sa.Column(sa.Integer(), nullable=False)
    battery_level = sa.Column(sa.Integer(), nullable=False)
    accel_x_mean = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_x_std = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_x_min = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_x_max = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_y_mean = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_y_std = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_y_min = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_y_max = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_z_mean = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_z_std = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_z_min = sa.Column(sa.Numeric(7, 4), nullable=False)
    accel_z_max = sa.Column(sa.Numeric(7, 4), nullable=False)
    activity = sa.Column(sa.Numeric(5, 3), nullable=False)
    activity_std = sa.Column(sa.Numeric(5, 3), nullable=False)
    sample_rate = sa.Column(sa.Integer(), nullable=False)
    window_samples = sa.Column(sa.Integer(), nullable=False)
    classification_status = sa.Column(sa.String(32), nullable=False)
    exclusion_reason = sa.Column(sa.String(50), nullable=True)
    predicted_behavior = sa.Column(sa.String(), nullable=True)
    behavior_confidence = sa.Column(sa.Float(), nullable=True)
    model_sha256 = sa.Column(sa.String(64), nullable=True)
    classified_at = sa.Column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("device_id", "session_id", "sequence", name="uq_untimed_identity"),
        sa.Index("idx_untimed_received", "received_at", "id"),
        sa.Index("idx_untimed_device_received", "device_id", "received_at", "id"),
        sa.CheckConstraint("session_id BETWEEN 1 AND 9223372036854775807", name="ck_untimed_session"),
        sa.CheckConstraint("sequence BETWEEN 0 AND 4294967295", name="ck_untimed_sequence"),
        sa.CheckConstraint("window_end_elapsed_ms BETWEEN 15000 AND 4294967295", name="ck_untimed_elapsed"),
        sa.CheckConstraint("protocol_version = 3 AND sample_rate = 10 AND window_samples = 150", name="ck_untimed_protocol"),
        sa.CheckConstraint("time_reliable = false AND measured_at IS NULL", name="ck_untimed_time"),
        sa.CheckConstraint("time_uncertainty_reason IN ('never_synchronized','holdover_expired','clock_discontinuity','non_monotonic_utc')", name="ck_untimed_reason"),
        sa.CheckConstraint("octet_length(raw_packet) = 58", name="ck_untimed_packet"),
        sa.CheckConstraint("attribution_status = 'unknown'", name="ck_untimed_attribution"),
        sa.CheckConstraint("battery_level BETWEEN 0 AND 100 AND transport_id_at_reception BETWEEN 1 AND 65535", name="ck_untimed_battery"),
        sa.CheckConstraint("(latitude IS NULL AND longitude IS NULL AND satellites = 0) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 AND satellites BETWEEN 1 AND 50)", name="ck_untimed_gps"),
        sa.CheckConstraint("activity BETWEEN 0 AND 20 AND activity_std BETWEEN 0 AND 65.535", name="ck_untimed_activity"),
        sa.CheckConstraint("(classification_status = 'predicted' AND predicted_behavior IN ('Active','Resting') AND predicted_behavior IS NOT NULL AND behavior_confidence IS NOT NULL AND behavior_confidence BETWEEN 0 AND 1 AND model_sha256 IS NOT NULL AND length(model_sha256) = 64 AND classified_at IS NOT NULL AND exclusion_reason IS NULL) OR (classification_status IN ('pending_model','excluded_context','inference_failed') AND predicted_behavior IS NULL AND behavior_confidence IS NULL AND model_sha256 IS NULL AND classified_at IS NULL)", name="ck_untimed_classification"),
        sa.CheckConstraint("accel_x_min BETWEEN -6 AND 6 AND accel_x_max BETWEEN -6 AND 6 AND accel_x_min <= accel_x_mean AND accel_x_mean <= accel_x_max AND accel_x_std BETWEEN 0 AND 6", name="ck_untimed_accel_x"),
        sa.CheckConstraint("accel_y_min BETWEEN -6 AND 6 AND accel_y_max BETWEEN -6 AND 6 AND accel_y_min <= accel_y_mean AND accel_y_mean <= accel_y_max AND accel_y_std BETWEEN 0 AND 6", name="ck_untimed_accel_y"),
        sa.CheckConstraint("accel_z_min BETWEEN -6 AND 6 AND accel_z_max BETWEEN -6 AND 6 AND accel_z_min <= accel_z_mean AND accel_z_mean <= accel_z_max AND accel_z_std BETWEEN 0 AND 6", name="ck_untimed_accel_z"),
    )
