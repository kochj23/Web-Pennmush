"""rate_limit_hits: persisted login/registration attempts

Revision ID: 0003_rate_limit_hits
Revises: 0002_world_settings
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_rate_limit_hits'
down_revision = '0002_world_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rate_limit_hits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bucket', sa.String(length=160), nullable=False),
    sa.Column('hit_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rate_limit_hits_bucket_hit_at', 'rate_limit_hits', ['bucket', 'hit_at'], unique=False)
    op.create_index('ix_rate_limit_hits_hit_at', 'rate_limit_hits', ['hit_at'], unique=False)


def downgrade():
    op.drop_index('ix_rate_limit_hits_hit_at', table_name='rate_limit_hits')
    op.drop_index('ix_rate_limit_hits_bucket_hit_at', table_name='rate_limit_hits')
    op.drop_table('rate_limit_hits')
