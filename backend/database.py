"""
Web-Pennmush Database Connection and Initialization
Author: Jordan Koch (GitHub: kochj23)
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from backend.models import Base, DBObject, ObjectType, Attribute, Channel, ChannelMembership, HelpTopic
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
            print("Initial game world created successfully!")
            print("  - Room Zero (#0): The Void")
            print("  - God/Admin (#1): One (password: potrzebie)")
            print("  - Central Plaza (#2): Starting room")
            print("  - Exits (#3, #4): Portal connections")
            print("  - Magic Crystal (#5): Sample object")
            print("  - Default Channels: Public, Newbie, Builder")
            print(f"  - Help Topics: {len(help_topics_data)} topics loaded")
            print("\nIMPORTANT: Change the God password after first login!")


async def close_db():
    """Close database connections"""
    await engine.dispose()
