"""Add veterinary tables: veterinary_cases, veterinary_entries

Revision ID: 9d5f7b2c3e4a
Revises: 8c4e6a1b2d3f
Create Date: 2026-09-22 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "9d5f7b2c3e4a"
down_revision = "8c4e6a1b2d3f"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Table veterinary_cases
    op.create_table(
        "veterinary_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("animal_id", sa.Integer(), sa.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("linked_alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="provisional", nullable=False),
        sa.Column("opened_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opened_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('provisional', 'confirmed', 'ruled_out', 'closed')",
            name="ck_veterinary_case_status",
        ),
    )
    op.create_index("ix_veterinary_cases_farm_id", "veterinary_cases", ["farm_id"])
    op.create_index("ix_veterinary_cases_animal_id", "veterinary_cases", ["animal_id"])
    op.create_index("ix_veterinary_cases_linked_alert_id", "veterinary_cases", ["linked_alert_id"])
    op.create_index("idx_vet_cases_farm_status", "veterinary_cases", ["farm_id", "status"])
    op.create_index("idx_vet_cases_animal", "veterinary_cases", ["animal_id", "created_at"])

    # 2. Table veterinary_entries
    op.create_table(
        "veterinary_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("veterinary_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "entry_type IN ('observation', 'intervention', 'follow_up', 'assessment', 'note')",
            name="ck_veterinary_entry_type",
        ),
    )
    op.create_index("ix_veterinary_entries_case_id", "veterinary_entries", ["case_id"])
    op.create_index("idx_vet_entries_case_occurred", "veterinary_entries", ["case_id", "occurred_at"])


def downgrade():
    op.drop_table("veterinary_entries")
    op.drop_table("veterinary_cases")
