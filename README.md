# Web-Pennmush

A modern, web-based MUSH (Multi-User Shared Hallucination) server inspired by the classic [PennMUSH](https://github.com/pennmush/pennmush). Built with Python, FastAPI, and WebSockets for real-time multiplayer text-based gaming.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)

## Features

### Core MUSH Engine
- **Unified Object System**: Everything is an object (rooms, exits, things, players)
- **Real-time Multiplayer**: WebSocket-based live communication
- **Room Navigation**: Move through interconnected rooms with exits
- **Object Manipulation**: Create, examine, pick up, and drop objects
- **Player Inventory**: Carry objects with you

### Softcode System
- **MUSHcode Interpreter**: Write custom scripts with familiar MUSH syntax
- **Function Library**: 30+ built-in functions (string, math, logic, conditionals, object manipulation)
- **Attribute System**: Attach custom attributes to any object
- **Function Evaluation**: `[function(args)]` syntax with nested evaluation
- **Variable Substitutions**: `%0-%9`, `%#`, `v(attr)`, `get(obj/attr)`

### Building Commands
- `@create <name>` - Create new objects
- `@dig <name>` - Create new rooms
- `@open <name>=<destination>` - Create exits between rooms
- `@describe <object>=<description>` - Set descriptions
- `@set <object>=<attribute:value>` - Set attributes and flags
- `@destroy <object>` - Remove objects

### Modern Web Interface
- **Multi-pane Layout**: Separate areas for output, input, room info, and player list
- **Terminal-inspired Design**: Dark theme with syntax highlighting
- **Command History**: Navigate with ↑/↓ arrow keys
- **Quick Commands**: One-click access to common commands
- **Responsive Design**: Works on desktop, tablet, and mobile

### Security Features 🔒 **NEW: Production-Ready!**
- **Password Hashing**: Bcrypt-based secure password storage
- **WebSocket Authentication**: Secure authentication before allowing commands
- **Permission System**: God, Wizard, Royal, and user-level permissions
- **Rate Limiting**: Prevents brute force, DoS, and spam attacks
- **Input Validation**: Validates all user input, prevents command injection
- **XSS Protection**: Sanitizes output, escapes dangerous content
- **AI Prompt Injection Protection**: Detects and blocks jailbreak attempts
- **Session Timeout**: Enforces idle timeout on connections
- **Security Logging**: Tracks failed logins, suspicious activity, admin actions
- **CSRF Protection Ready**: Framework in place for CSRF tokens

### NEW: Channel System 📢
- **Group Communication**: Create and join channels for organized chat
- **Default Channels**: Public, Newbie, and Builder channels pre-configured
- **Channel Aliases**: Quick shortcuts (e.g., `pub Hello!` to chat on Public)
- **Channel Management**: Create, join, leave, and list channels
- **Member Tracking**: See who's on each channel with `channel/who`

### NEW: Comprehensive Help System 📚
- **In-Game Documentation**: Searchable help topics covering all commands
- **Category Organization**: Commands, building, softcode, NPCs, and more
- **Context-Sensitive**: Related topics suggested for each help entry
- **Alias Support**: Find help by command aliases
- **Examples Included**: Every help topic includes usage examples

### NEW: Visual Room Map 🗺️
- **Interactive Graph**: See connected rooms as an interactive network
- **Real-time Updates**: Map refreshes as you explore
- **Clickable Nodes**: Click rooms on the map to view them
- **Spatial Awareness**: Understand the layout of the game world
- **Customizable Radius**: Adjust how many rooms to display

### NEW: AI-Powered NPCs 🤖
- **Local AI Integration**: Uses Ollama or MLX (no cloud APIs needed!)
- **Intelligent Characters**: NPCs respond with context-aware conversations
- **Personality System**: Define unique personalities for each NPC
- **Knowledge Base**: Give NPCs specific information to share
- **Natural Conversations**: Talk to NPCs using natural language
- **Conversation Memory**: NPCs remember your previous messages
- **Easy Configuration**: Set personality and knowledge with simple commands
- **Game Guide**: AI-powered help system answers player questions
- **Multiple Backends**: Supports Ollama (all platforms) and MLX (Apple Silicon)

### NEW: Rich Text Features ✨
- **Structured Output**: Commands return formatted data for better display
- **Clickable Elements**: Room names, objects, and exits are interactive
- **Visual Enhancements**: Better formatting and organization
- **Room Map Integration**: See your location visually
- **Channel Messages**: Formatted with colors and sender information

### NEW: Advanced Lock System 🔐
- **Complex Access Control**: Powerful lock expressions with AND, OR, NOT operators
- **Multiple Lock Types**: use, enter, get, teleport, and more
- **Attribute-Based Locks**: Lock based on player stats (`HP:>50`)
- **Flag-Based Locks**: Require specific flags (`WIZARD|ROYAL`)
- **Lock Commands**: `@lock`, `@unlock`, `@lock/list`
- **Examples**: `@lock/use sword=#123|WIZARD`, `@lock/enter door=HP:>50&QUEST_COMPLETE:1`

### NEW: Mail System 📬
- **Async Messaging**: Send mail to offline players
- **Subject Lines**: Organize messages with subjects
- **Inbox Management**: List, read, and delete mail
- **Mail Commands**: `@mail`, `@mail/list`, `@mail/read`, `@mail/delete`
- **Full Implementation**: Complete mail system ready to use

### NEW: Page System 📟
- **Direct Messages**: Real-time pages to online players
- **Page History**: View recent pages sent and received
- **Commands**: `page <player>=<message>`, `page/list`
- **Online Check**: Suggests mail if recipient is offline

### NEW: Moderation Tools 👮
- **Ban System**: Ban players permanently or temporarily
- **Kick Command**: Disconnect disruptive players
- **Muzzle System**: Prevent players from using chat
- **Ban Management**: `@ban`, `@unban`, `@ban/list`
- **Permission Checks**: Only wizards and admins can moderate
- **Audit Trail**: All moderation actions logged

### NEW: Quest System 🎯
- **Structured Quests**: Create quests with multiple steps
- **Progress Tracking**: Track player progress on quests
- **Rewards**: Grant credits upon quest completion
- **Repeatable Quests**: Quests can be repeated
- **Quest Commands**: `quest/list`, `quest/start`, `quest/progress`, `@quest/create`
- **Quest Creation**: Wizards can create quests with `@quest/create`

### NEW: Economy System 💰
- **Currency System**: Players earn and spend credits
- **Transfer Credits**: Give credits to other players
- **Transaction History**: Track all economic activity
- **Admin Controls**: Grant credits with `@economy/grant`
- **Leaderboard**: See richest players with `@economy/stats`
- **Quest Rewards**: Quests automatically grant credits
- **Economy Commands**: `balance`, `give`, `transactions`

### NEW: Admin Dashboard 🛡️
- **Web Interface**: Access at `/admin`
- **Real-time Stats**: Server statistics, online players, active bans
- **Quick Actions**: Broadcast messages, create quests, grant credits
- **Economy Overview**: Richest players, transaction volume
- **Quest Management**: View active quests
- **AI Status**: Check AI backend configuration
- **Auto-refresh**: Dashboard updates every 30 seconds

## Installation

### Prerequisites
- Python 3.9 or higher
- pip (Python package manager)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/kochj23/Web-Pennmush.git
   cd Web-Pennmush
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the server**
   ```bash
   python -m backend.main
   ```

4. **Open your browser**
   Navigate to: `http://localhost:8000`

5. **Log in**
   - Default admin account:
     - Username: `One`
     - Password: `potrzebie`
   - **IMPORTANT**: Change this password immediately after first login!

### AI Setup (Optional but Recommended)

Enable intelligent NPCs and AI game guide:

**Option 1: Ollama (All platforms)**
```bash
# Install Ollama from https://ollama.ai
# Then pull a model:
ollama pull llama2

# Restart Web-Pennmush
python -m backend.main
```

**Option 2: MLX (Apple Silicon only)**
```bash
pip install mlx-lm
python -m backend.main
```

**Verify AI is working:**
```bash
# In the game:
@ai/status
guide How do I create a room?
```

📖 **Full AI setup guide**: See [AI_SETUP.md](AI_SETUP.md) for detailed instructions

## Project Structure

```
Web-Pennmush/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration settings
│   ├── database.py          # Database connection and initialization
│   ├── models.py            # SQLAlchemy models (objects, attributes, locks)
│   ├── engine/              # Core MUSH engine
│   │   ├── objects.py       # Object manipulation
│   │   ├── commands.py      # Command parser
│   │   └── softcode.py      # Softcode interpreter
│   └── api/                 # API routes
│       ├── rest.py          # REST endpoints
│       └── websocket.py     # WebSocket handler
├── frontend/
│   ├── index.html           # Main HTML5 interface
│   ├── css/
│   │   └── style.css        # Styles
│   └── js/
│       ├── app.js           # Main application logic
│       ├── websocket.js     # WebSocket manager
│       └── ui.js            # UI helpers
├── requirements.txt         # Python dependencies
├── LICENSE                  # MIT License
└── README.md               # This file
```

## Usage

### Basic Commands

```
look [object]       - Look at room or object
examine <object>    - Examine object in detail
say <message>       - Say something (or use ")
pose <action>       - Pose an action (or use :)
go <exit>           - Go through an exit (or just type exit name)
get <object>        - Pick up an object
drop <object>       - Drop an object
inventory           - See what you're carrying
who                 - See who's online
help                - Show help
```

### Building Your World

```
@dig Castle Entrance
# Created: Castle Entrance(#10)

@open north=#10
# Created: north(#11) to Castle Entrance(#10)

@describe here=You stand at the entrance to a grand castle.
# Description set on Castle Entrance(#10)

@create magic sword
# Created: magic sword(#12)

@set magic sword=POWER:15
# Attribute POWER set on magic sword(#12)
```

### Softcode Examples

```
# String manipulation
think [strlen(Hello)]
# Output: 5

# Math
think [add(10,20,30)]
# Output: 60

# Conditionals
think [if(1,Yes,No)]
# Output: Yes

# Object functions
think [name(#0)]
# Output: Room Zero

# Attribute access
@set me=HP:100
think [v(HP)]
# Output: 100

# Complex expressions
@set magic_sword=DAMAGE:[mul([v(POWER)],2)]
```

### Using Channels

```bash
# List all available channels
channel/list

# Join a channel
channel/join Public

# Chat on a channel using its alias
pub Hello everyone!

# See who's on a channel
channel/who Public

# Leave a channel
channel/leave Public

# Create your own channel
channel/create MyChannel=mc
mc This is my custom channel!
```

### Using the Help System

```bash
# Show help categories
help

# Get help on a specific command
help look
help channel/join

# See all commands
help commands

# Learn about building
help building

# Get softcode help
help softcode
```

### Using AI-Powered NPCs

```bash
# Create an NPC
@npc/create Sage

# Set the NPC's personality
@npc/personality Sage=Wise and mysterious wizard who speaks in riddles

# Give the NPC knowledge
@npc/knowledge Sage=Knows the location of ancient artifacts and the history of the realm

# Talk to the NPC (AI responds intelligently!)
talk to Sage=Where can I find the crystal?
# Sage says, "Seek ye the luminous stone within the cave kissed by sun's first light, where shadows dare not dwell."

talk to Sage=Can you teach me magic?
# Sage says, "Magic flows through those who seek wisdom with pure intent. Begin with simple incantations, young apprentice."

# Alternative syntax
ask Sage=What do you know about magic?
# Sage says, "The ancient arts require patience and understanding. Each spell is a conversation with the forces of nature."
```

**NPCs remember your conversation!** They use local AI (Ollama or MLX) for intelligent responses.

### Using the AI Game Guide

```bash
# Ask the AI guide for help
guide How do I create a room?
# === AI Guide ===
# To create a new room, use the @dig command followed by the room name.
# For example: @dig Castle Entrance
# Then use @open to create exits connecting rooms...

guide What are channels?
# === AI Guide ===
# Channels are group chat rooms for player communication. Join a channel
# with 'channel/join Public' and chat with 'pub <message>'...

# The guide knows your current location and inventory
guide What should I do here?
# === AI Guide ===
# You're in Central Plaza. Try exploring by typing exit names like 'portal'.
# You can also examine objects with 'look <object>'...
```

**Note**: AI features require Ollama or MLX. See [AI_SETUP.md](AI_SETUP.md) for installation.

### Using the Lock System

```bash
# Lock an object so only specific players can use it
@lock sword/use=#123|WIZARD
# Only player #123 OR wizards can use the sword

# Lock a door with attribute requirement
@lock door/enter=HP:>50&QUEST_COMPLETE:1
# Need HP>50 AND QUEST_COMPLETE:1 to enter

# Complex lock with grouping
@lock treasure/get=!THIEF&(WIZARD|ROYAL)
# Can get if NOT a thief AND (wizard OR royal)

# Remove a lock
@unlock sword/use

# List all locks on an object
@lock/list sword
```

### Using the Mail System

```bash
# Send mail to a player
@mail Alice=Meeting Tonight/Let's meet in Central Plaza at 8pm

# List your inbox
@mail/list
# Shows all mail with ID, sender, subject, date, status

# Read a message
@mail/read 1
# Displays full message

# Delete mail
@mail/delete 1
```

### Using the Page System

```bash
# Send a page (direct message) to online player
page Bob=Are you available to help with the quest?
# You paged Bob: Are you available to help with the quest?

# View recent pages
page/list
# Shows last 10 pages sent and received
```

### Using Moderation Tools

```bash
# Ban a player for 7 days
@ban Spammer=Flooding chat with spam/7
# Spammer(#42) has been banned for 7 days. Reason: Flooding chat with spam

# Permanent ban
@ban TrollUser=Harassment and abuse
# TrollUser(#43) has been banned permanently.

# Unban a player
@unban Spammer
# Spammer(#42) has been unbanned.

# Muzzle a player (prevent chat)
@muzzle Annoying=Temporary mute for spam
# Annoying(#44) has been muzzled.

# Unmuzzle
@unmuzzle Annoying

# Kick a player (disconnect)
@kick IdleUser=Freeing up connection slot

# List active bans
@ban/list
```

### Using the Quest System

```bash
# List available quests
quest/list
# === Available Quests ===
# Find the Crystals (ID: 1)
#   Retrieve the three ancient crystals scattered across the realm
#   Reward: 1000 credits

# Start a quest
quest/start Find the Crystals
# Quest started: Find the Crystals
# Use 'quest/progress' to track your progress.

# Check your progress
quest/progress
# === Your Quests ===
# Active:
#   Find the Crystals - Step 1

# Create a quest (wizards only)
@quest/create Rescue the Princess=Save the princess from the dragon/500
# Quest created: Rescue the Princess (ID: 2)

# Add steps to quest
@quest/addstep Rescue the Princess=1/Travel to the Dragon's Lair
@quest/addstep Rescue the Princess=2/Defeat the dragon
@quest/addstep Rescue the Princess=3/Escort the princess to safety
```

### Using the Economy System

```bash
# Check your balance
balance
# Your balance: 500 credits

# Give credits to another player
give Alice=100
# You gave 100 credits to Alice. Your new balance: 400 credits

# View transaction history
transactions
# === Transaction History ===
# Shows recent transactions

# Grant credits (admin only)
@economy/grant Bob=1000
# Granted 1000 credits to Bob. New balance: 1000 credits

# View richest players
@economy/stats
# === Economy Statistics ===
# Richest Players:
# 1      Alice     5000
# 2      Bob       3500
```

### Accessing the Admin Dashboard

Open your browser to: `http://localhost:8000/admin`

Features:
- Real-time server statistics
- Online player list
- Active ban management
- Economy leaderboard
- Quest overview
- Quick action buttons

### Viewing the Room Map

The room map is automatically displayed in the left sidebar. It shows:
- All rooms connected to your current location
- Exits between rooms as lines
- Your current room highlighted in green
- Click any room on the map to view information about it
- Click "Refresh Map" to update the visualization

## REST API

Web-Pennmush exposes a REST API for account management and queries:

- `POST /api/players/register` - Create a new player account
- `GET /api/players` - List all players
- `GET /api/players/{id}` - Get player information
- `GET /api/objects/{id}` - Get object information
- `GET /api/rooms/{id}/contents` - Get room contents
- `GET /api/rooms/map?center_room_id=0&radius=10` - Get room map graph data
- `GET /api/stats` - Get server statistics

## WebSocket Protocol

WebSocket endpoint: `ws://localhost:8000/ws`

### Message Format

```json
{
  "type": "command",
  "command": "look"
}
```

### Response Types

- `welcome` - Authentication successful
- `output` - Command output
- `error` - Error message
- `auth_required` - Authentication needed

## Configuration

Edit `backend/config.py` to customize:

```python
HOST: str = "0.0.0.0"           # Server host
PORT: int = 8000                 # Server port
DATABASE_URL: str = "..."        # Database connection
STARTING_ROOM: int = 2           # Default starting room
MAX_COMMAND_LENGTH: int = 8192   # Max command length
```

## Database

Web-Pennmush uses SQLite by default, with full support for PostgreSQL and other SQLAlchemy-compatible databases.

### Initial World

The database is automatically initialized with:
- **Room Zero (#0)**: The Void - where all journeys begin
- **Admin Account (#1)**: "One" (God-level permissions)
- **Central Plaza (#2)**: Starting room for new players
- **Exits (#3, #4)**: Portal connections between rooms
- **Magic Crystal (#5)**: Sample object with attributes

## Development

### Running in Development Mode

```bash
# Enable debug mode
export DEBUG=True

# Run with auto-reload
python -m backend.main
```

### Adding New Commands

Edit `backend/engine/commands.py`:

```python
async def cmd_mycommand(self, player: DBObject, args: str) -> str:
    """My custom command"""
    return f"You executed mycommand with args: {args}"

# Register in _register_commands():
self.register_command("mycommand", self.cmd_mycommand, ["mc"])
```

### Adding Softcode Functions

Edit `backend/engine/softcode.py`:

```python
async def func_myfunction(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
    """My custom function"""
    return "result"

# Register in _register_functions():
self.register_function("myfunction", self.func_myfunction)
```

## Deployment

### Production Settings

1. Change the secret key in `config.py` or set `SECRET_KEY` environment variable
2. Change the default admin password
3. Use a production database (PostgreSQL recommended)
4. Enable HTTPS/WSS
5. Set `DEBUG=False`

### Using PostgreSQL

```bash
# Install PostgreSQL driver
pip install asyncpg

# Update DATABASE_URL in config.py
DATABASE_URL = "postgresql+asyncpg://user:password@localhost/webpennmush"
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Roadmap

- [ ] Advanced lock system (lock evaluation)
- [ ] Mail system (player-to-player messages)
- [ ] Channel system (public/private chat channels)
- [ ] Help system (command documentation)
- [ ] @parent system (object inheritance)
- [ ] Zone system (area management)
- [ ] Quota system (building limits)
- [ ] Admin commands (@teleport, @force, @halt)
- [ ] Bulletin board system
- [ ] More softcode functions (list operations, regex, etc.)
- [ ] Mobile app (React Native)
- [ ] Map visualization
- [ ] Rich text formatting (ANSI colors, markdown)
- [ ] Voice integration
- [ ] AI-powered NPCs

## Acknowledgments

- Inspired by [PennMUSH](https://github.com/pennmush/pennmush) by the PennMUSH development team
- Built with [FastAPI](https://fastapi.tiangolo.com/)
- WebSocket support via [uvicorn](https://www.uvicorn.org/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Jordan Koch** (GitHub: [@kochj23](https://github.com/kochj23))

## Support

- GitHub Issues: https://github.com/kochj23/Web-Pennmush/issues
- Email: [Contact via GitHub]

---

**Built with passion for text-based multiplayer gaming** ❤️

---

**Last Updated:** January 22, 2026
**Status:** ✅ Production Ready
