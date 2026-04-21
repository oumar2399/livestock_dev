"""baseline_existing_schema

Revision ID: fbc3952585f9
Revises: 
Create Date: 2026-04-12 11:12:40.362812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fbc3952585f9'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('telemetry', sa.Column('activity_std',   sa.Numeric(5,3)))
    op.add_column('telemetry', sa.Column('accel_x_mean',   sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_x_std',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_x_min',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_x_max',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_y_mean',   sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_y_std',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_y_min',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_y_max',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_z_mean',   sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_z_std',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_z_min',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('accel_z_max',    sa.Numeric(7,4)))
    op.add_column('telemetry', sa.Column('sample_rate',    sa.Integer()))
    op.add_column('telemetry', sa.Column('window_samples', sa.Integer()))


def downgrade():
    for col in ['activity_std', 'accel_x_mean', 'accel_x_std',
                'accel_x_min', 'accel_x_max', 'accel_y_mean',
                'accel_y_std', 'accel_y_min', 'accel_y_max',
                'accel_z_mean', 'accel_z_std', 'accel_z_min',
                'accel_z_max', 'sample_rate', 'window_samples']:
        op.drop_column('telemetry', col)
