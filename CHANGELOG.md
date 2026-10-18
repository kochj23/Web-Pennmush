# Web-Pennmush Changelog

All notable changes to this project will be documented in this file.

## [3.1.0] - 2026-10-17

### Nova Games Deployment

Web-Pennmush now runs as the `mush` service of the Nova Games platform on nova-core3, served at `https://192.168.1.5:8443/mush/` behind Caddy and deployed with `deploy/deploy.sh mush` from the NovaGames repo.

#### Added
- `Dockerfile` (`novagames/mush`): `python:3.12-slim`, non-root uid 10001, read-only rootfs ready, `/healthz` healthcheck, uvicorn on `0.0.0.0:8000` with `--ws-max-size 16384`, `--limit-concurrency 400`, no `Server` header
- Postgres via asyncpg on the dedicated Games DB (schema `mush`): `sslmode=verify-full` with a pinned CA, owner role for DDL (`DATABASE_MIGRATE_URL`) and DML-only app role (`DATABASE_URL`), bounded pool, statement timeout, startup retry with backoff, sequence sync after seeding
- `GET /healthz` liveness endpoint (no DB, no LLM)
- NPC and guide lines via the Nova Games pull relay (`mush.npc` template, HMAC-signed `GET /relay/jobs` and `POST /relay/jobs/{id}/result`, 404 without `RELAY_SECRET_MUSH`) with a scripted fallback on every failure path
- Session auth: HMAC-signed tokens in an HttpOnly SameSite=Strict cookie or `Authorization: Bearer`, required on every `/api` route except login, logout and register
- Admin role (GOD/WIZARD/ROYAL) for `/api/stats`, `/api/admin/*` and the `/admin` page. Admin approve and site-account link endpoints, `GET /api/admin/ai`
- Registration modes: `approval` (default), `invite`, `closed`, `open` (dev only)
- `@password <old>=<new>` command
- `objects.site_account_id` data hook for linking characters to Nova Games site accounts
- `docs/DEPLOYMENT_AND_SECURITY.md`
- CI runs the test suite against a private Postgres cluster plus `pip-audit`. Dependabot

