"""
Web-Pennmush Database Connection and Initialization
Author: Jordan Koch (GitHub: kochj23)
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from backend.models import Base, DBObject, ObjectType, Attribute
from backend.config import settings
from passlib.context import CryptContext
from datetime import datetime


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in settings.DATABASE_URL else None,
    echo=settings.DEBUG
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db():
    """Dependency for FastAPI to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables and create starting rooms/objects.
    Creates the classic MUSH starting area: Room Zero (The Void).
    """
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

    # Create initial game world if it doesn't exist
    async with AsyncSessionLocal() as session:
        # Check if Room Zero exists
        result = await session.get(DBObject, 0)
        if result is None:
            print("Creating initial game world...")

            # Create God/Admin account (object #1)
            god = DBObject(
                id=1,
                name="One",
                type=ObjectType.PLAYER,
                password_hash=pwd_context.hash("potrzebie"),  # Default password, CHANGE THIS
                description="The One. The Administrator of this MUSH.",
                flags="GOD,WIZARD,ROYAL",
                created_at=datetime.utcnow(),
                location_id=0,
                home_id=0
            )
            session.add(god)

            # Create Room Zero - The Void (object #0)
            room_zero = DBObject(
                id=0,
                name="Room Zero",
                type=ObjectType.ROOM,
                owner_id=1,
                description=(
                    "You are standing in a formless void. There is nothing here but "
                    "infinite possibility. This is where all journeys begin.\n\n"
                    "Welcome to Web-Pennmush, a modern reimagination of the classic "
                    "PennMUSH server. Type 'help' to get started."
                ),
                flags="VISIBLE",
                created_at=datetime.utcnow()
            )
            session.add(room_zero)

            # Create Starting Room - Central Plaza (object #2)
            central_plaza = DBObject(
                id=2,
                name="Central Plaza",
                type=ObjectType.ROOM,
                owner_id=1,
                description=(
                    "You stand in the heart of the MUSH, a grand plaza paved with "
                    "smooth stone. Fountains bubble at the cardinal points, and "
                    "archways lead in all directions. This is where new adventurers "
                    "typically begin their journey.\n\n"
                    "A large sign reads: 'Welcome, traveler! Type 'look' to examine "
                    "your surroundings, 'say <message>' to speak, and 'help' for "
                    "more commands.'"
                ),
                flags="VISIBLE",
                created_at=datetime.utcnow(),
                owner_id=1
            )
            session.add(central_plaza)

            # Create exit from Room Zero to Central Plaza
            exit_zero_to_plaza = DBObject(
                id=3,
                name="portal",
                alias="portal;enter;go portal",
                type=ObjectType.EXIT,
                owner_id=1,
                description="A shimmering portal of light leading to the Central Plaza.",
                location_id=0,  # Exit is in Room Zero
                home_id=2,      # Destination is Central Plaza
                flags="VISIBLE",
                created_at=datetime.utcnow()
            )
            session.add(exit_zero_to_plaza)

            # Create return exit from Central Plaza to Room Zero
            exit_plaza_to_zero = DBObject(
                id=4,
                name="void",
                alias="void;enter void;return",
                type=ObjectType.EXIT,
                owner_id=1,
                description="A dark portal leading back to the formless void.",
                location_id=2,  # Exit is in Central Plaza
                home_id=0,      # Destination is Room Zero
                flags="VISIBLE",
                created_at=datetime.utcnow()
            )
            session.add(exit_plaza_to_zero)

            # Create a sample object - Magic Crystal
            magic_crystal = DBObject(
                id=5,
                name="magic crystal",
                alias="crystal",
                type=ObjectType.THING,
                owner_id=1,
                description=(
                    "A brilliant crystal that pulses with inner light. Strange runes "
                    "are etched into its surface. It feels warm to the touch."
                ),
                location_id=2,  # Located in Central Plaza
                home_id=2,
                flags="VISIBLE",
                created_at=datetime.utcnow()
            )
            session.add(magic_crystal)

            # Add sample attribute to crystal (softcode example)
            crystal_power_attr = Attribute(
                object_id=5,
                name="POWER",
                value="10",
                flags="VISIBLE"
            )
            session.add(crystal_power_attr)

            crystal_magic_attr = Attribute(
                object_id=5,
                name="MAGIC_TYPE",
                value="Illumination",
                flags="VISIBLE"
            )
            session.add(crystal_magic_attr)

            await session.commit()
            print("Initial game world created successfully!")
            print("  - Room Zero (#0): The Void")
            print("  - God/Admin (#1): One (password: potrzebie)")
            print("  - Central Plaza (#2): Starting room")
            print("  - Exits (#3, #4): Portal connections")
            print("  - Magic Crystal (#5): Sample object")
            print("\nIMPORTANT: Change the God password after first login!")


async def close_db():
    """Close database connections"""
    await engine.dispose()
