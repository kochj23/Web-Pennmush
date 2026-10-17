"""
Web-Pennmush Configuration
Author: Jordan Koch (GitHub: kochj23)

All settings come from the environment (or an optional .env for local dev).
Production values (secrets, DB credentials) are injected by the deployment
(Nova Games: /srv/games/secrets/mush.env on nova-core3) and never live in git.
Defaults are safe: DEBUG off, loopback bind, no docs, registration gated.
"""
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # Application
    APP_NAME: str = "Web-Pennmush"
    APP_VERSION: str = "3.1.0"
    DEBUG: bool = False

    # Server (container overrides HOST to 0.0.0.0; local default stays on loopback)
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database. Production: Postgres (asyncpg). Either a full DATABASE_URL or the
    # DB_* parts (password from DB_PASSWORD or DB_PASSWORD_FILE). SQLite is only
    # used for local dev and the unit-test fixture.
    DATABASE_URL: str = ""
    # Owner/DDL role used only for create_all + sequence sync at startup.
    DATABASE_MIGRATE_URL: str = ""
    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_NAME: str = "games"
    DB_USER: str = "mush"
    DB_PASSWORD: str = ""
    DB_PASSWORD_FILE: str = ""
    DB_SCHEMA: str = "mush"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_S: int = 10
    DB_STATEMENT_TIMEOUT_MS: int = 5000
    DB_CONNECT_RETRIES: int = 8

    # Data dir (writable volume) - holds the one-time God password file only.
    DATA_DIR: str = "./data"

    # Security
    SECRET_KEY: str = ""  # required in production; ephemeral random key if empty
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    # Origins allowed to open the WebSocket / POST with cookies. Empty = same host only.
    ALLOWED_ORIGINS: List[str] = []
    # Reverse proxies whose X-Forwarded-For is trusted (CIDRs).
    TRUSTED_PROXIES: List[str] = ["127.0.0.1/32", "172.30.11.0/24"]
    COOKIE_SECURE: bool = False  # set true behind HTTPS (Nova Games site is https)
    COOKIE_PATH: str = "/"  # "/mush/" when served under that prefix
    SECURITY_HEADERS: bool = True

    # Registration: "invite" (needs INVITE_CODE), "approval" (admin approves),
    # "closed" (admins create accounts in-game), "open" (dev only).
    REGISTRATION_MODE: str = "approval"
    INVITE_CODE: str = ""

    # Connection / abuse limits
    WS_MAX_PER_IP: int = 4
    WS_MAX_TOTAL: int = 200
    WS_MAX_MESSAGE_BYTES: int = 16384
    WS_AUTH_TIMEOUT_S: float = 30.0
    WS_FRAMES_PER_10S: int = 40

    # Softcode evaluation budget (per top-level evaluation)
    SOFTCODE_MAX_CALLS: int = 10000
    SOFTCODE_MAX_MS: int = 250
    SOFTCODE_MAX_DEPTH: int = 50
    SOFTCODE_MAX_OUTPUT: int = 16384

    # MUSH Settings
    STARTING_ROOM: int = 0  # Default room ID for new players
    MAX_COMMAND_LENGTH: int = 8192
    MAX_OUTPUT_LENGTH: int = 16384
    IDLE_TIMEOUT_MINUTES: int = 30

    # AI: NPC lines go through the Nova Games LLM relay (pull model). The relay
    # authenticates with RELAY_SECRET_MUSH. Without it, NPCs use scripted lines.
    AI_BACKEND: str = "relay"  # relay | none
    RELAY_SECRET_MUSH: str = ""
    AI_RESULT_TIMEOUT_S: float = 60.0
    AI_MAX_PENDING: int = 20
    AI_ENABLE_GAME_GUIDE: bool = True

    def database_url(self) -> str:
        """Resolve the SQLAlchemy URL from DATABASE_URL or DB_* parts."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DB_HOST:
            password = self.DB_PASSWORD
            if not password and self.DB_PASSWORD_FILE:
                password = Path(self.DB_PASSWORD_FILE).read_text().strip()
            return (
                f"postgresql+asyncpg://{quote(self.DB_USER, safe='')}:{quote(password, safe='')}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{quote(self.DB_NAME, safe='')}"
            )
        return "sqlite+aiosqlite:///./webpennmush.db"

    def migrate_url(self) -> str:
        return self.DATABASE_MIGRATE_URL or self.database_url()

    @property
    def is_postgres(self) -> bool:
        return self.database_url().startswith("postgresql")


settings = Settings()
