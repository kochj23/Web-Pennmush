"""
Web-Pennmush Database Connection and Initialization
Author: Jordan Koch (GitHub: kochj23)

Production runs on Postgres (asyncpg) with a bounded pool, a per-statement
timeout and connection retry with backoff. SQLite remains for local dev/tests.
"""
import asyncio
import logging
import os
import secrets
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from backend.models import Base, DBObject, ObjectType, Attribute, Channel, ChannelMembership, HelpTopic, WorldSetting
from backend.config import settings
from backend.passwords import pwd_context
from datetime import datetime

log = logging.getLogger("webpennmush.db")


_SSL_KEYS = ("sslmode", "sslrootcert", "sslcert", "sslkey")


def split_pg_url(url: str):
    """
    Normalise a libpq-style Postgres URL for SQLAlchemy+asyncpg.

    Returns (sqlalchemy_url, ssl_arg). sslmode/sslrootcert are removed from the
    query string and turned into an SSLContext (verify-full pins the CA and
    checks the hostname), because SQLAlchemy passes kwargs, not the DSN.
    """
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    import ssl

    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    rootcert = query.pop("sslrootcert", None)
    for k in _SSL_KEYS:
        query.pop(k, None)
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    ssl_arg = None
    if sslmode in ("verify-full", "verify-ca"):
        ctx = ssl.create_default_context(cafile=rootcert) if rootcert else ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = sslmode == "verify-full"
        ctx.verify_mode = ssl.CERT_REQUIRED
        ssl_arg = ctx
    elif sslmode == "require":
        ssl_arg = "require"
    elif sslmode == "disable":
        ssl_arg = False
    return clean, ssl_arg


def build_engine(url: str):
    """Create the async engine with backend-appropriate pool/timeout settings."""
    if url.startswith("sqlite"):
        in_memory = url.endswith("://") or ":memory:" in url
        return create_async_engine(
            url,
            connect_args={"check_same_thread": False},
            # A file DB gets a fresh connection per session (no event-loop affinity).
            poolclass=StaticPool if in_memory else NullPool,
            echo=False,
        )
    connect_args = {
        "timeout": 10,
        "command_timeout": max(1, settings.DB_STATEMENT_TIMEOUT_MS // 1000 + 1),
        "server_settings": {
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
            "idle_in_transaction_session_timeout": "30000",
            "application_name": "web-pennmush",
            "search_path": settings.DB_SCHEMA,
        },
    }
    url, ssl_arg = split_pg_url(url)
    if ssl_arg is not None:
        connect_args["ssl"] = ssl_arg
    return create_async_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_S,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
        echo=False,
    )


# Create async engine
engine = build_engine(settings.database_url())

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


async def wait_for_db(eng=None, retries: int = None, base_delay: float = 0.5, max_delay: float = 10.0):
    """Block until the database answers SELECT 1, retrying with exponential backoff."""
    eng = eng or engine
    retries = settings.DB_CONNECT_RETRIES if retries is None else retries
    delay = base_delay
    for attempt in range(1, retries + 1):
        try:
            async with eng.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return attempt
        except Exception as exc:  # connection refused, DNS, auth during startup...
            if attempt >= retries:
                raise
            log.warning("database not ready (attempt %d/%d): %s", attempt, retries, type(exc).__name__)
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
    return retries


async def sync_sequences(eng=None):
    """Postgres: move serial sequences past explicitly-inserted seed ids."""
    eng = eng or engine
    if eng.dialect.name != "postgresql":
        return
    async with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if "id" not in table.c:
                continue
            await conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                f"GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table.name}), 1))"
            ))


