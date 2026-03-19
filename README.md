# Ґрунт

Metadata-driven application framework для побудови CMS, ERP, реєстрів та інших бізнес-додатків.

## Швидкий старт

```bash
curl -sSL https://raw.githubusercontent.com/rareMaxim/grunt/master/setup.sh | bash
```

або якщо репозиторій вже склонований:

```bash
git clone https://github.com/rareMaxim/grunt && cd grunt && bash setup.sh
```

Після цього:

- API: http://localhost:8000
- Документація API: http://localhost:8000/docs
- Інтерфейс: http://localhost:5173

---

## Вимоги

| Інструмент | Версія |
|-----------|--------|
| Python | 3.12+ |
| Node.js | 20+ |
| [uv](https://astral.sh/uv) | будь-яка (авто-встановлюється) |

Для production додатково: PostgreSQL 15+, Redis 7+

---

## Режими розгортання

### Dev (за замовчуванням)

SQLite, без Redis. Достатньо для локальної розробки.

```bash
bash setup.sh
# або
bash setup.sh dev
```

Запуск після розгортання:

```bash
make dev
```

### Production

PostgreSQL + Redis. Перед запуском заповни `DATABASE_URL` і `REDIS_URL` у `.env`.

```bash
bash setup.sh prod
```

### Docker

```bash
bash setup.sh docker
```

Запускає PostgreSQL, Redis і додаток через Docker Compose.

---

## Команди

```bash
make dev          # запустити backend + frontend
make backend      # тільки FastAPI (порт 8000)
make frontend     # тільки Vite (порт 5173)

make test         # всі тести
make lint         # ruff + eslint
make typecheck    # mypy + vue-tsc

make db-migrate   # застосувати міграції
make db-reset     # скинути БД (тільки dev)
```

---

## Структура проєкту

```
grunt/
├── backend/        # Python / FastAPI
├── frontend/       # Vue 3 / TypeScript
├── grunt-cli/      # CLI інструмент
├── setup.sh        # скрипт розгортання
└── Makefile        # команди розробника
```

Детальніше — у [ARCHITECTURE.md](ARCHITECTURE.md) та [CLAUDE.md](CLAUDE.md).
