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
