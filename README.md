# Web-Pennmush

![Build](https://github.com/kochj23/Web-Pennmush/actions/workflows/build.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)
![Version](https://img.shields.io/badge/version-3.0.0-brightgreen.svg)

A modern, web-based MUSH (Multi-User Shared Hallucination) server inspired by the classic [PennMUSH](https://github.com/pennmush/pennmush). Built with Python, FastAPI, and WebSockets for real-time multiplayer text-based gaming. Supports AI-powered NPCs via local Ollama or MLX backends -- no cloud APIs required.

---

## Architecture

```
                         +-------------------------------+
                         |        Web Browser            |
                         |  (HTML5 / CSS / JavaScript)   |
                         +-------+-------------+---------+
                                 |             |
                         HTTP GET/POST    WebSocket (ws://)
                                 |             |
              +------------------+-------------+------------------+
              |              FastAPI  (uvicorn)                    |
              |                                                   |
              |   /             -> index.html (game client)       |
              |   /admin        -> admin.html (dashboard)         |
              |   /ws           -> WebSocket handler              |
              |   /api/*        -> REST endpoints                 |
              |   /health       -> health check                   |
              +--+----------------------------+---+---------------+
                 |                            |   |
       +---------+--------+       +-----------+   +----------+
       |  Command Parser  |       | REST API  |   | Security |
       |  50+ commands     |       | /api/*   |   | Module   |
       +--+--+--+--+--+--+       +-----------+   +----------+
          |  |  |  |  |  |           |
    +-----+  |  |  |  |  +------+   |
    |        |  |  |  |         |   |
+---+---+ +--+--+ | +--+--+ +--+--+ |
|Objects| |Soft-| | |Chan-| |Locks| |
|Manager| |code | | |nels | |Mgr  | |
+-------+ |Eval | | +-----+ +-----+ |
          +-----+ |                  |
   +---------+-+--+--+---------+     |
   |         | |     |         |     |
+--+--+ +---++ +----++ +------++ +---+-------+
|Mail | |Page| |Quest| |Economy| |Moderation |
|Mgr  | |Mgr | |Mgr  | |Mgr   | |Mgr        |
+-----+ +----+ +-----+ +------+ +-----------+
   |       |      |        |          |
   +---+---+------+--------+----------+
       |
+------+-------+       +----------------+
| SQLAlchemy   |       | AI Manager     |
| (async)      |       | Ollama / MLX   |
+------+-------+       +-------+--------+
       |                        |
+------+-------+       +-------+--------+
| SQLite (dev) |       | Local LLM      |
| PostgreSQL   |       | (llama2, etc.) |
+--------------+       +----------------+
```

---

## Features

### Core MUSH Engine

- **Unified Object System** -- Everything is an object (rooms, exits, things, players) following the PennMUSH model. Objects carry attributes, flags, and ownership.
- **Real-time Multiplayer** -- WebSocket connections provide live communication between all connected players.
- **Room Navigation** -- Move through interconnected rooms using named exits.
- **Object Manipulation** -- Create, examine, pick up, drop, describe, and destroy objects.
- **Player Inventory** -- Carry objects with you as you explore.

### Softcode Interpreter

A full MUSHcode interpreter supporting user-created scripting:

- 30+ built-in functions covering string manipulation, math, logic, conditionals, and object queries
- `[function(args)]` evaluation syntax with nested function calls
- Variable substitutions: `%0`-`%9`, `%#`, `v(attr)`, `get(obj/attr)`
- Custom attributes on any object
- Extended softcode with list operations, regex, hashing, and more

### Channel System

- Create and join group chat channels
- Default channels: Public, Newbie, Builder
- Channel aliases for quick messaging (e.g., `pub Hello!`)
- Member tracking with `channel/who`

### Help System

- In-game searchable documentation covering all commands
- Organized by category: commands, building, softcode, NPCs
- Context-sensitive related topic suggestions
- Alias support and usage examples for every entry

### Visual Room Map

- Interactive SVG graph showing connected rooms
- Real-time updates as you explore
- Clickable nodes for room inspection
- Configurable display radius

### AI-Powered NPCs

- Local AI integration via Ollama (all platforms) or MLX (Apple Silicon)
- No cloud API keys needed -- runs entirely on your machine
- Personality and knowledge systems per NPC
- Conversation memory across interactions
- AI-powered game guide that answers player questions contextually

### Lock System

- Complex access control expressions with AND (`&`), OR (`|`), NOT (`!`) operators
- Multiple lock types: use, enter, get, teleport
- Attribute-based locks (`HP:>50`), flag-based locks (`WIZARD|ROYAL`), object ID locks (`#123`)
- Parenthetical grouping for compound expressions

### Mail and Page Systems

- Asynchronous mail with subject lines and inbox management for offline messaging
- Real-time page (direct message) system for online players with history

### Quest System

- Structured multi-step quests with progress tracking
- Credit rewards upon completion
- Repeatable quests
- Wizard-only quest creation tools

### Economy System

- Credit-based currency with player-to-player transfers
- Full transaction history and audit trail
- Admin grant commands and leaderboard

### Moderation Tools

- Ban system (permanent and temporary) with audit logging
- Kick and muzzle commands
- Wizard/God permission enforcement on all moderation actions

### Admin Dashboard

- Web interface at `/admin` with real-time server statistics
- Online player monitoring, ban management, economy overview, quest stats
- Quick action buttons for broadcasts, grants, and quest creation
- Auto-refresh every 30 seconds

### Security

- **Password hashing** -- bcrypt via passlib
- **WebSocket authentication** -- secure login before command execution
- **Permission hierarchy** -- God, Wizard, Royal, and user levels
- **Rate limiting** -- per-endpoint limits on login, commands, API, channels, and AI
- **Input validation** -- length limits, character filtering, SQL injection detection
- **XSS protection** -- HTML entity escaping on all output
- **AI prompt injection protection** -- jailbreak pattern detection and sanitization
- **Session timeout** -- idle connection enforcement
- **Security logging** -- failed logins, rate limit violations, suspicious input, admin actions

---

## Project Structure

```
Web-Pennmush/
|-- backend/
|   |-- main.py                  # FastAPI entry point, lifespan events
|   |-- config.py                # Pydantic settings (host, port, DB, AI)
|   |-- database.py              # Async SQLAlchemy engine, session factory, init_db
|   |-- models.py                # ORM models (DBObject, Attribute, Channel, Quest, etc.)
|   |-- security.py              # RateLimiter, InputValidator, SecurityLogger
|   |-- api/
|   |   |-- rest.py              # REST endpoints (/api/players, /api/objects, etc.)
|   |   |-- websocket.py         # WebSocket connection manager and handler
|   |-- engine/
|       |-- objects.py           # Object creation, lookup, manipulation
|       |-- commands.py          # Command parser and 50+ command handlers
|       |-- softcode.py          # MUSHcode interpreter (4,000+ lines)
|       |-- softcode_complete.py # Extended softcode functions
|       |-- softcode_extended.py # Additional softcode library
|       |-- softcode_phase2_4.py # Phase 2-4 softcode extensions
|       |-- channels.py          # Channel and help system managers
|       |-- ai_manager.py        # Ollama/MLX AI backend detection and queries
|       |-- locks.py             # Lock expression parser and evaluator
|       |-- mail.py              # Async mail system
|       |-- pages.py             # Real-time direct messaging
|       |-- moderation.py        # Ban, kick, muzzle managers
|       |-- quests.py            # Quest creation and progress tracking
|       |-- economy.py           # Currency, transfers, transactions
|-- frontend/
|   |-- index.html               # Main game client (multi-pane layout)
|   |-- admin.html               # Admin dashboard
|   |-- css/
|   |   |-- style.css            # Dark terminal-inspired theme
|   |-- js/
|       |-- app.js               # Application logic and command dispatch
|       |-- websocket.js         # WebSocket manager with reconnection
|       |-- ui.js                # UI helpers, command history, formatting
|       |-- roommap.js           # Interactive SVG room map renderer
|-- .github/
|   |-- workflows/
|       |-- build.yml            # CI build workflow
|-- requirements.txt             # Python dependencies
|-- AI_SETUP.md                  # Detailed AI backend setup guide
|-- CHANGELOG.md                 # Version history
|-- SECURITY.md                  # Security policy and vulnerability reporting
|-- LICENSE                      # MIT License
```

Total codebase: approximately 13,800 lines across Python backend and JavaScript frontend.

---

## Installation

### Prerequisites

- Python 3.9 or higher
- pip

### Quick Start

```bash
git clone https://github.com/kochj23/Web-Pennmush.git
cd Web-Pennmush
pip install -r requirements.txt
python -m backend.main
```

Open your browser to `http://localhost:8000`.

Default admin account:

- Username: `One`
- Password: `potrzebie`

Change the default password immediately after first login.

### AI Setup (Optional)

AI enables intelligent NPCs and the in-game guide system. Two backends are supported:

**Ollama (all platforms):**

```bash
# Install from https://ollama.ai, then:
ollama pull llama2
python -m backend.main
```

**MLX (Apple Silicon only):**

```bash
pip install mlx-lm
python -m backend.main
```

Verify in-game:

```
@ai/status
guide How do I create a room?
```

See [AI_SETUP.md](AI_SETUP.md) for full instructions.

---

## Usage

### Movement and Interaction

```
look [object]       - Look at the current room or a specific object
examine <object>    - Examine an object in detail
say <message>       - Speak aloud (alias: ")
pose <action>       - Emote an action (alias: :)
go <exit>           - Move through an exit (or type the exit name directly)
get <object>        - Pick up an object
drop <object>       - Drop an object from inventory
inventory           - List carried objects (alias: i)
who                 - List connected players
help [topic]        - Show help (alias: ?)
```

### Building

```
@dig Castle Entrance            - Create a new room
@open north=#10                 - Create an exit to room #10
@describe here=A grand hall.    - Set a description on the current room
@create magic sword             - Create a new object
@set magic sword=POWER:15       - Set a custom attribute
@destroy magic sword            - Remove an object
```

### Softcode

```
think [strlen(Hello)]                          -> 5
think [add(10,20,30)]                          -> 60
think [if(1,Yes,No)]                           -> Yes
think [name(#0)]                               -> Room Zero
@set me=HP:100
think [v(HP)]                                  -> 100
@set magic_sword=DAMAGE:[mul([v(POWER)],2)]
```

### Channels

```
channel/list                    - List all channels
channel/join Public             - Join a channel
pub Hello everyone!             - Chat via channel alias
channel/who Public              - See channel members
channel/create MyChannel=mc     - Create a channel with alias
```

### AI NPCs

```
@npc/create Sage
@npc/personality Sage=Wise wizard who speaks in riddles
@npc/knowledge Sage=Knows the location of ancient artifacts
talk to Sage=Where can I find the crystal?
guide How do I build a room?
```

### Locks

```
@lock sword/use=#123|WIZARD
@lock door/enter=HP:>50&QUEST_COMPLETE:1
@lock treasure/get=!THIEF&(WIZARD|ROYAL)
@unlock sword/use
@lock/list sword
```

### Mail and Pages

```
@mail Alice=Meeting Tonight/Let's meet at 8pm
@mail/list
@mail/read 1
page Bob=Are you ready for the quest?
page/list
```

### Quests and Economy

```
quest/list
quest/start Find the Crystals
quest/progress
balance
give Alice=100
transactions
```

### Moderation (Wizard only)

```
@ban Spammer=Flooding chat/7
@unban Spammer
@kick IdleUser=Freeing slot
@muzzle Disruptive
@ban/list
```

### Admin Dashboard

Open `http://localhost:8000/admin` in your browser for real-time server monitoring, player management, economy stats, and quick admin actions.

---

## REST API

```
POST   /api/players/register           - Create a new player account
GET    /api/players                     - List all players
GET    /api/players/{id}                - Get player information
GET    /api/objects/{id}                - Get object information
GET    /api/rooms/{id}/contents         - Get room contents
GET    /api/rooms/map?center_room_id=0&radius=10  - Get room map graph data
GET    /api/stats                       - Get server statistics
GET    /health                          - Health check
```

## WebSocket Protocol

Endpoint: `ws://localhost:8000/ws`

Send:

```json
{ "type": "command", "command": "look" }
```

Response types: `welcome`, `output`, `error`, `auth_required`.

---

## Configuration

All settings are managed in `backend/config.py` via Pydantic and can be overridden with environment variables or a `.env` file:

| Setting                      | Default                             | Description                     |
|------------------------------|-------------------------------------|---------------------------------|
| `HOST`                       | `0.0.0.0`                           | Server bind address             |
| `PORT`                       | `8000`                              | Server port                     |
| `DATABASE_URL`               | `sqlite+aiosqlite:///./webpennmush.db` | Database connection string   |
| `SECRET_KEY`                 | (change in production)              | JWT signing key                 |
| `STARTING_ROOM`              | `0`                                 | Default room for new players    |
| `MAX_COMMAND_LENGTH`         | `8192`                              | Maximum command input length    |
| `IDLE_TIMEOUT_MINUTES`       | `30`                                | Idle session timeout            |
| `AI_BACKEND`                 | `auto`                              | AI backend: auto, ollama, mlx, none |
| `AI_DEFAULT_MODEL`           | `llama2`                            | Default LLM for NPCs and guide |
| `OLLAMA_BASE_URL`            | `http://localhost:11434`            | Ollama server URL               |

---

## Database

SQLite is the default for development. PostgreSQL is recommended for production.

### Initial World

The database is automatically seeded on first run with:

- **Room Zero (#0)** -- The Void
- **Admin Account (#1)** -- "One" (God-level permissions)
- **Central Plaza (#2)** -- Starting room for new players
- **Exits (#3, #4)** -- Portal connections between rooms
- **Magic Crystal (#5)** -- Sample object with attributes

### PostgreSQL Setup

```bash
pip install asyncpg
```

Set `DATABASE_URL` in your `.env` or `config.py`:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost/webpennmush
```

---

## Production Deployment

1. Set a strong, unique `SECRET_KEY` (environment variable or `.env`)
2. Change the default admin password immediately
3. Set `DEBUG=False`
4. Use PostgreSQL instead of SQLite
5. Terminate TLS upstream (reverse proxy with HTTPS/WSS)
6. Review rate limiting thresholds in `backend/security.py`

---

## Development

### Running in Development Mode

```bash
export DEBUG=True
python -m backend.main
```

Auto-reload is enabled when `DEBUG=True`.

### Adding a New Command

In `backend/engine/commands.py`:

```python
async def cmd_mycommand(self, player: DBObject, args: str) -> str:
    """My custom command."""
    return f"You executed mycommand with args: {args}"

# In _register_commands():
self.register_command("mycommand", self.cmd_mycommand, ["mc"])
```

### Adding a Softcode Function

In `backend/engine/softcode.py`:

```python
async def func_myfunction(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
    """My custom function."""
    return "result"

# In _register_functions():
self.register_function("myfunction", self.func_myfunction)
```

---

## Technical Details

| Component           | Technology                                          |
|---------------------|-----------------------------------------------------|
| Backend framework   | FastAPI 0.109 on uvicorn                            |
| Database ORM        | SQLAlchemy 2.0 (async) with aiosqlite               |
| Authentication      | bcrypt (passlib) + python-jose JWT                   |
| WebSockets          | FastAPI native WebSocket support                     |
| Validation          | Pydantic 2.5                                         |
| AI backends         | Ollama (cross-platform), MLX (Apple Silicon)         |
| Frontend            | Vanilla HTML5 / CSS / JavaScript (no framework)      |
| Room map            | SVG rendering via roommap.js                         |
| Database tables     | 15 (objects, attributes, channels, quests, bans, etc.) |
| Registered commands | 50+                                                  |
| Softcode functions  | 30+                                                  |

---

## Acknowledgments

- Inspired by [PennMUSH](https://github.com/pennmush/pennmush) by the PennMUSH development team
- Built with [FastAPI](https://fastapi.tiangolo.com/)
- WebSocket serving via [uvicorn](https://www.uvicorn.org/)

---

## Contributing

Contributions are welcome. Fork the repository, create a feature branch, and open a pull request.

```bash
git checkout -b feature/your-feature
git commit -m "feat: Add your feature"
git push origin feature/your-feature
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Author

Written by **Jordan Koch** (GitHub: [@kochj23](https://github.com/kochj23))

---

> **Disclaimer:** This is a personal project created on my own time. It is not affiliated with, endorsed by, or representative of my employer.
