"""add_alert_feedback_and_unique_constraints

Revision ID: 29135abe6072
Revises: 093cf2d65539
Create Date: 2026-08-20 09:47:19.821233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '29135abe6072'
down_revision: Union[str, None] = '093cf2d65539'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create alert_feedbacks table
    op.create_table('alert_feedbacks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=False),
        sa.Column('animal_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('z_score', sa.Float(), nullable=True),
        sa.Column('verdict', sa.String(length=30), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['animal_id'], ['animals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'alert_id', name='uq_user_alert_feedback')
    )
    op.create_index(op.f('ix_alert_feedbacks_alert_id'), 'alert_feedbacks', ['alert_id'], unique=False)
    op.create_index(op.f('ix_alert_feedbacks_animal_id'), 'alert_feedbacks', ['animal_id'], unique=False)
    op.create_index(op.f('ix_alert_feedbacks_id'), 'alert_feedbacks', ['id'], unique=False)
    op.create_index(op.f('ix_alert_feedbacks_user_id'), 'alert_feedbacks', ['user_id'], unique=False)

    # Update prediction_feedbacks: remove NULLs and keep latest row for duplicate (user_id, animal_id, telemetry_time)
    op.execute("DELETE FROM prediction_feedbacks WHERE telemetry_time IS NULL OR user_id IS NULL")
    op.execute("""
        DELETE FROM prediction_feedbacks a USING prediction_feedbacks b
        WHERE a.id < b.id
          AND a.user_id = b.user_id
          AND a.animal_id = b.animal_id
          AND a.telemetry_time = b.telemetry_time
    """)
    op.alter_column('prediction_feedbacks', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('prediction_feedbacks', 'telemetry_time',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.create_index(op.f('ix_prediction_feedbacks_animal_id'), 'prediction_feedbacks', ['animal_id'], unique=False)
    op.create_index(op.f('ix_prediction_feedbacks_telemetry_time'), 'prediction_feedbacks', ['telemetry_time'], unique=False)
    op.create_index(op.f('ix_prediction_feedbacks_user_id'), 'prediction_feedbacks', ['user_id'], unique=False)
    op.create_unique_constraint('uq_user_prediction_feedback', 'prediction_feedbacks', ['user_id', 'animal_id', 'telemetry_time'])
    op.drop_constraint('prediction_feedbacks_user_id_fkey', 'prediction_feedbacks', type_='foreignkey')
    op.create_foreign_key(None, 'prediction_feedbacks', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint(None, 'prediction_feedbacks', type_='foreignkey')
    op.create_foreign_key('prediction_feedbacks_user_id_fkey', 'prediction_feedbacks', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    op.drop_constraint('uq_user_prediction_feedback', 'prediction_feedbacks', type_='unique')
    op.drop_index(op.f('ix_prediction_feedbacks_user_id'), table_name='prediction_feedbacks')
    op.drop_index(op.f('ix_prediction_feedbacks_telemetry_time'), table_name='prediction_feedbacks')
    op.drop_index(op.f('ix_prediction_feedbacks_animal_id'), table_name='prediction_feedbacks')
    op.alter_column('prediction_feedbacks', 'telemetry_time',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('prediction_feedbacks', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    op.drop_index(op.f('ix_alert_feedbacks_user_id'), table_name='alert_feedbacks')
    op.drop_index(op.f('ix_alert_feedbacks_id'), table_name='alert_feedbacks')
    op.drop_index(op.f('ix_alert_feedbacks_animal_id'), table_name='alert_feedbacks')
    op.drop_index(op.f('ix_alert_feedbacks_alert_id'), table_name='alert_feedbacks')
    op.drop_table('alert_feedbacks')
    # ### end Alembic commands ###
