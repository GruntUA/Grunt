# Installation

## Requirements

- Python 3.12+
- Node.js 20+ (for frontend development)
- PostgreSQL 14+ (recommended) or SQLite (dev/testing)
- Redis 7+ (optional, for background tasks, WebSocket scaling, caching)

## Install via pip / uv

```bash
# Core only (SQLite, no Redis)
pip install grunt

# With PostgreSQL support
pip install grunt[postgres]

# With Redis support
pip install grunt[postgres,redis]

# All extras (MFA, OAuth, S3)
pip install grunt[postgres,redis,mfa,oauth]
```

Using [uv](https://github.com/astral-sh/uv) (recommended):

```bash
uv add grunt[postgres,redis]
```

## Project setup

```bash
# 1. Create a new project directory
mkdir my_project && cd my_project

# 2. Initialize Grunt (creates .env, first admin user, DB schema)
grunt init

# 3. Start the development server
grunt serve --reload
```

## Environment variables

Copy `.env.example` to `.env` and configure:

```dotenv
# Required
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/grunt
SECRET_KEY=change-me-to-a-random-64-char-string

# Optional
REDIS_URL=redis://localhost:6379
SENTRY_DSN=https://...@sentry.io/...

# OAuth (Google SSO)
OAUTH_GOOGLE_CLIENT_ID=...
OAUTH_GOOGLE_CLIENT_SECRET=...

# File storage (default: local)
STORAGE_BACKEND=s3
S3_BUCKET=my-bucket
S3_REGION=eu-central-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

See [Environment Variables](../deployment/env-vars.md) for a full reference.

## Docker Compose

For a complete local stack with PostgreSQL and Redis:

```bash
docker compose up -d
```

The `docker-compose.yml` in the repo provides:

- `backend` — FastAPI + Grunt
- `frontend` — Vite dev server (development) or Nginx (production)
- `db` — PostgreSQL 16
- `redis` — Redis 7
- `worker` — TaskIQ background worker
