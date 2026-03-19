# Ґрунт — Makefile
# Використання: make <команда>
.PHONY: help setup setup-prod setup-docker dev backend frontend \
        db-init db-migrate db-reset test test-py test-js lint typecheck clean

# ─── За замовчуванням — показати допомогу ─────────────────────────────────────
help:
	@echo ""
	@echo "  Ґрунт Framework — доступні команди:"
	@echo ""
	@echo "  Розгортання:"
	@echo "    make setup         — dev-розгортання (SQLite)"
	@echo "    make setup-prod    — production (PostgreSQL + Redis)"
	@echo "    make setup-docker  — через Docker Compose"
	@echo ""
	@echo "  Запуск:"
	@echo "    make dev           — backend + frontend паралельно"
	@echo "    make backend       — тільки FastAPI (порт 8000)"
	@echo "    make frontend      — тільки Vite (порт 5173)"
	@echo ""
	@echo "  База даних:"
	@echo "    make db-init       — ініціалізувати БД"
	@echo "    make db-migrate    — застосувати міграції"
	@echo "    make db-reset      — скинути БД (тільки dev!)"
	@echo ""
	@echo "  Якість коду:"
	@echo "    make test          — всі тести"
	@echo "    make test-py       — Python тести (pytest)"
	@echo "    make test-js       — Vue тести (vitest)"
	@echo "    make lint          — ruff + eslint"
	@echo "    make typecheck     — mypy + vue-tsc"
	@echo ""
	@echo "    make clean         — видалити артефакти збірки"
	@echo ""

# ─── Розгортання ──────────────────────────────────────────────────────────────
setup:
	@bash setup.sh dev

setup-prod:
	@bash setup.sh prod

setup-docker:
	@bash setup.sh docker

# ─── Запуск ───────────────────────────────────────────────────────────────────
dev:
	@echo "→ Запуск backend і frontend..."
	@trap 'kill 0' INT; \
	uv run uvicorn backend.grunt.main:app --reload --port 8000 & \
	cd frontend && npm run dev & \
	wait

backend:
	uv run uvicorn backend.grunt.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# ─── База даних ───────────────────────────────────────────────────────────────
db-init:
	uv run alembic -c backend/alembic.ini upgrade head

db-migrate:
	uv run alembic -c backend/alembic.ini upgrade head

db-reset:
	@echo "⚠  Це видалить всі дані! Ctrl+C щоб скасувати..."
	@sleep 3
	uv run alembic -c backend/alembic.ini downgrade base
	uv run alembic -c backend/alembic.ini upgrade head

# ─── Тести ────────────────────────────────────────────────────────────────────
test: test-py test-js

test-py:
	uv run pytest backend/tests/ -v --tb=short

test-js:
	cd frontend && npm test -- --run

# ─── Якість коду ──────────────────────────────────────────────────────────────
lint:
	uv run ruff check . --fix
	cd frontend && npm run lint 2>/dev/null || true

typecheck:
	uv run mypy backend/grunt
	cd frontend && npm run typecheck

# ─── Збірка ───────────────────────────────────────────────────────────────────
build:
	cd frontend && npm run build

# ─── Очищення ─────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf frontend/dist frontend/node_modules/.vite
	rm -rf .pytest_cache .mypy_cache .ruff_cache
