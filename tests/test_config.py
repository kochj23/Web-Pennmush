"""
Unit Tests -- Configuration
Author: Jordan Koch (GitHub: kochj23)

Verifies config defaults and settings loading.
"""
import pytest
from backend.config import Settings


class TestSettings:
    def test_default_app_name(self):
        s = Settings()
        assert s.APP_NAME == "Web-Pennmush"

    def test_default_version(self):
        s = Settings()
        assert s.APP_VERSION == "3.1.0"

    def test_default_host_and_port(self):
        assert Settings.model_fields["HOST"].default == "127.0.0.1"
        assert Settings.model_fields["PORT"].default == 8000

    def test_default_database_url(self):
        s = Settings(DATABASE_URL="", DB_HOST="")
        assert "sqlite+aiosqlite" in s.database_url()
        pg = Settings(DATABASE_URL="", DB_HOST="games-pg", DB_PASSWORD="x")
        assert pg.database_url().startswith("postgresql+asyncpg://mush:x@games-pg:5432/games")

    def test_debug_default_true(self):
        """Renamed intent: DEBUG now defaults to False (security finding #1)."""
        assert Settings.model_fields["DEBUG"].default is False

    def test_ai_defaults(self):
        assert Settings.model_fields["AI_BACKEND"].default == "relay"
        assert "AI_DEFAULT_MODEL" not in Settings.model_fields  # relay picks the model, never nova*
        assert Settings.model_fields["AI_ENABLE_GAME_GUIDE"].default is True

    def test_mush_defaults(self):
        s = Settings()
        assert s.STARTING_ROOM == 0
        assert s.MAX_COMMAND_LENGTH == 8192
        assert s.MAX_OUTPUT_LENGTH == 16384
        assert s.IDLE_TIMEOUT_MINUTES == 30

    def test_token_expiry(self):
        s = Settings()
        assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 60 * 12
