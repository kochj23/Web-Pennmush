"""
Web-Pennmush Database Models
Author: Jordan Koch (GitHub: kochj23)

Core object system modeled after PennMUSH's unified object structure.
Everything is an Object with different types: ROOM, THING, EXIT, PLAYER.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum


Base = declarative_base()


class ObjectType(str, enum.Enum):
    """Object types following PennMUSH convention"""
    ROOM = "ROOM"
    THING = "THING"
    EXIT = "EXIT"
    PLAYER = "PLAYER"
    GARBAGE = "GARBAGE"


class FlagType(str, enum.Enum):
    """Permission flags following PennMUSH hierarchy"""
    INHERIT = "INHERIT"
    OWNED = "OWNED"
    ROYAL = "ROYAL"
    WIZARD = "WIZARD"
    GOD = "GOD"
    INTERNAL = "INTERNAL"
    DARK = "DARK"
    VISIBLE = "VISIBLE"
    CONNECTED = "CONNECTED"
    HAVEN = "HAVEN"
    TRANSPARENT = "TRANSPARENT"


class DBObject(Base):
    """
    Unified object structure representing all MUSH entities.
    Fields are overloaded based on object type:

    - location: Container for things/players; destination for exits; drop-to for rooms
    - home: Home for things/players; source room for exits; unused for rooms
    - contents_id: First item in contents chain (for rooms and containers)
    - parent_id: Inheritance parent object
    """
    __tablename__ = "objects"

    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    type = Column(Enum(ObjectType), nullable=False, index=True)

    # Ownership and zones
    owner_id = Column(Integer, ForeignKey("objects.id"), nullable=True)
    zone_id = Column(Integer, ForeignKey("objects.id"), nullable=True)

    # Location tracking (overloaded based on type)
    location_id = Column(Integer, ForeignKey("objects.id"), nullable=True, index=True)
    home_id = Column(Integer, ForeignKey("objects.id"), nullable=True)

    # Object hierarchy
    parent_id = Column(Integer, ForeignKey("objects.id"), nullable=True)
    contents_id = Column(Integer, ForeignKey("objects.id"), nullable=True)

    # Descriptions
    description = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    # Flags and permissions
    flags = Column(String(255), default="", nullable=False)  # Comma-separated flags
    powers = Column(String(255), default="", nullable=False)

    # Player-specific fields
    password_hash = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    last_login = Column(DateTime, nullable=True)
    is_connected = Column(Boolean, default=False)

    # Exit-specific fields
    alias = Column(String(255), nullable=True)  # Exit aliases (north;n;go north)

    # Relationships
    owner = relationship("DBObject", foreign_keys=[owner_id], remote_side=[id], backref="owned_objects")
    zone = relationship("DBObject", foreign_keys=[zone_id], remote_side=[id], backref="zone_objects")
    location = relationship("DBObject", foreign_keys=[location_id], remote_side=[id], backref="located_objects")
    home = relationship("DBObject", foreign_keys=[home_id], remote_side=[id], backref="homed_objects")
    parent = relationship("DBObject", foreign_keys=[parent_id], remote_side=[id], backref="children")

    def __repr__(self):
        return f"<DBObject(id={self.id}, name='{self.name}', type={self.type})>"


class Attribute(Base):
    """
    Arbitrary attributes attached to objects.
    Used for softcode storage, object properties, etc.
    """
    __tablename__ = "attributes"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    value = Column(Text, nullable=False)
    flags = Column(String(255), default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    object = relationship("DBObject", backref="attributes")

    def __repr__(self):
        return f"<Attribute(id={self.id}, name='{self.name}', object_id={self.object_id})>"


class Lock(Base):
    """
    Lock system for controlling access to objects and commands.
    Format: lock_type:key (e.g., "use:has_key" or "enter:#123")
    """
    __tablename__ = "locks"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    lock_type = Column(String(50), nullable=False)  # use, enter, teleport, etc.
    lock_key = Column(Text, nullable=False)  # Lock evaluation expression
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    object = relationship("DBObject", backref="locks")

    def __repr__(self):
        return f"<Lock(id={self.id}, type='{self.lock_type}', object_id={self.object_id})>"


class Mail(Base):
    """Mail system for player-to-player messages"""
    __tablename__ = "mail"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)

    # Relationships
    sender = relationship("DBObject", foreign_keys=[sender_id], backref="sent_mail")
    recipient = relationship("DBObject", foreign_keys=[recipient_id], backref="received_mail")

    def __repr__(self):
        return f"<Mail(id={self.id}, from={self.sender_id}, to={self.recipient_id})>"


class Channel(Base):
    """
    Communication channels for group chat.
    Players can join channels and broadcast messages to all members.
    """
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    alias = Column(String(50), nullable=True)  # Short alias for quick access
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_public = Column(Boolean, default=True)  # Public channels vs private
    is_moderated = Column(Boolean, default=False)  # Requires approval to join
    flags = Column(String(255), default="", nullable=False)  # Channel flags

    # Relationships
    owner = relationship("DBObject", backref="owned_channels")

    def __repr__(self):
        return f"<Channel(id={self.id}, name='{self.name}')>"


class ChannelMembership(Base):
    """
    Tracks which players are subscribed to which channels.
    """
    __tablename__ = "channel_memberships"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_muted = Column(Boolean, default=False)  # Player muted the channel
    is_moderator = Column(Boolean, default=False)  # Can moderate the channel

    # Relationships
    channel = relationship("Channel", backref="memberships")
    player = relationship("DBObject", backref="channel_memberships")

    def __repr__(self):
        return f"<ChannelMembership(channel_id={self.channel_id}, player_id={self.player_id})>"


class HelpTopic(Base):
    """
    Help system topics for in-game documentation.
    """
    __tablename__ = "help_topics"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(255), unique=True, nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)  # commands, building, softcode, etc.
    content = Column(Text, nullable=False)
    aliases = Column(String(500), nullable=True)  # Comma-separated aliases
    related_topics = Column(String(500), nullable=True)  # Comma-separated related topics
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<HelpTopic(id={self.id}, topic='{self.topic}')>"


class NPC(Base):
    """
    AI-powered NPCs with personality and knowledge base.
    """
    __tablename__ = "npcs"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False, unique=True)
    personality = Column(Text, nullable=False)  # AI personality description
    knowledge_base = Column(Text, nullable=True)  # Context for AI responses
    ai_model = Column(String(100), default="gpt-4", nullable=False)  # AI model to use
    temperature = Column(Integer, default=7, nullable=False)  # 0-10 scale (divide by 10 for API)
    max_tokens = Column(Integer, default=150, nullable=False)
    conversation_history = Column(Text, nullable=True)  # JSON array of recent messages
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    object = relationship("DBObject", backref="npc_data")

    def __repr__(self):
        return f"<NPC(id={self.id}, object_id={self.object_id})>"


class Quest(Base):
    """
    Quest system for structured gameplay.
    """
    __tablename__ = "quests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    creator_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    reward_credits = Column(Integer, default=0)
    reward_items = Column(Text, nullable=True)  # JSON array of item IDs
    is_repeatable = Column(Boolean, default=False)
    min_level = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    creator = relationship("DBObject", backref="created_quests")

    def __repr__(self):
        return f"<Quest(id={self.id}, name='{self.name}')>"


class QuestStep(Base):
    """Individual steps in a quest"""
    __tablename__ = "quest_steps"

    id = Column(Integer, primary_key=True, index=True)
    quest_id = Column(Integer, ForeignKey("quests.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    required_object_id = Column(Integer, ForeignKey("objects.id"), nullable=True)
    required_location_id = Column(Integer, ForeignKey("objects.id"), nullable=True)
    required_action = Column(String(100), nullable=True)  # Command to complete step
    completion_text = Column(Text, nullable=True)

    # Relationships
    quest = relationship("Quest", backref="steps")

    def __repr__(self):
        return f"<QuestStep(id={self.id}, quest_id={self.quest_id}, step={self.step_number})>"


class QuestProgress(Base):
    """Tracks player progress on quests"""
    __tablename__ = "quest_progress"

    id = Column(Integer, primary_key=True, index=True)
    quest_id = Column(Integer, ForeignKey("quests.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    current_step = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    times_completed = Column(Integer, default=0)

    # Relationships
    quest = relationship("Quest")
    player = relationship("DBObject", backref="quest_progress")

    def __repr__(self):
        return f"<QuestProgress(quest_id={self.quest_id}, player_id={self.player_id}, step={self.current_step})>"


class PlayerCurrency(Base):
    """Player currency balances"""
    __tablename__ = "player_currency"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("objects.id"), nullable=False, unique=True, index=True)
    credits = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    player = relationship("DBObject", backref="currency")

    def __repr__(self):
        return f"<PlayerCurrency(player_id={self.player_id}, credits={self.credits})>"


class Transaction(Base):
    """Economic transaction log"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    from_player_id = Column(Integer, ForeignKey("objects.id"), nullable=True, index=True)
    to_player_id = Column(Integer, ForeignKey("objects.id"), nullable=True, index=True)
    amount = Column(Integer, nullable=False)
    transaction_type = Column(String(50), nullable=False)  # give, quest_reward, shop_buy, etc.
    description = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    from_player = relationship("DBObject", foreign_keys=[from_player_id], backref="transactions_sent")
    to_player = relationship("DBObject", foreign_keys=[to_player_id], backref="transactions_received")

    def __repr__(self):
        return f"<Transaction(id={self.id}, amount={self.amount}, type={self.transaction_type})>"


class BanRecord(Base):
    """Player ban records for moderation"""
    __tablename__ = "ban_records"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    banned_by_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    reason = Column(Text, nullable=False)
    banned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # NULL = permanent ban
    is_active = Column(Boolean, default=True)

    # Relationships
    player = relationship("DBObject", foreign_keys=[player_id], backref="ban_records")
    banned_by = relationship("DBObject", foreign_keys=[banned_by_id], backref="bans_issued")

    def __repr__(self):
        return f"<BanRecord(id={self.id}, player_id={self.player_id}, active={self.is_active})>"


class Page(Base):
    """Direct message system (pages)"""
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    from_player_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    to_player_id = Column(Integer, ForeignKey("objects.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_read = Column(Boolean, default=False)

    # Relationships
    from_player = relationship("DBObject", foreign_keys=[from_player_id], backref="pages_sent")
    to_player = relationship("DBObject", foreign_keys=[to_player_id], backref="pages_received")

    def __repr__(self):
        return f"<Page(id={self.id}, from={self.from_player_id}, to={self.to_player_id})>"
