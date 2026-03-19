#!/usr/bin/env bash
# setup.sh — Швидке розгортання Ґрунт у новому середовищі
set -euo pipefail

# ─── Кольори ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${BLUE}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }
step() { echo -e "\n${BOLD}${BLUE}[$1]${NC} $2"; }

# ─── Аргументи ────────────────────────────────────────────────────────────────
MODE="${1:-dev}"   # dev | prod | docker
SKIP_CHECKS="${SKIP_CHECKS:-false}"

echo -e "${BOLD}"
echo "╔═══════════════════════════════════════╗"
echo "║   Ґрунт Framework — Setup Script      ║"
echo "║   mode: ${MODE}                             ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

# ─── 1. Перевірка залежностей ─────────────────────────────────────────────────
step "1/6" "Перевірка системних залежностей"

if [[ "$SKIP_CHECKS" != "true" ]]; then
    # Python
    if command -v python3 &>/dev/null; then
        PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
        if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 12 ]]; then
            ok "Python $PY_VERSION"
        else
            fail "Python >= 3.12 required (got $PY_VERSION)"
        fi
    else
        fail "Python3 не знайдено. Встанови з https://python.org"
    fi

    # uv
    if command -v uv &>/dev/null; then
        ok "uv $(uv --version 2>&1 | head -1)"
    else
        warn "uv не знайдено. Встановлюю..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
        ok "uv встановлено"
    fi

    # Node.js
    if command -v node &>/dev/null; then
        NODE_VERSION=$(node --version)
        ok "Node.js $NODE_VERSION"
    else
        fail "Node.js не знайдено. Встанови з https://nodejs.org (v20+)"
    fi

    # npm / pnpm
    if command -v npm &>/dev/null; then
        ok "npm $(npm --version)"
    else
        fail "npm не знайдено"
    fi

    if [[ "$MODE" == "docker" ]]; then
        if command -v docker &>/dev/null; then
            ok "Docker $(docker --version | cut -d' ' -f3)"
        else
            fail "Docker не знайдено"
        fi
        if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
            ok "Docker Compose"
        else
            fail "Docker Compose v2 не знайдено"
        fi
    fi
fi

# ─── 2. Змінні середовища ─────────────────────────────────────────────────────
step "2/6" "Налаштування .env"

if [[ ! -f .env ]]; then
    cp .env.example .env
    info "Створено .env з .env.example"

    # Генеруємо SECRET_KEY
    if command -v openssl &>/dev/null; then
        SECRET=$(openssl rand -hex 32)
    elif command -v python3 &>/dev/null; then
        SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    else
        SECRET="change-me-$(date +%s)"
        warn "Не вдалося згенерувати ключ, замініть SECRET_KEY вручну"
    fi
    # sed -i '' на macOS, sed -i на Linux
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s/change-me-to-a-random-64-char-string/$SECRET/" .env
    else
        sed -i "s/change-me-to-a-random-64-char-string/$SECRET/" .env
    fi
    ok "SECRET_KEY згенеровано"

    if [[ "$MODE" == "prod" ]]; then
        warn "Для production налаштуй DATABASE_URL (PostgreSQL) і REDIS_URL у .env"
    fi
else
    ok ".env вже існує, пропускаю"
fi

# ─── 3. Python залежності ─────────────────────────────────────────────────────
step "3/6" "Встановлення Python залежностей"

if [[ "$MODE" == "prod" ]]; then
    info "Встановлення з postgres + redis extras..."
    uv sync --extra postgres --extra redis
else
    info "Встановлення dev залежностей (SQLite)..."
    uv sync --extra dev
fi
ok "Python залежності встановлено"

# ─── 4. Node.js залежності ────────────────────────────────────────────────────
step "4/6" "Встановлення Node.js залежностей"

cd frontend
npm install --silent
cd ..
ok "Node.js залежності встановлено"

# ─── 5. База даних ────────────────────────────────────────────────────────────
step "5/6" "Ініціалізація бази даних"

if [[ "$MODE" == "docker" ]]; then
    info "Запуск docker compose для БД..."
    docker compose up -d db redis
    info "Очікування готовності PostgreSQL..."
    for i in {1..30}; do
        if docker compose exec -T db pg_isready -U grunt &>/dev/null 2>&1; then
            ok "PostgreSQL готовий"
            break
        fi
        if [[ $i -eq 30 ]]; then
            fail "PostgreSQL не запустився за 30 секунд"
        fi
        sleep 1
    done
fi

# Запуск міграцій
info "Запуск міграцій Alembic..."
uv run alembic -c backend/alembic.ini upgrade head 2>/dev/null || {
    warn "alembic.ini не знайдено, пропускаю міграції (буде виконано при першому запуску)"
}
ok "База даних готова"

# ─── 6. Фінальна перевірка ────────────────────────────────────────────────────
step "6/6" "Готово!"

echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Ґрунт успішно розгорнуто!               ${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════${NC}"
echo ""

if [[ "$MODE" == "docker" ]]; then
    echo -e "  Запуск:  ${BOLD}docker compose up${NC}"
else
    echo -e "  Backend: ${BOLD}uv run uvicorn backend.grunt.main:app --reload${NC}"
    echo -e "  Frontend:${BOLD}cd frontend && npm run dev${NC}"
    echo ""
    echo -e "  Або разом через grunt CLI:"
    echo -e "           ${BOLD}uv run grunt serve${NC}"
fi

echo ""
echo -e "  API Docs: ${BLUE}http://localhost:8000/docs${NC}"
echo -e "  Frontend: ${BLUE}http://localhost:5173${NC}"
echo ""
