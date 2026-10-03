"""Bootstrap prospective tracking and durable farm creation receipts."""

from alembic import op
import sqlalchemy as sa

revision = "7b3d5f6a8c9e"
down_revision = "6a2c4e5f7b8d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "farm_creation_requests",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id", ondelete="SET NULL")),
    )
    # No backdating: only associations known at deployment become proven.
    op.execute("LOCK TABLE animals, animal_tracking_periods IN SHARE ROW EXCLUSIVE MODE")
    op.create_index("uq_tracking_open_animal", "animal_tracking_periods", ["animal_id"],
                    unique=True, postgresql_where=sa.text("valid_to IS NULL"))
    op.execute("""
        INSERT INTO animal_tracking_periods
            (animal_id, device_id, farm_id, valid_from, recorded_at, source)
        SELECT a.id, a.assigned_device, a.farm_id, statement_timestamp(),
               statement_timestamp(), 'deployment_bootstrap'
        FROM animals a
        WHERE a.farm_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM animal_tracking_periods p
              WHERE p.animal_id = a.id AND p.valid_to IS NULL
          )
    """)


def downgrade():
    # Keep historical evidence; a schema rollback must not delete tracking history.
    op.drop_table("farm_creation_requests")
    op.drop_index("uq_tracking_open_animal", table_name="animal_tracking_periods")
