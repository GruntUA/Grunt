"""System health — the checks behind the «Стан системи» report.

Every check returns rows ``{category, check, status, value, hint}`` with status
``OK`` / ``Warning`` / ``Error`` / ``Info``. A check that blows up becomes an
``Error`` row of its own — one broken subsystem never hides the others. The
browser half of the report (service worker, offline cache and queue) runs in
the page itself: ``frontend/src/core/browserHealth.ts``.
"""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from grunt import whitelist
from grunt.app import grunt
from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

OK, WARNING, ERROR, INFO = "OK", "Warning", "Error", "Info"

ERRORS_WARN_PER_DAY = 1
ERRORS_ERROR_PER_DAY = 100
STUCK_EMAIL_AFTER = timedelta(minutes=30)
DISK_WARN_FREE = 0.10
DISK_ERROR_FREE = 0.05
DEAD_WORKER_IDLE_MS = 10 * 60 * 1000
TOP_N = 10

_ROOT = Path(__file__).resolve().parents[2]  # apps/grunt
FRONTEND_DIST = _ROOT / "dist"
SERVICE_WORKER_SRC = _ROOT / "public" / "sw.js"

Row = dict[str, Any]


def row(category: str, check: str, status: str, value: Any = "", hint: str = "") -> Row:
    return {
        "category": category,
        "check": check,
        "status": status,
        "value": "" if value is None else str(value),
        "hint": hint,
    }