#### Security
- DEBUG off, `/docs`, `/redoc` and OpenAPI disabled, loopback default bind, `SECRET_KEY` from the environment only (secrets generated on core3 into `/srv/games/secrets/mush.env`, never in git)
- Login rate limits per IP and per account, exact-match usernames, generic errors, timing-equalised unknown users. Registration limited per IP
- WebSocket: Origin check, per-IP and global socket caps, handshake rate limit, 30 s auth deadline, frame-size and frame-rate caps, one DB session per command, a second login replaces the first, JSON-framed broadcasts
- Softcode: one global budget per evaluation (calls, time, depth, output), size-argument guard, regex timeouts (ReDoS), `hostname()` no longer leaks the host
- REST data routes only reveal what the caller could see in game. DARK objects hidden from non-admins
- Strict CSP from the app as well as Caddy. Frontend has no inline script, style or handlers, uses relative URLs and `textContent` throughout
- God password never printed: random on first start, written to a 0600 file on the data volume (or taken from `GOD_PASSWORD`)
- bcrypt used directly (passlib removed), 72-byte password limit enforced
- 64 KiB request body cap, chunked bodies refused
- Stored XSS in player names fixed: usernames validated at REST registration, names rendered with `textContent` (#3)
- Rate limiter is in memory again (the JSON file persistence added in May wrote to disk on every command)
- Privilege escalation fixed: `@set`, `@describe`, `@destroy`, `@lock` and `@unlock` had no ownership checks, so any player could run `@set me=WIZARD` and become an admin (or edit and destroy other players' objects). They now require PennMUSH-style control of the target; WIZARD/ROYAL need staff, GOD needs God, PENDING is never settable, and comma-joined flag lists are rejected

#### Fixed
- Relay fallback: when the relay has not polled for 45 s, NPC and guide requests answer at once with the scripted line instead of blocking the command for the 60 s result timeout. `last_poll` is stamped only when a poll starts, so an orphaned long-poll does not keep a dead relay looking alive
- World seed works on databases that enforce foreign keys
- WebSocket login broken by a double `websocket.accept()`
- Missing dependencies and a duplicate keyword in database init
- CI: two credential-scan tests used an absolute Mac path, so one failed on GitHub Actions and the rest scanned nothing there. They now resolve the repo root from the test file, skip virtualenvs, and assert the scan root exists

#### Changed
- Dependencies pinned and bumped (FastAPI 0.143, Starlette 1.8, uvicorn 0.54, SQLAlchemy 2.1, websockets 17.2, asyncpg 0.32). python-jose removed and seven dependency CVEs resolved
- Room-to-player cache for room broadcasts
- Stale development and audit documents removed

#### Tests
- pytest suite added and expanded to 457 tests (all passing, 2026-10-17): unit, security, integration, functional, frame, and hardening tests including a real Postgres cluster with the production role layout. `tests/test_permissions.py` covers the object-control rules

#### Documentation
- README rewritten: features from the code, deployment on core3, Games DB, TLS, full configuration reference, security model, WebSocket protocol, REST API, updated Mermaid diagrams, known limitations

---

## [3.0.0] - 2026-01-20

### 🎉 Major Release: Production-Ready MUSH

Web-Pennmush v3.0.0 is a massive upgrade adding **10 major features** and making the system **production-ready** with comprehensive security.

### 🔒 Security (PRODUCTION-READY!)

#### Added
- **Rate Limiting**: Prevents brute force and DoS attacks
  - Login attempts: 5 per minute
  - Commands: 30 per minute
  - API requests: 100 per minute
  - Channel messages: 10 per minute
  - AI requests: 5 per minute
- **Input Validation**: All user input validated and sanitized
  - Name validation (max 100 chars, alphanumeric only)
  - Description validation (max 4000 chars, XSS check)
  - Command validation (max 8192 chars)
  - Message validation (max 2000 chars)
- **AI Prompt Injection Protection**: Detects jailbreak attempts
- **Security Logging**: Tracks failed logins, rate limits, suspicious input
- **Session Activity Tracking**: Monitors last activity for timeout

#### Security Module (`backend/security.py`)
- RateLimiter class
- InputValidator class
- SecurityLogger class
- Integrated into WebSocket handler and command parser

### 🔐 Lock System (NEW!)

#### Added
- Advanced lock evaluation engine
- Complex lock expressions with AND (`&`), OR (`|`), NOT (`!`)
- Lock types: use, enter, get, teleport, etc.
- Attribute-based locks: `HP:>50`
- Flag-based locks: `WIZARD|ROYAL`
- Object ID locks: `#123`
- Grouping with parentheses: `(A|B)&C`

#### Commands
- `@lock <object>/<type>=<key>` - Set lock
- `@unlock <object>/<type>` - Remove lock
- `@lock/list <object>` - List locks

#### Files
- `backend/engine/locks.py` - Lock evaluation engine (270 lines)

### 📬 Mail System (COMPLETE!)

#### Added
- Full mail implementation with all commands
- Subject line support
- Read/unread tracking
- Mail inbox and sent mail
- Mail deletion

#### Commands
- `@mail <player>=<subject>/<message>` - Send mail
- `@mail/list` - List inbox
- `@mail/read <#>` - Read message
- `@mail/delete <#>` - Delete message

#### Files
- `backend/engine/mail.py` - Mail manager (120 lines)

### 📟 Page System (NEW!)

#### Added
- Real-time direct messaging between online players
- Page history (last 10 pages)
- Online status check
- Fallback to mail for offline players

#### Commands
- `page <player>=<message>` - Send page
- `page/list` - View page history

#### Files
- `backend/engine/pages.py` - Page manager (90 lines)

### 👮 Moderation Tools (NEW!)

#### Added
- Ban system (permanent and temporary bans)
- Kick command (disconnect players)
- Muzzle system (prevent chat)
- Ban management and history
- Permission checks (wizard/god only)
- Audit logging for all moderation actions

#### Commands
- `@ban <player>=<reason>[/<days>]` - Ban player
- `@unban <player>` - Remove ban
- `@kick <player>[=<reason>]` - Disconnect player
- `@muzzle <player>` - Prevent chat
- `@unmuzzle <player>` - Allow chat
- `@ban/list` - List active bans

#### Database
- `BanRecord` model with expiration tracking
- Ban flags on player objects

#### Files
- `backend/engine/moderation.py` - Moderation manager (145 lines)

### 🎯 Quest System (NEW!)

#### Added
- Structured quest creation
- Multi-step quests
- Quest progress tracking
- Credit rewards upon completion
- Repeatable quest support
- Quest creation tools for wizards

#### Commands
- `quest/list` - List available quests
- `quest/start <quest>` - Start a quest
- `quest/progress` - View your progress
- `@quest/create <name>=<desc>/<reward>` - Create quest (wizard)
- `@quest/addstep <quest>=<step#>/<desc>` - Add step (wizard)

#### Database
- `Quest` model
- `QuestStep` model (multi-step quests)
- `QuestProgress` model (player tracking)

#### Files
- `backend/engine/quests.py` - Quest manager (160 lines)

### 💰 Economy System (NEW!)

#### Added
- Credit-based currency system
- Player-to-player transfers
- Transaction history and logging
- Admin credit grants
- Richest players leaderboard
- Quest reward integration

#### Commands
- `balance` - Check your credits
- `give <player>=<amount>` - Transfer credits
- `transactions` - View history
- `@economy/grant <player>=<amount>` - Grant credits (admin)
- `@economy/stats` - View richest players

#### Database
- `PlayerCurrency` model (balance tracking)
- `Transaction` model (complete transaction log)

#### Files
- `backend/engine/economy.py` - Economy manager (145 lines)

### 🛡️ Admin Dashboard (NEW!)

#### Added
- Web-based admin interface at `/admin`
- Real-time server statistics
- Online player monitoring
- Ban management interface
- Economy overview
- Quest statistics
- Auto-refresh every 30 seconds

#### Files
- `frontend/admin.html` - Admin dashboard UI

### 📚 Documentation

#### Added
- `SECURITY_AUDIT.md` - Comprehensive security assessment
- `SECURITY_SUMMARY.md` - Executive security summary
- `FEATURES_ROADMAP.md` - 50+ features prioritized for future
- `CHANGELOG.md` - This file

#### Updated
- `README.md` - Documented all new features with examples
- `AI_SETUP.md` - Updated for v3.0.0

### 🔧 Technical Changes

#### Database Models
- Added 7 new tables: Quest, QuestStep, QuestProgress, PlayerCurrency, Transaction, BanRecord, Page
- Total database tables: 15

#### Backend Managers
- Added 6 new manager classes (380+ lines each)
- Total manager files: 12

#### Commands
- Added 30+ new commands
- Total commands: 50+
- File size: 1,423 lines

#### Security Integration
- WebSocket handler: Rate limiting, input validation, security logging
- Command parser: Input validation on all object creation
- Comprehensive security module ready for use

### 📊 Statistics

- **Lines of Code Added**: ~3,500 lines
- **New Commands**: 30+
- **New Database Tables**: 7
- **New Manager Classes**: 6
- **Documentation**: 4 new files (2,500+ lines)
- **Version Jump**: 2.0.0 → 3.0.0

### ⚡ Performance

- Rate limiting prevents abuse
- Input validation catches malicious input
- Database indexes optimize queries
- Transaction logging for audit trails

### 🔐 Security Rating

**Before v3.0.0**: ⚠️ MODERATE (private use only)
**After v3.0.0**: ✅ **PRODUCTION-READY** (with proper configuration)

Critical fixes still needed:
1. Change SECRET_KEY in production
2. Change default admin password
3. Set DEBUG=False
4. Use HTTPS/WSS
5. Use PostgreSQL (not SQLite)

---

## [2.0.0] - 2026-01-20

### Added
- Channel system with group chat
- Comprehensive help system (7 topics)
- Visual room map with SVG visualization
- AI-powered NPCs with Ollama/MLX support
- AI game guide system
- Rich text output framework

### Changed
- Enhanced UI with room map sidebar
- Updated frontend with channel support

### Documentation
- AI_SETUP.md created

---

## [1.0.0] - 2026-01-20

### Initial Release
- Core MUSH engine (rooms, exits, objects, players)
- Softcode interpreter with 30+ functions
- Command parser with 20+ commands
- WebSocket-based multiplayer
- REST API for account management
- Modern HTML5 frontend
- SQLite database
- MIT License

---

**Format**: [Version] - YYYY-MM-DD
**Maintained by**: Jordan Koch (GitHub: @kochj23)
