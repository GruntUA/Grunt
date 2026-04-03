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
    debug: bool = True
    secret_key: str = "change-me-to-a-random-64-char-string"

    # Database
    database_url: str = "sqlite+aiosqlite:///./grunt.db"
    database_echo: bool = False
    slow_query_threshold_ms: float = 200.0  # log queries slower than this (dev only)

    # Redis (optional)
    redis_url: str | None = None

    # Auth
    access_token_expire_minutes: int = 60 * 24  # 24h
    algorithm: str = "HS256"

    # App URL (used for password reset links in emails)
    app_url: str = "http://localhost:5173"

    # Sentry (optional — leave empty to disable)
    sentry_dsn: str | None = None
    sentry_environment: str = "production"

    # Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    storage_backend: str = "local"  # "local" | "s3"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None  # for MinIO / Cloudflare R2
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # CORS
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Localization
    default_locale: str = "uk"
    default_timezone: str = "Europe/Kyiv"

    # OAuth2 / SSO (optional — leave empty to disable)
    oauth_google_client_id: str | None = None
    oauth_google_client_secret: str | None = None
    # Microsoft Azure AD
    oauth_microsoft_client_id: str | None = None
    oauth_microsoft_client_secret: str | None = None
    oauth_microsoft_tenant_id: str = "common"  # or specific tenant UUID


settings = Settings()