def human_size(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def _since(delta: timedelta) -> datetime:
    return datetime.now(UTC) - delta


def _session():
    from grunt.context import require_session

    return require_session()


# ── Database ──────────────────────────────────────────────────────────────


async def check_database() -> list[Row]:
    session = _session()
    dialect = session.bind.dialect.name
    started = time.perf_counter()
    if dialect == "sqlite":
        version = (await session.execute(text("select sqlite_version()"))).scalar()
    else:
        version = (await session.execute(text("select version()"))).scalar()
    latency = (time.perf_counter() - started) * 1000
    rows = [
        row(
            "База даних",
            "З'єднання",
            OK if latency < 200 else WARNING,
            f"{dialect} {str(version).split(' on ')[0]} · {latency:.0f} мс",
            "" if latency < 200 else "Повільна відповідь бази даних.",
        )
    ]
    size = await _database_size(session, dialect)
    if size is not None:
        rows.append(row("База даних", "Розмір", INFO, human_size(size)))
    return rows


async def _database_size(session, dialect: str) -> int | None:
    if dialect == "sqlite":
        path = session.bind.url.database
        return Path(path).stat().st_size if path and Path(path).exists() else None
    if dialect == "postgresql":
        return (await session.execute(text("select pg_database_size(current_database())"))).scalar()
    return None


async def largest_tables() -> list[Row]:
    """Top DocTypes by row count — what grows (logs usually) and may need retention."""
    from grunt.metadata.registry import doctype_registry

    counts: list[tuple[str, int]] = []
    for dt in await doctype_registry.list_all():
        if dt.is_virtual or dt.is_singleton:
            continue
        try:
            async with _session().begin_nested():  # keep a failure from aborting the tx
                n = await grunt.db.count(dt.name)
        except Exception:  # noqa: BLE001 - a DocType whose table isn't synced yet
            continue
        counts.append((dt.name, n))
    counts.sort(key=lambda c: c[1], reverse=True)
    items = []
    for name, n in counts[:TOP_N]:
        dt = await grunt.get_meta(name)
        retention = dt.retention_days if dt else None
        details = f"зберігається {retention} дн." if retention else ""
        if dt and dt.is_log and not retention:
            details = "журнал — загальний строк зберігання логів"
        items.append({"label": name, "count": n, "details": details})
    return items


# ── Background jobs & scheduler ───────────────────────────────────────────


async def check_background_jobs() -> list[Row]:
    from grunt.tasks.redis_introspect import redis_conn, s, stream_broker

    cat = "Фонові задачі"
    sb = stream_broker()
    if sb is None:
        return [
            row(
                cat,
                "Черга задач",
                WARNING,
                "у процесі (без Redis)",
                "REDIS_URL не задано: задачі виконуються в процесі сервера й губляться при "
                "перезапуску. Для production налаштуйте Redis і воркер.",
            )
        ]
    async with redis_conn() as conn:
        await conn.ping()
        consumers = await conn.xinfo_consumers(sb.queue_name, sb.consumer_group_name)
        groups = await conn.xinfo_groups(sb.queue_name)
    alive = [c for c in consumers if int(c.get("idle", 0)) < DEAD_WORKER_IDLE_MS]
    dead = len(consumers) - len(alive)
    rows = [row(cat, "Redis", OK, "доступний")]
    if not consumers:
        rows.append(
            row(
                cat,
                "Воркери",
                ERROR,
                0,
                "Жоден воркер не підключений — фонові задачі не виконуються.",
            )
        )
    else:
        rows.append(
            row(
                cat,
                "Воркери",
                OK if not dead else WARNING,
                f"{len(alive)} активних" + (f", {dead} без активності" if dead else ""),
                "Воркер без активності понад 10 хв міг впасти — див. «Воркери черги»."
                if dead
                else "",
            )
        )
    group = next((g for g in groups if s(g.get("name")) == sb.consumer_group_name), None)
    if group is not None:
        lag = group.get("lag") or 0
        pending = group.get("pending") or 0
        rows.append(
            row(
                cat,
                "Черга",
                OK if lag < 100 else WARNING,
                f"{lag} у черзі, {pending} виконується",
                "" if lag < 100 else "Задачі накопичуються швидше, ніж виконуються.",
            )
        )
    return rows


async def check_scheduler() -> list[Row]:
    from grunt.tasks.scheduler import scheduler

    cat = "Планувальник"
    rows = [
        row(
            cat,
            "Планувальник",
            OK if scheduler.running else ERROR,
            f"працює, {len(scheduler.get_jobs())} задач" if scheduler.running else "зупинений",
            ""
            if scheduler.running
            else "Запланові задачі (розсилки, чистка, дайджести) не запускаються.",
        )
    ]
    failed = await grunt.db.count(
        "ScheduledJobLog", {"status": "Failed", "started_at__gte": _since(timedelta(days=1))}
    )
    rows.append(
        row(
            cat,
            "Невдалі запуски за добу",
            OK if not failed else WARNING,
            failed,
            "Подробиці — у «Журнал запланованих задач»." if failed else "",
        )
    )
    return rows


# ── Errors, email ─────────────────────────────────────────────────────────


async def check_errors() -> list[Row]:
    n = await grunt.db.count("ErrorLog", {"created_at__gte": _since(timedelta(days=1))})
    status = OK if n < ERRORS_WARN_PER_DAY else WARNING if n < ERRORS_ERROR_PER_DAY else ERROR
    return [row("Помилки", "Помилок за добу", status, n, "Див. «Журнал помилок»." if n else "")]


async def top_errors() -> list[Row]:
    rows = await grunt.db.aggregate(
        "ErrorLog",
        filters={"created_at__gte": _since(timedelta(days=7))},
        group_by="title",
        aggregations={"count": "count(name)"},
        order_by="count",
        limit=TOP_N,
    )
    return [{"label": r["title"] or "—", "count": r["count"], "details": "за 7 днів"} for r in rows]


async def check_email() -> list[Row]:
    cat = "Пошта"
    outgoing = await grunt.db.count("EmailAccount", {"enable_outgoing": 1})
    rows = [
        row(
            cat,
            "Обліковий запис для надсилання",
            OK if outgoing else WARNING,
            outgoing,
            "" if outgoing else "Листи (скидання пароля, сповіщення) не надсилатимуться.",
        )
    ]
    failed = await grunt.db.count(
        "EmailQueue", {"status": "Error", "created_at__gte": _since(timedelta(days=7))}
    )
    rows.append(row(cat, "Помилки надсилання за 7 днів", OK if not failed else WARNING, failed))
    stuck = await grunt.db.count(
        "EmailQueue",
        {"status__in": ["Pending", "Sending"], "created_at__lt": _since(STUCK_EMAIL_AFTER)},
    )
    rows.append(
        row(
            cat,
            "Застряглі листи",
            OK if not stuck else WARNING,
            stuck,
            "Листи чекають понад 30 хв — перевірте воркер і SMTP." if stuck else "",
        )
    )
    return rows


# ── Users & security ──────────────────────────────────────────────────────


async def check_users() -> list[Row]:
    cat = "Користувачі та безпека"
    active = await grunt.db.count("User", {"is_active": 1})
    sessions = await grunt.db.count("UserSession", {"is_active": 1})
    managers = await grunt.db.get_all(
        "UserRole", filters={"role_name": "System Manager"}, pluck="parent_name"
    )
    without_mfa = await grunt.db.get_all(
        "User",
        filters={"name__in": managers or [""], "is_active": 1, "mfa_enabled": 0},
        pluck="name",
    )
    locked = await grunt.db.count("User", {"locked_until__gt": datetime.now(UTC)})
    return [
        row(cat, "Активні користувачі", INFO, active),
        row(cat, "Активні сесії", INFO, sessions),
        row(
            cat,
            "Адміністратори без 2FA",
            OK if not without_mfa else WARNING,
            len(without_mfa),
            ", ".join(without_mfa[:5]) if without_mfa else "",
        ),
        row(cat, "Заблоковані облікові записи", OK if not locked else WARNING, locked),
    ]


async def check_config() -> list[Row]:
    from grunt.config import DEFAULT_SECRET_KEY, settings

    cat = "Конфігурація"
    return [
        row(
            cat,
            "Режим налагодження",
            WARNING if settings.debug else OK,
            "увімкнено" if settings.debug else "вимкнено",
            "DEBUG=true у production відкриває зайві подробиці помилок." if settings.debug else "",
        ),
        row(
            cat,
            "Секретний ключ",
            ERROR if settings.secret_key == DEFAULT_SECRET_KEY else OK,
            "стандартний" if settings.secret_key == DEFAULT_SECRET_KEY else "власний",
            "Задайте SECRET_KEY — зі стандартним ключем токени можна підробити."
            if settings.secret_key == DEFAULT_SECRET_KEY
            else "",
        ),
        row(cat, "Сховище файлів", INFO, settings.storage_backend),
    ]


# ── Storage ───────────────────────────────────────────────────────────────


async def check_storage() -> list[Row]:
    from grunt.config import settings
    from grunt.site.manager import site_manager

    cat = "Файли"
    count = await grunt.db.count("File")
    [agg] = await grunt.db.aggregate("File", aggregations={"size": "sum(file_size)"})
    rows = [row(cat, "Файлів", INFO, f"{count} · {human_size(agg.get('size') or 0)}")]
    if settings.storage_backend == "local":
        site_dir = site_manager.sites_dir / site_manager.get_active_site()
        usage = shutil.disk_usage(site_dir)
        free = usage.free / usage.total
        status = OK if free >= DISK_WARN_FREE else WARNING if free >= DISK_ERROR_FREE else ERROR
        rows.append(
            row(
                cat,
                "Вільне місце на диску",
                status,
                f"{human_size(usage.free)} з {human_size(usage.total)} ({free:.0%})",
                "" if status == OK else "Звільніть місце — завантаження й база можуть зупинитися.",
            )
        )
    return rows


# ── Realtime (WebSocket) ──────────────────────────────────────────────────

WS_ECHO_EVENT = "health_echo"
REDIS_ROUNDTRIP_TIMEOUT = 2.0


async def check_realtime() -> list[Row]:
    """Connections of this process + the Redis pub/sub relay that carries
    realtime messages between processes (web workers, the task worker)."""
    import asyncio
    import uuid

    from grunt.api.v1.ws import manager
    from grunt.config import settings

    cat = "Вебсокети"
    channels = manager._connections
    users = {c for c, conns in channels.items() if c.startswith("user:") and conns}
    rows = [
        row(
            cat,
            "Підключення (цей процес)",
            INFO,
            f"{manager._total_connections()} з'єднань, {len(users)} користувачів",
        )
    ]
    if not settings.redis_url:
        rows.append(
            row(
                cat,
                "Ретрансляція між процесами",
                INFO,
                "без Redis",
                "Повідомлення доходять лише до клієнтів цього процесу — достатньо для одного "
                "процесу сервера без окремого воркера.",
            )
        )
        return rows

    import redis.asyncio as aioredis

    key = f"grunt:ws:__health__:{uuid.uuid4().hex}"
    r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
    try:
        pubsub = r.pubsub()
        await pubsub.subscribe(key)
        started = time.perf_counter()
        await r.publish(key, "ping")
        got = None
        deadline = started + REDIS_ROUNDTRIP_TIMEOUT
        while got is None and time.perf_counter() < deadline:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                got = time.perf_counter() - started
            await asyncio.sleep(0)
        await pubsub.unsubscribe(key)
        await pubsub.aclose()
    finally:
        await r.aclose()
    rows.append(
        row(cat, "Ретрансляція через Redis", OK, f"працює, {got * 1000:.0f} мс")
        if got is not None
        else row(
            cat,
            "Ретрансляція через Redis",
            ERROR,
            "не працює",
            "Повідомлення з воркера й інших процесів (прогрес імпорту, сповіщення) не дійдуть "
            "до браузера.",
        )
    )
    listening = manager.redis_listener_alive or not channels
    rows.append(
        row(
            cat,
            "Слухач Redis у цьому процесі",
            OK if listening else WARNING,
            "працює" if manager.redis_listener_alive else "не працює",
            ""
            if listening
            else "Є з'єднання, але слухач не працює — повідомлення з Redis не доставляються.",
        )
    )
    return rows


@whitelist(roles=["System Manager"])
async def ws_echo(nonce: str) -> dict[str, Any]:
    """Push a test event to the caller's own user channel — the browser half
    of the report checks it arrives exactly once (grunt/api/v1/ws.py)."""
    from grunt.api.v1.ws import manager

    await manager.send_to_user(
        grunt.session.user, {"event": WS_ECHO_EVENT, "data": {"nonce": nonce}}
    )
    return {"sent": True}


# ── Apps' Python dependencies ─────────────────────────────────────────────


def _requirement_name(spec: str) -> str:
    import re

    return re.split(r"[\s\[<>=!~;@]", spec.strip(), maxsplit=1)[0]


async def check_app_dependencies() -> list[Row]:
    """Every package an app declares in its pyproject.toml is installed."""
    import importlib.metadata
    import tomllib

    from grunt.apps.deps import app_packages
    from grunt.site.manager import site_manager

    missing: list[str] = []
    apps = app_packages(site_manager.bench_dir / "apps")
    for app in apps:
        project = tomllib.loads((app / "pyproject.toml").read_text()).get("project", {})
        for spec in [app.name, *project.get("dependencies", [])]:
            name = _requirement_name(spec)
            try:
                importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                missing.append(f"{app.name}: {name}")
    return [
        row(
            "Залежності додатків",
            "Python-пакети додатків",
            ERROR if missing else OK,
            f"бракує {len(missing)}" if missing else f"{len(apps)} додатків, усе встановлено",
            ("Виконайте `grunt app deps`. Бракує: " + ", ".join(missing)) if missing else "",
        )
    ]


# ── Offline mode (server side) ────────────────────────────────────────────


async def check_offline_build() -> list[Row]:
    """The service worker exists only in the production build — check it is there."""
    import json

    cat = "Офлайн-режим"
    manifest = FRONTEND_DIST / "precache-manifest.json"
    if not manifest.exists():
        return [
            row(
                cat,
                "Production-збірка",
                WARNING,
                "відсутня",
                "Немає dist/precache-manifest.json: офлайн працює лише з production-збірки "
                "(`npm run build`). У режимі розробки (Vite dev) service worker не реєструється.",
            )
        ]
    files = json.loads(manifest.read_text())
    built = datetime.fromtimestamp(manifest.stat().st_mtime, UTC)
    rows = [row(cat, "Production-збірка", OK, f"{len(files)} файлів, {built:%d.%m.%Y %H:%M} UTC")]
    dist_sw = FRONTEND_DIST / "sw.js"
    if not dist_sw.exists():
        rows.append(row(cat, "Service worker у збірці", ERROR, "відсутній"))
    elif SERVICE_WORKER_SRC.exists() and dist_sw.read_bytes() != SERVICE_WORKER_SRC.read_bytes():
        rows.append(
            row(
                cat,
                "Service worker у збірці",
                WARNING,
                "застарілий",
                "public/sw.js змінено після збірки — перезберіть фронтенд.",
            )
        )
    else:
        rows.append(row(cat, "Service worker у збірці", OK, "актуальний"))
    return rows


# ── Runner ────────────────────────────────────────────────────────────────

CHECKS: list[tuple[str, Callable[[], Awaitable[list[Row]]]]] = [
    ("База даних", check_database),
    ("Фонові задачі", check_background_jobs),
    ("Планувальник", check_scheduler),
    ("Помилки", check_errors),
    ("Пошта", check_email),
    ("Користувачі та безпека", check_users),
    ("Конфігурація", check_config),
    ("Файли", check_storage),
    ("Вебсокети", check_realtime),
    ("Залежності додатків", check_app_dependencies),
    ("Офлайн-режим", check_offline_build),
]


async def _safe(category: str, fn: Callable[[], Awaitable[Any]]) -> Any:
    try:
        # Savepoint: on PostgreSQL a failed query would poison the whole transaction.
        async with _session().begin_nested():
            return await fn()
    except Exception as e:  # noqa: BLE001 - a broken subsystem is a finding, not a crash
        log.warning("health.check_failed", check=fn.__name__, error=str(e))
        return [row(category, fn.__name__.removeprefix("check_"), ERROR, "перевірка впала", str(e))]


async def _items(fn: Callable[[], Awaitable[list[Row]]]) -> list[Row]:
    try:
        return await fn()
    except Exception as e:  # noqa: BLE001 - the check rows already cover the subsystem
        log.warning("health.items_failed", source=fn.__name__, error=str(e))
        return []


async def build_report() -> dict[str, Any]:
    checks: list[Row] = []
    for category, fn in CHECKS:
        checks.extend(await _safe(category, fn))
    tally = {s: sum(1 for c in checks if c["status"] == s) for s in (OK, WARNING, ERROR)}
    overall = ERROR if tally[ERROR] else WARNING if tally[WARNING] else OK
    return {
        "overall_status": overall,
        "checked_at": datetime.now(UTC),
        "ok_count": tally[OK],
        "warning_count": tally[WARNING],
        "error_count": tally[ERROR],
        "checks": checks,
        "top_errors": await _items(top_errors),
        "largest_tables": await _items(largest_tables),
    }
