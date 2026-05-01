"""
Web-Pennmush Test Configuration
Author: Jordan Koch (GitHub: kochj23)

Shared fixtures for the entire test suite.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models import (
    Base, DBObject, ObjectType, Attribute, Lock, Mail, Channel,
    ChannelMembership, HelpTopic, NPC, Quest, QuestStep, QuestProgress,
    PlayerCurrency, Transaction, BanRecord, Page,
)
from backend.config import Settings
from backend.security import RateLimiter, InputValidator, SecurityLogger
from passlib.context import CryptContext
from datetime import datetime


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite://"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest_asyncio.fixture
async def engine():
    """Create an in-memory async SQLite engine for tests."""
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Provide a transactional database session for tests."""
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_session(db_session):
    """Seed the database with basic game world objects and return the session."""
    # God player
    god = DBObject(
        id=1,
        name="One",
        type=ObjectType.PLAYER,
        password_hash=pwd_context.hash("potrzebie"),
        description="The Administrator.",
        flags="GOD,WIZARD,ROYAL",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        location_id=0,
        home_id=0,
        is_connected=False,
    )
    db_session.add(god)

    # Room Zero
    room_zero = DBObject(
        id=0,
        name="Room Zero",
        type=ObjectType.ROOM,
        owner_id=1,
        description="The Void.",
        flags="VISIBLE",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(room_zero)

    # Central Plaza
    central_plaza = DBObject(
        id=2,
        name="Central Plaza",
        type=ObjectType.ROOM,
        owner_id=1,
        description="The heart of the MUSH.",
        flags="VISIBLE",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(central_plaza)

    # Exit Room Zero -> Central Plaza
    exit_forward = DBObject(
        id=3,
        name="portal",
        alias="portal;enter;go portal",
        type=ObjectType.EXIT,
        owner_id=1,
        description="A shimmering portal.",
        location_id=0,
        home_id=2,
        flags="VISIBLE",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(exit_forward)

    # Exit Central Plaza -> Room Zero
    exit_back = DBObject(
        id=4,
        name="void",
        alias="void;enter void;return",
        type=ObjectType.EXIT,
        owner_id=1,
        description="A dark portal.",
        location_id=2,
        home_id=0,
        flags="VISIBLE",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(exit_back)

    # Magic crystal in Central Plaza
    crystal = DBObject(
        id=5,
        name="magic crystal",
        alias="crystal",
        type=ObjectType.THING,
        owner_id=1,
        description="A brilliant crystal.",
        location_id=2,
        home_id=2,
        flags="VISIBLE",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(crystal)

    # Attribute on crystal
    power_attr = Attribute(
        object_id=5,
        name="POWER",
        value="10",
        flags="VISIBLE",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(power_attr)

    # Regular player
    player = DBObject(
        id=10,
        name="TestPlayer",
        type=ObjectType.PLAYER,
        password_hash=pwd_context.hash("testpass"),
        description="A test player.",
        flags="",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        location_id=2,
        home_id=2,
        is_connected=True,
    )
    db_session.add(player)

    # Public channel
    pub_channel = Channel(
        id=1,
        name="Public",
        alias="pub",
        description="General public channel",
        owner_id=1,
        is_public=True,
        is_moderated=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(pub_channel)

    # Help topic
    help_topic = HelpTopic(
        topic="help",
        category="basics",
        content="HELP - Display help information",
        aliases="?",
        related_topics="commands,building",
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
    )
    db_session.add(help_topic)

    await db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# Security fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rate_limiter():
    """Fresh rate limiter instance."""
    return RateLimiter()


@pytest.fixture
def input_validator():
    """Fresh input validator instance."""
    return InputValidator()


# ---------------------------------------------------------------------------
# FastAPI test client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def app_client(engine):
    """Provide an async HTTP client wired to the FastAPI app with a test DB."""
    from backend.main import app
    from backend.database import get_db

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    # Seed minimal data for API tests
    async with session_factory() as session:
        god = DBObject(
            id=1, name="One", type=ObjectType.PLAYER,
            password_hash=pwd_context.hash("potrzebie"),
            description="Admin", flags="GOD,WIZARD",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
            location_id=0, home_id=0, is_connected=False,
        )
        session.add(god)
        room = DBObject(
            id=0, name="Room Zero", type=ObjectType.ROOM, owner_id=1,
            description="The Void.", flags="VISIBLE",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        session.add(room)
        plaza = DBObject(
            id=2, name="Central Plaza", type=ObjectType.ROOM, owner_id=1,
            description="Starting room.", flags="VISIBLE",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        session.add(plaza)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
