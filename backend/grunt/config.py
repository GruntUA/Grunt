"""Application settings powered by pydantic-settings."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file = os.environ.get("DOTENV_PATH", ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Core
    app_name: str = "Ґрунт"
    debug: bool = False
    secret_key: str = "change-me-to-a-random-64-char-string"

    # Database
    database_url: str = "sqlite+aiosqlite:///./grunt.db"

    # Redis (optional)
    redis_url: str | None = None

    # Auth
    access_token_expire_minutes: int = 60 * 24  # 24h
    algorithm: str = "HS256"

    # Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # CORS
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Localization
    default_locale: str = "uk"
    default_timezone: str = "Europe/Kyiv"


settings = Settings()
