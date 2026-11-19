"""world_settings: key/value table holding the world RNG seed and epoch

Revision ID: 0002_world_settings
Revises: 0001_baseline
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_world_settings'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('world_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade():
    op.drop_table('world_settings')
