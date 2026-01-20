"""
Web-Pennmush Configuration
Author: Jordan Koch (GitHub: kochj23)
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration settings"""

    # Application
    APP_NAME: str = "Web-Pennmush"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./webpennmush.db"

    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # MUSH Settings
    STARTING_ROOM: int = 0  # Default room ID for new players
    MAX_COMMAND_LENGTH: int = 8192
    MAX_OUTPUT_LENGTH: int = 16384
    IDLE_TIMEOUT_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
