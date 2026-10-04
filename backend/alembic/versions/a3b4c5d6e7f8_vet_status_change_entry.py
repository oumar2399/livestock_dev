"""Allow 'status_change' veterinary journal entries (case status history).

Revision ID: a3b4c5d6e7f8
Revises: 9d5f7b2c3e4a
Create Date: 2026-10-04 03:00:00.000000

"""
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "9d5f7b2c3e4a"
branch_labels = None
depends_on = None

MANUAL_TYPES = "'observation', 'intervention', 'follow_up', 'assessment', 'note'"


def upgrade():
    op.drop_constraint("ck_veterinary_entry_type", "veterinary_entries", type_="check")
    op.create_check_constraint(
        "ck_veterinary_entry_type",
        "veterinary_entries",
        f"entry_type IN ({MANUAL_TYPES}, 'status_change')",
    )


def downgrade():
    # The journal is append-only: refuse rather than delete status-change history.
    count = op.get_bind().exec_driver_sql(
        "SELECT count(*) FROM veterinary_entries WHERE entry_type = 'status_change'"
    ).scalar()
    if count:
        raise RuntimeError(f"{count} status_change journal entries exist; downgrade would lose case history")
    op.drop_constraint("ck_veterinary_entry_type", "veterinary_entries", type_="check")
    op.create_check_constraint(
        "ck_veterinary_entry_type",
        "veterinary_entries",
        f"entry_type IN ({MANUAL_TYPES})",
    )