def _store_god_password(password: str) -> str:
    """Write the one-time God password to a 0600 file on the data volume (never stdout)."""
    data_dir = Path(settings.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "initial_god_password"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(password + "\n")
    return str(path)


async def init_db():
    """
    Initialize database tables and create starting rooms/objects.
    Creates the classic MUSH starting area: Room Zero (The Void).
    """
    await wait_for_db()
    migrate_url = settings.migrate_url()
    ddl_engine = engine if migrate_url == settings.database_url() else build_engine(migrate_url)
    try:
        await _init_schema_and_seed(ddl_engine)
    finally:
        if ddl_engine is not engine:
            await ddl_engine.dispose()


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BASELINE_REVISION = "0001_baseline"


def alembic_config(extra_version_locations=()):
    """Programmatic Alembic config (no alembic.ini needed in the image)."""
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("path_separator", "os")
    locations = [str(MIGRATIONS_DIR / "versions"), *(str(p) for p in extra_version_locations)]
    cfg.set_main_option("version_locations", os.pathsep.join(locations))
    return cfg


def _migrate_sync(conn, cfg) -> str:
    """Stamp a pre-Alembic database at the baseline, then upgrade to head."""
    from alembic import command
    from sqlalchemy import inspect

    cfg.attributes["connection"] = conn
    tables = set(inspect(conn).get_table_names())
    action = "upgraded"
    if "alembic_version" not in tables and "objects" in tables:
        # Created by the old create_all startup: record it as the baseline
        # without touching a single table.
        command.stamp(cfg, BASELINE_REVISION)
        action = "stamped"
    command.upgrade(cfg, "head")
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    drift = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    if drift:
        log.warning("schema differs from the models in %d place(s) after upgrade: %s", len(drift), drift[:5])
    return action


async def run_migrations(ddl_engine, extra_version_locations=()) -> str:
    """Run `alembic upgrade head` on ddl_engine (owner role) in one transaction."""
    cfg = alembic_config(extra_version_locations)
    async with ddl_engine.begin() as conn:
        action = await conn.run_sync(_migrate_sync, cfg)
    log.info("database schema %s to head", action)
    return action


async def _init_schema_and_seed(ddl_engine):
    """Alembic upgrade + world seed + sequence sync, run as the schema owner role."""
    await run_migrations(ddl_engine)
    SeedSession = async_sessionmaker(ddl_engine, class_=AsyncSession, expire_on_commit=False)

    # Create initial game world if it doesn't exist
    async with SeedSession() as session:
        # Check if Room Zero exists
        result = await session.get(DBObject, 0)
        if result is None:
            log.warning("Creating initial game world...")

            # Create God/Admin account (object #1) with random password
            god_password = os.environ.get("GOD_PASSWORD") or secrets.token_urlsafe(16)
            god = DBObject(
                id=1,
                name="One",
                type=ObjectType.PLAYER,
                password_hash=pwd_context.hash(god_password),
                description="The One. The Administrator of this MUSH.",
                flags="GOD,WIZARD,ROYAL",
                created_at=datetime.utcnow(),
                # location/home (#0) are set after Room Zero exists: Postgres enforces the FK.
                location_id=None,
                home_id=None
            )
            session.add(god)
            await session.flush()

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
            await session.flush()
            god.location_id = 0
            god.home_id = 0

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
                created_at=datetime.utcnow()
            )
            session.add(central_plaza)
            await session.flush()

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
            await session.flush()

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

            # Create default channels
            public_channel = Channel(
                name="Public",
                alias="pub",
                description="General public discussion channel",
                owner_id=1,
                is_public=True,
                is_moderated=False
            )
            session.add(public_channel)

            newbie_channel = Channel(
                name="Newbie",
                alias="new",
                description="Help channel for new players",
                owner_id=1,
                is_public=True,
                is_moderated=False
            )
            session.add(newbie_channel)

            builder_channel = Channel(
                name="Builder",
                alias="build",
                description="Channel for builders and creators",
                owner_id=1,
                is_public=True,
                is_moderated=False
            )
            session.add(builder_channel)

            # Auto-join God to all channels
            await session.flush()  # Flush to get channel IDs
            for channel in [public_channel, newbie_channel, builder_channel]:
                membership = ChannelMembership(
                    channel_id=channel.id,
                    player_id=1,
                    is_moderator=True
                )
                session.add(membership)

            # Create help topics
            help_topics_data = [
                {
                    "topic": "help",
                    "category": "basics",
                    "content": """HELP - Display help information

Usage: help [topic]

The help command displays information about commands, building, and other topics.
Without arguments, it shows a list of available categories.

Examples:
  help              - Show help categories
  help look         - Help on the 'look' command
  help channels     - Help on the channel system
  help commands     - List all commands

Related: help commands, help building, help softcode
                    """,
                    "aliases": "?",
                    "related_topics": "commands,building,softcode"
                },
                {
                    "topic": "commands",
                    "category": "basics",
                    "content": """COMMANDS - List of available commands

=== Basic Commands ===
  look [object]       - Look at room or object
  examine <object>    - Examine object in detail
  say <message>       - Say something (alias: ")
  pose <action>       - Pose an action (alias: :)
  go <exit>           - Go through an exit
  get <object>        - Pick up an object
  drop <object>       - Drop an object
  inventory           - See what you're carrying (alias: i)

=== Communication ===
  channel/list        - List all channels
  channel/join <name> - Join a channel
  channel/leave <name>- Leave a channel
  <alias> <message>   - Chat on a channel (e.g., "pub Hello!")
  who                 - See who's online

=== Building ===
  @create <name>      - Create a new object
  @dig <name>         - Create a new room
  @open <name>=<dest> - Create an exit
  @describe <obj>=<desc> - Set description
  @set <obj>=<attr>   - Set attribute or flag
  @destroy <object>   - Destroy an object

=== NPCs ===
  @npc/create <name>  - Create an AI-powered NPC
  @npc/personality <npc>=<desc> - Set NPC personality
  talk to <npc>=<message> - Talk to an NPC

See 'help <command>' for detailed information on each command.
                    """,
                    "aliases": "cmd,command",
                    "related_topics": "help,building,channels"
                },
                {
                    "topic": "channels",
                    "category": "communication",
                    "content": """CHANNELS - Communication system

Channels allow group communication between players.

Commands:
  channel/list              - List all available channels
  channel/join <name>       - Join a channel
  channel/leave <name>      - Leave a channel
  channel/who <name>        - See who's on a channel
  channel/create <name>     - Create a new channel (builders+)
  channel/describe <name>=<desc> - Set channel description
  <alias> <message>         - Send a message to a channel

Default Channels:
  Public (pub)  - General discussion
  Newbie (new)  - Help for new players
  Builder (build) - Building and creation

Examples:
  channel/join Public
  pub Hello everyone!
  new How do I create a room?

Related: help say, help pose
                    """,
                    "aliases": "channel,chan",
                    "related_topics": "say,pose,who"
                },
                {
                    "topic": "look",
                    "category": "basics",
                    "content": """LOOK - Examine your surroundings

Usage: look [object]

The look command lets you examine your current room or a specific object.
Without arguments, it shows your current location.

Examples:
  look              - Look at the room you're in
  look crystal      - Look at the magic crystal
  look #5           - Look at object #5

Aliases: l

Related: help examine, help @describe
                    """,
                    "aliases": "l",
                    "related_topics": "examine,@describe"
                },
                {
                    "topic": "building",
                    "category": "building",
                    "content": """BUILDING - Creating your world

Web-Pennmush allows you to build rooms, exits, and objects.

Basic Building Commands:
  @dig <name>         - Create a new room
  @open <name>=<#>    - Create an exit to room #
  @create <name>      - Create an object
  @describe <obj>=<text> - Set a description
  @set <obj>=<attr:value> - Set an attribute

Example Building Session:
  @dig Castle Entrance
  > Created: Castle Entrance(#10)

  @open north=#10
  > Created: north(#11) to Castle Entrance(#10)

  @describe here=A grand castle entrance with tall doors.
  > Description set.

  @create guard
  > Created: guard(#12)

  @describe guard=A stern castle guard.
  @set guard=HP:100

See individual command help for more details.

Related: help @dig, help @open, help @create, help softcode
                    """,
                    "aliases": "build",
                    "related_topics": "@dig,@open,@create,@describe,@set"
                },
                {
                    "topic": "softcode",
                    "category": "building",
                    "content": """SOFTCODE - MUSHcode programming

Web-Pennmush supports MUSHcode for creating dynamic content.

Function Syntax:
  [function(arg1, arg2, ...)]

Substitutions:
  %0-%9   - Arguments
  %#      - Executor object ID
  v(attr) - Get attribute from executor
  get(obj/attr) - Get attribute from object

String Functions:
  strlen, strcat, substr, trim, ucstr, lcstr

Math Functions:
  add, sub, mul, div, mod, rand

Logic Functions:
  eq, neq, gt, gte, lt, lte, and, or, not

Conditionals:
  if, ifelse, switch

Object Functions:
  name, num, loc, owner, get, v

Examples:
  think [add(10,20)]
  > 30

  @set me=SCORE:100
  think [v(SCORE)]
  > 100

  @set sword=DAMAGE:[mul(5,3)]
  examine sword
  > DAMAGE: 15

See 'help functions' for a complete list.

Related: help @set, help building
                    """,
                    "aliases": "mushcode,code",
                    "related_topics": "@set,building,functions"
                },
                {
                    "topic": "@npc/create",
                    "category": "npcs",
                    "content": """@NPC/CREATE - Create an AI-powered NPC

Usage: @npc/create <name>

Creates a new NPC (Non-Player Character) powered by AI.
The NPC will respond intelligently to player conversations.

After creation, configure the NPC:
  @npc/personality <npc>=<description>
  @npc/knowledge <npc>=<information>
  @npc/model <npc>=<model_name>

Talk to NPCs:
  talk to <npc>=<message>
  ask <npc>=<question>

Example:
  @npc/create Sage
  > Created NPC: Sage(#15)

  @npc/personality Sage=Wise and mysterious, speaks in riddles
  @npc/knowledge Sage=Knows the history of the realm and location of artifacts

  talk to Sage=Where can I find the crystal?
  > Sage says, "Seek ye the light in the darkest place..."

Note: AI features require API configuration.

Related: help @create, help talk
                    """,
                    "aliases": "@npc",
                    "related_topics": "@create,talk"
                }
            ]

            for topic_data in help_topics_data:
                help_topic = HelpTopic(**topic_data)
                session.add(help_topic)

            await session.commit()
            if os.environ.get("GOD_PASSWORD"):
                log.warning("Initial game world created. God (#1 'One') password = GOD_PASSWORD secret.")
            else:
                try:
                    pw_file = _store_god_password(god_password)
                    log.warning("Initial game world created. God (#1 'One') password written to %s "
                                "(mode 0600). Change it after first login and delete the file.", pw_file)
                except OSError:
                    log.error("Initial game world created but the God password could not be stored; "
                              "set GOD_PASSWORD and reset #1 with @password.")

    await sync_sequences(ddl_engine)
    await load_world_rng(SeedSession)


async def load_world_rng(session_factory, world=None):
    """Create the world RNG seed once, bump the epoch every start, and configure world_rng."""
    from backend.engine.world_rng import world_rng
    world = world or world_rng
    async with session_factory() as session:
        seed_row = await session.get(WorldSetting, "rng_seed")
        if seed_row is None:
            seed_row = WorldSetting(key="rng_seed", value=str(secrets.randbits(63)))
            session.add(seed_row)
        epoch_row = await session.get(WorldSetting, "rng_epoch")
        if epoch_row is None:
            epoch_row = WorldSetting(key="rng_epoch", value="0")
            session.add(epoch_row)
        epoch_row.value = str(int(epoch_row.value) + 1)
        await session.commit()
        world.configure(int(seed_row.value), int(epoch_row.value))
    log.info("world rng epoch %d", world.epoch)  # never log the seed
    return world


async def close_db():
    """Close database connections"""
    await engine.dispose()
