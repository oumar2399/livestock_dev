"""add daily job execution history

Revision ID: e9f5a7b2c3d4
Revises: d8e4f6a1b2c3
Create Date: 2026-09-01 11:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f5a7b2c3d4"
down_revision: Union[str, None] = "d8e4f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=80), nullable=False),
        sa.Column("trigger_source", sa.String(length=20), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("timezone_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initiated_by", sa.Integer(), nullable=True),
        sa.Column("summaries_created", sa.Integer(), nullable=True),
        sa.Column("alerts_created", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_daily_job_runs_status",
        ),
        sa.CheckConstraint(
            "trigger_source IN ('scheduled', 'manual')",
            name="ck_daily_job_runs_trigger_source",
        ),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_daily_job_runs_job_target",
        "daily_job_runs",
        ["job_name", "target_date"],
    )
    op.create_index(
        "idx_daily_job_runs_started",
        "daily_job_runs",
        [sa.text("started_at DESC")],
    )
    op.create_index(
        "idx_daily_job_runs_status",
        "daily_job_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("idx_daily_job_runs_status", table_name="daily_job_runs")
    op.drop_index("idx_daily_job_runs_started", table_name="daily_job_runs")
    op.drop_index("idx_daily_job_runs_job_target", table_name="daily_job_runs")
    op.drop_table("daily_job_runs")
