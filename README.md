# Web-Pennmush

**Web-based MUSH server with AI-powered NPCs**

![Build](https://github.com/kochj23/Web-Pennmush/actions/workflows/build.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)
![Version](https://img.shields.io/badge/version-3.0.0-brightgreen)
![Tests](https://img.shields.io/badge/tests-358-brightgreen)

A modern MUSH (Multi-User Shared Hallucination) server inspired by [PennMUSH](https://github.com/pennmush/pennmush). Built with Python, FastAPI, and WebSockets for real-time multiplayer text-based gaming. Includes a softcode interpreter, channel system, lock evaluator, mail, quests, economy, moderation, and AI-powered NPCs via a pull-based LLM relay (the server never calls a model itself).

---

## Architecture

```mermaid
graph TD
    Browser["Web Browser"] -- "HTTP" --> FastAPI
    Browser -- "WebSocket" --> FastAPI

    subgraph FastAPI["FastAPI Server"]
        Routes["/index.html /admin /ws /api/* /health"]
    end

    FastAPI --> CP["Command Parser - 50+ commands"]
    FastAPI --> REST["REST API"]
    FastAPI --> SEC["Security Module"]

    CP --> OBJ["Object Manager"]
    CP --> SC["Softcode Evaluator"]
    CP --> CH["Channel System"]
    CP --> LK["Lock Manager"]
    CP --> ML["Mail Manager"]
    CP --> PG["Page Manager"]
    CP --> QM["Quest Manager"]
    CP --> EC["Economy Manager"]
    CP --> MOD["Moderation Manager"]
    CP --> AI["AI Manager"]

    REST --> ORM["SQLAlchemy - async"]
    OBJ --> ORM
    CH --> ORM
    LK --> ORM
    ML --> ORM
    PG --> ORM
    QM --> ORM
    EC --> ORM
    MOD --> ORM

    ORM --> DB["SQLite / PostgreSQL"]
    AI --> LLM["LLM relay (pulls template jobs)"]
```

---

## Features

| Category | Details |
|----------|---------|
| **Object System** | Rooms, exits, things, players -- all are objects with attributes, flags, and ownership |
| **Real-time Multiplayer** | WebSocket connections for live communication between all players |
| **Room Navigation** | Interconnected rooms with named exits |
| **Softcode Interpreter** | Full MUSHcode: 30+ functions, `[function(args)]` syntax, `%0`-`%9` substitutions, nested evaluation |
| **Channel System** | Create/join group channels; default Public, Newbie, Builder; aliases for quick messaging |
| **Lock System** | AND/OR/NOT operators, attribute locks (`HP:>50`), flag locks (`WIZARD\|ROYAL`), object ID locks |
| **Mail System** | Asynchronous mail with subject lines, inbox management, offline messaging |
| **Page System** | Real-time direct messaging with history |
| **Quest System** | Multi-step quests with progress tracking, credit rewards, repeatable quests |
| **Economy** | Credit currency, player-to-player transfers, transaction history, admin grants, leaderboard |
| **Moderation** | Ban (permanent/temporary), kick, muzzle with audit logging |
| **AI NPCs** | Template jobs pulled by an LLM relay (HMAC-signed); scripted fallback lines; per-player quotas |
| **AI Game Guide** | Context-aware help via `guide <question>` |
| **Help System** | Searchable in-game docs organized by category with alias support |
| **Room Map** | Interactive SVG graph of connected rooms with clickable nodes |
| **Admin Dashboard** | Web UI at `/admin` with player monitoring, ban management, economy stats, quest stats |
| **Permission Hierarchy** | God > Wizard > Royal > User enforced on all admin commands |

---

## Security

| Layer | Implementation |
|-------|---------------|
| Password Hashing | bcrypt via passlib |
| WebSocket Auth | Credential verification before command execution |
| Rate Limiting | Per-endpoint: login 5/min, commands 30/min, API 100/min, channels 10/min, AI 5/min |
| Input Validation | Length limits, character filtering, SQL keyword detection |
| XSS Protection | HTML entity escaping on all output; pattern detection on input |
| AI Prompt Injection | Jailbreak pattern detection and sanitization |
| Soft Delete | Objects marked GARBAGE, never truly deleted |
| Security Logging | Failed logins, rate violations, suspicious input, admin actions |

---

## Quick Start

```bash
git clone git@github.com:kochj23/Web-Pennmush.git
cd Web-Pennmush
pip install -r requirements.txt
python -m backend.main
```

For local development `REGISTRATION_MODE=open` is convenient (`echo REGISTRATION_MODE=open > .env`).
Open `http://127.0.0.1:8000`. The admin account is `One`; its password is `GOD_PASSWORD` if set, otherwise a random one written once to `data/initial_god_password` (mode 0600, never printed). Change it in game with `@password <old>=<new>`.

### AI (optional)

NPC lines and the `guide` come from the Nova Games LLM relay, which pulls jobs from `GET /relay/jobs` (HMAC-signed with `RELAY_SECRET_MUSH`). Without the relay, NPCs answer with scripted lines.

Verify in-game: `@ai/status` and `guide How do I build?`

---

## Commands

| Area | Commands |
|------|----------|
| Movement | `look`, `examine`, `go`, `get`, `drop`, `inventory`, `who` |
| Communication | `say`/`"`, `pose`/`:`, `page`, `@mail`, `channel/*` |
| Building | `@dig`, `@open`, `@describe`, `@create`, `@set`, `@destroy` |
| Softcode | `think [strlen(Hello)]` -> 5, `think [add(10,20)]` -> 30 |
| AI | `@npc/create`, `@npc/personality`, `talk to`, `guide` |
| Locks | `@lock obj/use=#123\|WIZARD`, `@unlock`, `@lock/list` |
| Economy | `balance`, `give Alice=100`, `transactions`, `quest/*` |
| Moderation | `@ban`, `@unban`, `@kick`, `@muzzle` (Wizard+) |

---

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Password login; sets an HttpOnly session cookie and returns a token |
| `/api/auth/logout` | POST | Clear the session cookie |
| `/api/auth/me` | GET | Current player (session required) |
| `/api/players/register` | POST | Create account (invite code / admin approval, rate limited) |
| `/api/players` | GET | Connected players (session); all accounts for admins |
| `/api/players/{id}` | GET | Player info (session) |
| `/api/objects/{id}` | GET | Objects you can see (session) |
| `/api/rooms/{id}/contents` | GET | Your current room (session; any room for admins) |
| `/api/rooms/map` | GET | Room graph around you (session) |
| `/api/stats`, `/api/admin/*` | GET/POST | Admin only (GOD/WIZARD/ROYAL) |
| `/healthz` | GET | Health check |

WebSocket: `/ws` -- first frame `{"type": "auth", "token": "..."}`, then `{"type": "command", "command": "look"}`.

---

## Configuration

All settings via environment variables, `.env` file, or `backend/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `HOST` | `127.0.0.1` (container: `0.0.0.0`) | Bind address |
| `PORT` | `8000` | Server port |
| `DATABASE_URL` | SQLite file (dev) | Postgres in production (`postgresql://...?sslmode=verify-full&sslrootcert=...`) |
| `DATABASE_MIGRATE_URL` | = `DATABASE_URL` | Schema-owner role for create_all |
| `SECRET_KEY` | none (required) | Session signing |
| `REGISTRATION_MODE` | `approval` | `invite`, `approval`, `closed`, `open` (dev) |
| `RELAY_SECRET_MUSH` | none | Enables the LLM relay endpoints |
| `IDLE_TIMEOUT_MINUTES` | `30` | Session timeout |
| `MAX_COMMAND_LENGTH` | `8192` | Input limit |

---

## Database

PostgreSQL in production (bounded pool, statement timeout, startup retry with backoff); SQLite only for local development and unit tests. Auto-seeds on first run with Room Zero, admin account "One", Central Plaza, portal exits, and a sample object.

```bash
# PostgreSQL
pip install asyncpg
# Set DATABASE_URL=postgresql+asyncpg://user:pass@localhost/webpennmush
```

---

## Test Suite

358 pytest tests covering unit, functional, security, and integration.

| File | Category | Tests | Description |
|------|----------|-------|-------------|
| test_models.py | Unit | 12 | ORM models, relationships, enums |
| test_config.py | Unit | 8 | Settings and configuration |
| test_objects.py | Unit | 24 | Object CRUD, attributes, flags, movement |
| test_channels.py | Unit | 15 | Channel CRUD, membership, help topics |
| test_locks.py | Unit | 19 | Lock creation, evaluator AND/OR/NOT/attribute |
| test_mail_pages.py | Unit | 15 | Mail send/read/delete, page send/history |
| test_moderation.py | Unit | 10 | Ban/unban, expiry, listing |
| test_quests_economy.py | Unit | 20 | Quests, credits, transfers, transactions |
| test_commands.py | Functional | 31 | Command parser, permissions, say/pose/look |
| test_api.py | Functional | 13 | REST endpoints, registration, queries |
| test_security.py | Security | 56 | Rate limiter, XSS, SQLi, AI prompt injection |
| test_security_advanced.py | Security | 15 | ORM injection, auth bypass, credential scan |
| test_comprehensive.py | Comprehensive | 111 | Extended coverage across all systems |
| test_integration.py | Integration | 9 | Multi-step flows: create-examine, dig-navigate |
| **Total** | | **358** | |

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## Production

See [docs/DEPLOYMENT_AND_SECURITY.md](docs/DEPLOYMENT_AND_SECURITY.md) and the `Dockerfile` (non-root, read-only rootfs, health check). Dependencies are pinned in [requirements.txt](requirements.txt) and checked with `pip-audit`. ~12,400 lines of Python backend, vanilla HTML/CSS/JS frontend.

---

## License

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2025 Jordan Koch.

---

Written by **Jordan Koch** ([@kochj23](https://github.com/kochj23))
