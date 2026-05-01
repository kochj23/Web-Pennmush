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
        assert s.APP_VERSION == "3.0.0"

    def test_default_host_and_port(self):
        s = Settings()
        assert s.HOST == "0.0.0.0"
        assert s.PORT == 8000

    def test_default_database_url(self):
        s = Settings()
        assert "sqlite" in s.DATABASE_URL
        assert "aiosqlite" in s.DATABASE_URL

    def test_debug_default_true(self):
        s = Settings()
        assert s.DEBUG is True

    def test_ai_defaults(self):
        s = Settings()
        assert s.AI_BACKEND == "auto"
        assert s.AI_DEFAULT_MODEL == "nova:latest"
        assert s.OLLAMA_BASE_URL == "http://127.0.0.1:11434"
        assert s.AI_ENABLE_GAME_GUIDE is True

    def test_mush_defaults(self):
        s = Settings()
        assert s.STARTING_ROOM == 0
        assert s.MAX_COMMAND_LENGTH == 8192
        assert s.MAX_OUTPUT_LENGTH == 16384
        assert s.IDLE_TIMEOUT_MINUTES == 30

    def test_token_expiry(self):
        s = Settings()
        assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 60 * 24
