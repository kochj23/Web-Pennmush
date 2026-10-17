# Deployment and Security

## Deployment

The Web-Pennmush server runs as a container named `novagames-mush` behind a Caddy reverse proxy at the path `/mush/`. The application sees URLs relative to `/`, including `/ws`, `/api/...`, and `/healthz`. All client URLs are relative.

### Container Image

- Dockerfile located at the repository root.
- Base image: `python:3.12-slim`.
- Runs as UID 10001.
- Root filesystem is read-only (only /tmp tmpfs and the /data volume are writable).
- Health check: `GET /healthz` returns `{"status":"ok"}`.

### Database

- Dedicated PostgreSQL instance with database named `games` and schema `mush`.
- Application uses `DATABASE_URL` (role `mush`, DML only).
- Table creation and sequence sync at startup use `DATABASE_MIGRATE_URL` (role `mush_owner`).
- TLS enabled with `sslmode=verify-full` and pinned CA.
- SQLite is used only for local development and unit tests.

### Database Behavior

- Connection retry with exponential backoff at startup:
  - `DB_CONNECT_RETRIES`: default 8
  - Initial delay: 0.5s, doubles to max 10s
- Pool settings:
  - `pool_size`: 5
  - `max_overflow`: 5
  - `pool_timeout`: 10s
  - `statement_timeout`: 5000 ms
  - `idle_in_transaction_session_timeout`: 30 s

### Environment Variables

| Name                      | Default         | Meaning                                                                 |
|---------------------------|------------------|-------------------------------------------------------------------------|
| DEBUG                     | false            | Enable debug mode (must be off in production)                           |
| SECRET_KEY                | required         | Session signing key; if empty a per-process random key is used and sessions reset on restart |
| DATABASE_URL              | SQLite file (dev) | Postgres URL for the app role (production)                             |
| DATABASE_MIGRATE_URL      | = DATABASE_URL   | Postgres URL for the schema-owner role (create_all, sequences)          |
| REGISTRATION_MODE         | approval         | One of: invite, approval, closed, open (open only for dev)              |
| INVITE_CODE               | required if mode=invite | Required when registration mode is `invite`                          |
| RELAY_SECRET_MUSH         | optional         | Enables NPC/guide lines through LLM relay; otherwise scripted           |
| GOD_PASSWORD              | optional         | Initial password for #1 "One"; otherwise a random one is written once to DATA_DIR/initial_god_password (0600), never printed |
| ALLOWED_ORIGINS           | empty            | JSON list of allowed origins (empty = same host only)        |
| TRUSTED_PROXIES           | 127.0.0.1/32, 172.30.11.0/24 | CIDR blocks trusted for forwarded headers         |
| COOKIE_SECURE             | false            | Set to true when behind HTTPS                                           |
| COOKIE_PATH               | "/"              | Set to "/mush/" in deployment under that prefix                         |
| WS_MAX_PER_IP             | 4                | Max WebSocket connections per IP                                        |
| WS_MAX_TOTAL              | 200              | Global WebSocket connection limit                                       |
| WS_MAX_MESSAGE_BYTES      | 16384            | Max message size in bytes                                               |
| WS_FRAMES_PER_10S         | 40               | Rate limit for WebSocket frames                                         |
| SOFTCODE_MAX_CALLS        | 10000            | Max function calls per softcode evaluation                              |
| SOFTCODE_MAX_MS           | 250              | Max wall time in milliseconds                                           |
| SOFTCODE_MAX_DEPTH        | 50               | Max nesting depth                                                       |
| SOFTCODE_MAX_OUTPUT       | 16384            | Max output size in characters                                           |

## Security Controls

- `/docs`, `/redoc`, and `/openapi.json` are disabled; `DEBUG` is off.
- All `/api` routes require a session except:
  - `/api/auth/login`
  - `/api/auth/logout`
  - `/api/players/register`
- Admin routes (`/api/stats`, `/api/admin/*`) and the `/admin` page require GOD, WIZARD, or ROYAL.
- Non-admin players only see:
  - Connected players
  - Objects they own/carry/stand with
  - Contents of their current room
  - Radius-3 map around themselves
- Sessions:
  - HMAC-SHA256 signed tokens (12 h)
  - Stored in HttpOnly SameSite=Strict cookie or `Authorization: Bearer`
  - Logins compare usernames exactly (case-insensitive)
- Login limits:
  - 20 attempts per IP and 10 per account per 10 minutes
  - Registration: 3 per IP per hour
  - Limits are in-memory only
- Browser requests that change state must come from the same origin (Origin header check).
- WebSocket:
  - Origin check
  - Per-IP and global connection caps
  - Handshake rate limit
  - 30 s auth timeout
  - Message size cap
  - Frame-rate cap
  - 30 commands/min
  - One short-lived DB session per command
  - Second login for same character closes first socket
- Softcode:
  - Budget per top-level evaluation (function calls, wall time, nesting depth, output size)
  - Size arguments above 4096 rejected
  - User regexes run with 50 ms timeout
  - `hostname()` no longer reveals server name
- Passwords:
  - bcrypt (passlib removed)
  - 8–72 bytes
  - `@password <old>=<new>` changes own password
- LLM:
  - Server does not call models directly
  - NPC lines via relay jobs (`GET /relay/jobs`, `POST /relay/jobs/{id}/result`)
  - Caddy blocks `/mush/relay/*` from outside
  - Per player: 5 AI lines/min, 20/hour
- Security headers:
  - CSP: `script-src 'self'; no inline`
  - X-Frame-Options: DENY
  - nosniff
  - Referrer-Policy: no-referrer

## Admin Tasks

- Approve accounts:
  - Admin page "Approve" button
  - POST `/api/admin/players/{id}/approve`
- Link character to Nova Games site account:
  - POST `/api/admin/players/{id}/link-account` with `{"site_account_id": "..."}`
  - Stored in `objects.site_account_id`; data hook only, no game logic uses it yet
- Check AI relay status:
  - GET `/api/admin/ai`
  - Or use `@ai/status` in-game

## Testing

- Install development dependencies:  
  ```bash
  pip install -r requirements-dev.txt
  ```
- Run tests:  
  ```bash
  pytest
  ```
- Postgres integration tests:
  - Start a private throwaway cluster with `initdb`/`pg_ctl`
  - Or use `PG_TEST_URL` / `PG_TEST_MIGRATE_URL`
  - Skipped if neither is available
## Linking characters to site accounts

The Nova Games site has one account system (`/api/saves`, see the platform CONTRACT.md). MUSH keeps its own characters. `objects.site_account_id` (nullable, indexed) is reserved to link a character to a site account id; admins set it with `POST /api/admin/players/{id}/link-account`. Nothing reads it yet; a later change can let a verified site session (games-saves `/internal/whoami`) log in to a linked character.
