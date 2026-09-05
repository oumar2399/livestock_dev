"""add_farm_memberships_table

Revision ID: b4e8f1a2c3d4
Revises: 29135abe6072
Create Date: 2026-08-22 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e8f1a2c3d4"
down_revision: Union[str, None] = "29135abe6072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farm_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("farm_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("invited_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "role IN ('owner', 'farmer', 'vet')",
            name="ck_farm_membership_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'revoked')",
            name="ck_farm_membership_status",
        ),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "farm_id", name="uq_user_farm_membership"),
    )
    op.create_index(
        op.f("ix_farm_memberships_farm_id"),
        "farm_memberships",
        ["farm_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_farm_memberships_id"),
        "farm_memberships",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_farm_memberships_user_id"),
        "farm_memberships",
        ["user_id"],
        unique=False,
    )

    # Seed: one owner membership per farm (owners only — no default farm id=1 for other users)
    op.execute(
        """
        INSERT INTO farm_memberships (user_id, farm_id, role, status, created_at, updated_at)
        SELECT f.owner_id, f.id, 'owner', 'active', NOW(), NOW()
        FROM farms f
        WHERE f.owner_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_farm_memberships_user_id"), table_name="farm_memberships")
    op.drop_index(op.f("ix_farm_memberships_id"), table_name="farm_memberships")
    op.drop_index(op.f("ix_farm_memberships_farm_id"), table_name="farm_memberships")
    op.drop_table("farm_memberships")
