# Environment Variables

All configuration is via environment variables (or a `.env` file in the project root).

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./grunt.db` | SQLAlchemy async DB URL |
| `SECRET_KEY` | `change-me-...` | JWT signing key — **must be changed in production** |
| `DEBUG` | `false` | Enable debug mode |
| `APP_NAME` | `Grunt` | Application name shown in the UI |
| `APP_URL` | `http://localhost:5173` | Public base URL (used in password reset emails) |
| `ALLOWED_ORIGINS` | `["http://localhost:5173"]` | CORS allowed origins (JSON list) |

## Auth & Tokens

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | JWT access token lifetime |
| `ALGORITHM` | `HS256` | JWT algorithm |

## Database backends

| Variable | Example | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` | PostgreSQL (production) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./grunt.db` | SQLite (dev/testing) |
| `DATABASE_URL` | `mysql+aiomysql://user:pass@host/db` | MySQL |

## Redis (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `None` | Redis URL — enables background tasks, WebSocket scaling, caching |

## File storage

| Variable | Default | Description |
|----------|---------|-------------|
| `UPLOAD_DIR` | `./uploads` | Upload directory (local storage) |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum file size in MB |

## OAuth2 / SSO

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH_GOOGLE_CLIENT_ID` | — | Google OAuth Client ID |
| `OAUTH_GOOGLE_CLIENT_SECRET` | — | Google OAuth Client Secret |
| `OAUTH_MICROSOFT_CLIENT_ID` | — | Microsoft Azure AD Client ID |
| `OAUTH_MICROSOFT_CLIENT_SECRET` | — | Microsoft Azure AD Client Secret |
| `OAUTH_MICROSOFT_TENANT_ID` | `common` | Azure tenant ID (or `common` for multi-tenant) |

## Localization

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LOCALE` | `en` | Default language (`en`, `uk`) |
| `DEFAULT_TIMEZONE` | `Europe/Kyiv` | Default timezone |
