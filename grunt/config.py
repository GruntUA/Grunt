"""Application settings powered by pydantic-settings."""

from __future__ import annotations

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file = os.environ.get("DOTENV_PATH", ".env")

# Placeholder shipped in the repo. Signing JWTs with it means anyone can forge a
# token for any user, so it must never survive into a non-debug deployment.
DEFAULT_SECRET_KEY = "change-me-to-a-random-64-char-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Core
    app_name: str = "Ґрунт"
    debug: bool = True
    secret_key: str = DEFAULT_SECRET_KEY

    # Logging
    log_level: str = "INFO"
    log_to_file: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./grunt.db"
    database_echo: bool = False
    slow_query_threshold_ms: float = 10.0  # individual SQL query slow threshold (dev only)
    slow_request_db_ms: float = 20.0  # total DB time per request slow threshold
    slow_request_ms: float = 100.0  # total request duration slow threshold

    # Redis (optional)
    redis_url: str | None = None

    # Query-level cache (optional, Redis-backed when redis_url is configured)
    query_cache_enabled: bool = True
    query_cache_ttl_seconds: int = 30

    # Per-document cache for hot get-by-id lookups (optional, Redis-backed
    # when redis_url is configured) — see grunt/cache/document_cache.py. TTL
    # is only a backstop; freshness is normally guaranteed by invalidation on
    # every write to the cached document.
    doc_cache_enabled: bool = True
    doc_cache_ttl_seconds: int = 300

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

    # Reverse proxies whose forwarded client-IP headers (CF-Connecting-IP,
    # X-Real-IP, X-Forwarded-For) are believed. A request from any other
    # address is identified by its own socket address — so a client can't
    # spoof its IP (and dodge a role / API-key IP allowlist) with a header.
    trusted_proxies: list[str] = ["127.0.0.1/32", "::1/128"]
    # Also believe CF-Connecting-IP when the connection comes from a published
    # Cloudflare edge range (grunt.auth.ip_policy.CLOUDFLARE_RANGES).
    trust_cloudflare: bool = True

    # CORS
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_user: int = 200  # req/min for authenticated users
    rate_limit_anon: int = 30  # req/min for anonymous (IP-based)
    rate_limit_webform: int = 10  # req/min per-IP for public web-form submissions
    rate_limit_files: int = 600  # req/min per-IP for signed file URLs (<img> grids)

    # CAPTCHA (Turnstile) — used only by WebForm submissions that opt in via
    # their own captcha_enabled flag. Leave captcha_provider unset to disable
    # site-wide, even if a form asks for it.
    captcha_provider: str | None = None  # "turnstile" is the only provider for now
    captcha_site_key: str | None = None
    captcha_secret_key: str | None = None

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

    # WebAuthn / Passkeys (optional — needs the `webauthn` extra installed)
    # All three fall back to APP_URL / APP_NAME when left unset, which is fine
    # for local dev but should be pinned explicitly in production.
    webauthn_rp_id: str | None = None  # DNS name only, e.g. "app.example.com"
    webauthn_rp_name: str | None = None  # display name shown by the authenticator
    webauthn_origin: str | None = None  # full origin, e.g. "https://app.example.com"

    @model_validator(mode="after")
    def _forbid_default_secret_outside_debug(self) -> Settings:
        """Refuse to run with the placeholder secret when debug is off.

        Failing loudly at startup is the only reliable guard: with the default
        key every JWT is forgeable, and that is invisible until exploited.
        """
        if not self.debug and self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                "secret_key is still the built-in placeholder. Set SECRET_KEY "
                '(e.g. `python -c "import secrets; print(secrets.token_urlsafe(64))"`) '
                "before running with debug=False."
            )
        return self


settings = Settings()
