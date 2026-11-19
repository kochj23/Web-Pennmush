"""baseline: schema as created by create_all (3.3.1)

Frozen snapshot of Base.metadata at 3.3.1. Databases that already have these
tables (from the old create_all startup) are STAMPED at this revision, never
re-created or altered. Do not edit; add a new revision instead.

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-11-19 11:33:32.567057
"""
from alembic import op
import sqlalchemy as sa


revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('help_topics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('topic', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('aliases', sa.String(length=500), nullable=True),
    sa.Column('related_topics', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('modified_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('help_topics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_help_topics_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_help_topics_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_help_topics_topic'), ['topic'], unique=True)

    op.create_table('objects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('type', sa.Enum('ROOM', 'THING', 'EXIT', 'PLAYER', 'GARBAGE', name='objecttype'), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('zone_id', sa.Integer(), nullable=True),
    sa.Column('location_id', sa.Integer(), nullable=True),
    sa.Column('home_id', sa.Integer(), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('contents_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('modified_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('flags', sa.String(length=255), nullable=False),
    sa.Column('powers', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.Column('is_connected', sa.Boolean(), nullable=True),
    sa.Column('site_account_id', sa.String(length=64), nullable=True),
    sa.Column('alias', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['contents_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['home_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['location_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('objects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_objects_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_objects_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_objects_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_objects_site_account_id'), ['site_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_objects_type'), ['type'], unique=False)

    op.create_table('attributes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('flags', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('modified_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attributes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attributes_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attributes_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_attributes_object_id'), ['object_id'], unique=False)

    op.create_table('ban_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('banned_by_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('banned_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['banned_by_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['player_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ban_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ban_records_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ban_records_player_id'), ['player_id'], unique=False)

    op.create_table('channels',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('alias', sa.String(length=50), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('is_public', sa.Boolean(), nullable=True),
    sa.Column('is_moderated', sa.Boolean(), nullable=True),
    sa.Column('flags', sa.String(length=255), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('channels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_channels_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_channels_name'), ['name'], unique=True)

    op.create_table('locks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('lock_type', sa.String(length=50), nullable=False),
    sa.Column('lock_key', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('locks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_locks_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_locks_object_id'), ['object_id'], unique=False)

    op.create_table('mail',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=False),
    sa.Column('recipient_id', sa.Integer(), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.Column('sent_at', sa.DateTime(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['recipient_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['sender_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mail', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mail_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mail_recipient_id'), ['recipient_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mail_sender_id'), ['sender_id'], unique=False)

    op.create_table('npcs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('personality', sa.Text(), nullable=False),
    sa.Column('knowledge_base', sa.Text(), nullable=True),
    sa.Column('ai_model', sa.String(length=100), nullable=False),
    sa.Column('temperature', sa.Integer(), nullable=False),
    sa.Column('max_tokens', sa.Integer(), nullable=False),
    sa.Column('conversation_history', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('modified_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('object_id')
    )
    with op.batch_alter_table('npcs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_npcs_id'), ['id'], unique=False)

    op.create_table('pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('from_player_id', sa.Integer(), nullable=False),
    sa.Column('to_player_id', sa.Integer(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['from_player_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['to_player_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pages_from_player_id'), ['from_player_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pages_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pages_to_player_id'), ['to_player_id'], unique=False)

    op.create_table('player_currency',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('credits', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('modified_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['player_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('player_currency', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_player_currency_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_player_currency_player_id'), ['player_id'], unique=True)

    op.create_table('quests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('reward_credits', sa.Integer(), nullable=True),
    sa.Column('reward_items', sa.Text(), nullable=True),
    sa.Column('is_repeatable', sa.Boolean(), nullable=True),
    sa.Column('min_level', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['creator_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('quests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_quests_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_quests_name'), ['name'], unique=True)

    op.create_table('transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('from_player_id', sa.Integer(), nullable=True),
    sa.Column('to_player_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('transaction_type', sa.String(length=50), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['from_player_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['to_player_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transactions_from_player_id'), ['from_player_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transactions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transactions_to_player_id'), ['to_player_id'], unique=False)

    op.create_table('channel_memberships',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('channel_id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('joined_at', sa.DateTime(), nullable=False),
    sa.Column('is_muted', sa.Boolean(), nullable=True),
    sa.Column('is_moderator', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
    sa.ForeignKeyConstraint(['player_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('channel_memberships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_channel_memberships_channel_id'), ['channel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_channel_memberships_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_channel_memberships_player_id'), ['player_id'], unique=False)

    op.create_table('quest_progress',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quest_id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('current_step', sa.Integer(), nullable=True),
    sa.Column('is_completed', sa.Boolean(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('times_completed', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['quest_id'], ['quests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('quest_progress', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_quest_progress_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_quest_progress_player_id'), ['player_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_quest_progress_quest_id'), ['quest_id'], unique=False)

    op.create_table('quest_steps',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quest_id', sa.Integer(), nullable=False),
    sa.Column('step_number', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('required_object_id', sa.Integer(), nullable=True),
    sa.Column('required_location_id', sa.Integer(), nullable=True),
    sa.Column('required_action', sa.String(length=100), nullable=True),
    sa.Column('completion_text', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['quest_id'], ['quests.id'], ),
    sa.ForeignKeyConstraint(['required_location_id'], ['objects.id'], ),
    sa.ForeignKeyConstraint(['required_object_id'], ['objects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('quest_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_quest_steps_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_quest_steps_quest_id'), ['quest_id'], unique=False)



def downgrade():
    with op.batch_alter_table('quest_steps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_quest_steps_quest_id'))
        batch_op.drop_index(batch_op.f('ix_quest_steps_id'))

    op.drop_table('quest_steps')
    with op.batch_alter_table('quest_progress', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_quest_progress_quest_id'))
        batch_op.drop_index(batch_op.f('ix_quest_progress_player_id'))
        batch_op.drop_index(batch_op.f('ix_quest_progress_id'))

    op.drop_table('quest_progress')
    with op.batch_alter_table('channel_memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_channel_memberships_player_id'))
        batch_op.drop_index(batch_op.f('ix_channel_memberships_id'))
        batch_op.drop_index(batch_op.f('ix_channel_memberships_channel_id'))

    op.drop_table('channel_memberships')
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_to_player_id'))
        batch_op.drop_index(batch_op.f('ix_transactions_id'))
        batch_op.drop_index(batch_op.f('ix_transactions_from_player_id'))

    op.drop_table('transactions')
    with op.batch_alter_table('quests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_quests_name'))
        batch_op.drop_index(batch_op.f('ix_quests_id'))

    op.drop_table('quests')
    with op.batch_alter_table('player_currency', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_player_currency_player_id'))
        batch_op.drop_index(batch_op.f('ix_player_currency_id'))

    op.drop_table('player_currency')
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pages_to_player_id'))
        batch_op.drop_index(batch_op.f('ix_pages_id'))
        batch_op.drop_index(batch_op.f('ix_pages_from_player_id'))

    op.drop_table('pages')
    with op.batch_alter_table('npcs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_npcs_id'))

    op.drop_table('npcs')
    with op.batch_alter_table('mail', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mail_sender_id'))
        batch_op.drop_index(batch_op.f('ix_mail_recipient_id'))
        batch_op.drop_index(batch_op.f('ix_mail_id'))

    op.drop_table('mail')
    with op.batch_alter_table('locks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_locks_object_id'))
        batch_op.drop_index(batch_op.f('ix_locks_id'))

    op.drop_table('locks')
    with op.batch_alter_table('channels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_channels_name'))
        batch_op.drop_index(batch_op.f('ix_channels_id'))

    op.drop_table('channels')
    with op.batch_alter_table('ban_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ban_records_player_id'))
        batch_op.drop_index(batch_op.f('ix_ban_records_id'))

    op.drop_table('ban_records')
    with op.batch_alter_table('attributes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attributes_object_id'))
        batch_op.drop_index(batch_op.f('ix_attributes_name'))
        batch_op.drop_index(batch_op.f('ix_attributes_id'))

    op.drop_table('attributes')
    with op.batch_alter_table('objects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_objects_type'))
        batch_op.drop_index(batch_op.f('ix_objects_site_account_id'))
        batch_op.drop_index(batch_op.f('ix_objects_name'))
        batch_op.drop_index(batch_op.f('ix_objects_location_id'))
        batch_op.drop_index(batch_op.f('ix_objects_id'))

    op.drop_table('objects')
    with op.batch_alter_table('help_topics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_help_topics_topic'))
        batch_op.drop_index(batch_op.f('ix_help_topics_id'))
        batch_op.drop_index(batch_op.f('ix_help_topics_category'))

    op.drop_table('help_topics')
    sa.Enum(name='objecttype').drop(op.get_bind(), checkfirst=True)
