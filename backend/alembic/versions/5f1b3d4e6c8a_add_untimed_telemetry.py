"""Add isolated untimed telemetry archive; no historical backfill."""

from alembic import op
import sqlalchemy as sa

revision = "5f1b3d4e6c8a"
down_revision = "4e0a2c3d5b7f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("untimed_telemetry",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("device_id", sa.String(50), sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transport_id_at_reception", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("window_end_elapsed_ms", sa.BigInteger(), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_reliable", sa.Boolean(), nullable=False),
        sa.Column("time_uncertainty_reason", sa.String(32), nullable=False),
        sa.Column("raw_packet", sa.LargeBinary(), nullable=False),
        sa.Column("farm_id_at_reception", sa.Integer(), nullable=True),
        sa.Column("animal_id_at_reception", sa.Integer(), nullable=True),
        sa.Column("device_status_at_reception", sa.String(50), nullable=False),
        sa.Column("attribution_status", sa.String(32), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("satellites", sa.Integer(), nullable=False),
        sa.Column("battery_level", sa.Integer(), nullable=False),
        sa.Column("accel_x_mean", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_x_std", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_x_min", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_x_max", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_y_mean", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_y_std", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_y_min", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_y_max", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_z_mean", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_z_std", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_z_min", sa.Numeric(7, 4), nullable=False),
        sa.Column("accel_z_max", sa.Numeric(7, 4), nullable=False),
        sa.Column("activity", sa.Numeric(5, 3), nullable=False),
        sa.Column("activity_std", sa.Numeric(5, 3), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("window_samples", sa.Integer(), nullable=False),
        sa.Column("classification_status", sa.String(32), nullable=False),
        sa.Column("exclusion_reason", sa.String(50), nullable=True),
        sa.Column("predicted_behavior", sa.String(), nullable=True),
        sa.Column("behavior_confidence", sa.Float(), nullable=True),
        sa.Column("model_sha256", sa.String(64), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("device_id", "session_id", "sequence", name="uq_untimed_identity"),
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
    op.create_index("idx_untimed_received", "untimed_telemetry", ["received_at", "id"])
    op.create_index("idx_untimed_device_received", "untimed_telemetry", ["device_id", "received_at", "id"])


def downgrade():
    op.drop_table("untimed_telemetry")
