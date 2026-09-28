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

import grunt
from grunt import log, whitelist
from grunt.i18n import N_, _

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
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {_(unit)}" if unit == "B" else f"{n:.1f} {_(unit)}"
        n /= 1024
    return f"{n:.1f} {_('TB')}"


def _since(delta: timedelta) -> datetime:
    return datetime.now(UTC) - delta


def _session():

    return grunt.get_session()


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
            _("Database"),
            _("Connection"),
            OK if latency < 200 else WARNING,
            f"{dialect} {str(version).split(' on ')[0]} · {latency:.0f} {_('ms')}",
            "" if latency < 200 else _("Slow database response."),
        )
    ]
    size = await _database_size(session, dialect)
    if size is not None:
        rows.append(row(_("Database"), _("Size"), INFO, human_size(size)))
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
        details = _("kept for %(days)s days") % {"days": retention} if retention else ""
        if dt and dt.is_log and not retention:
            details = _("log: general log retention period")
        items.append({"label": name, "count": n, "details": details})
    return items


# ── Background jobs & scheduler ───────────────────────────────────────────


async def check_background_jobs() -> list[Row]:
    from grunt.tasks.redis_introspect import redis_conn, s, stream_broker

    cat = _("Background jobs")
    sb = stream_broker()
    if sb is None:
        return [
            row(
                cat,
                _("Job queue"),
                WARNING,
                _("in-process (no Redis)"),
                _(
                    "REDIS_URL is not set: jobs run inside the server process and are lost on "
                    "restart. Configure Redis and a worker for production."
                ),
            )
        ]
    async with redis_conn() as conn:
        assert conn is not None  # stream_broker() was checked above
        await conn.ping()
        consumers = await conn.xinfo_consumers(sb.queue_name, sb.consumer_group_name)
        groups = await conn.xinfo_groups(sb.queue_name)
    alive = [c for c in consumers if int(c.get("idle", 0)) < DEAD_WORKER_IDLE_MS]
    dead = len(consumers) - len(alive)
    rows = [row(cat, "Redis", OK, _("available"))]
    if not consumers:
        rows.append(
            row(
                cat,
                _("Workers"),
                ERROR,
                0,
                _("No worker is connected: background jobs are not running."),
            )
        )
    else:
        rows.append(
            row(
                cat,
                _("Workers"),
                OK if not dead else WARNING,
                _("%(count)s active") % {"count": len(alive)}
                + (", " + _("%(count)s idle") % {"count": dead} if dead else ""),
                _("A worker idle for over 10 min may have crashed; see Queue Workers.")
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
                _("Queue"),
                OK if lag < 100 else WARNING,
                _("%(queued)s queued, %(running)s running") % {"queued": lag, "running": pending},
                "" if lag < 100 else _("Jobs are piling up faster than they are processed."),
            )
        )
    return rows


async def check_scheduler() -> list[Row]:
    from grunt.tasks.scheduler import failed_jobs, scheduler

    cat = _("Scheduler")
    rows = [
        row(
            cat,
            _("Scheduler"),
            OK if scheduler.running else ERROR,
            _("running, %(count)s jobs") % {"count": len(scheduler.get_jobs())}
            if scheduler.running
            else _("stopped"),
            ""
            if scheduler.running
            else _("Scheduled jobs (mailings, cleanup, digests) are not running."),
        )
    ]
    rows.append(
        row(
            cat,
            _("Unregistered jobs"),
            ERROR if failed_jobs else OK,
            len(failed_jobs),
            "; ".join(f"{p}: {e}" for p, e in failed_jobs.items())
            + " — "
            + _("fix the path in scheduler_events (hooks.py).")
            if failed_jobs
            else "",
        )
    )
    failed = await grunt.db.count(
        "ScheduledJobLog", {"status": "Failed", "started_at__gte": _since(timedelta(days=1))}
    )
    rows.append(
        row(
            cat,
            _("Failed runs in the last day"),
            OK if not failed else WARNING,
            failed,
            _("Details in the Scheduled Job Log.") if failed else "",
        )
    )
    return rows


# ── Errors, email ─────────────────────────────────────────────────────────


async def check_errors() -> list[Row]:
    n = await grunt.db.count("ErrorLog", {"created_at__gte": _since(timedelta(days=1))})
    status = OK if n < ERRORS_WARN_PER_DAY else WARNING if n < ERRORS_ERROR_PER_DAY else ERROR
    return [
        row(
            _("Errors"),
            _("Errors in the last day"),
            status,
            n,
            _("See the Error Log.") if n else "",
        )
    ]


async def top_errors() -> list[Row]:
    rows = await grunt.db.aggregate(
        "ErrorLog",
        filters={"created_at__gte": _since(timedelta(days=7))},
        group_by="title",
        aggregations={"count": "count(name)"},
        order_by="count",
        limit=TOP_N,
    )
    return [
        {"label": r["title"] or "—", "count": r["count"], "details": _("in 7 days")} for r in rows
    ]


async def check_email() -> list[Row]:
    cat = _("Email")
    outgoing = await grunt.db.count("EmailAccount", {"enable_outgoing": 1})
    rows = [
        row(
            cat,
            _("Outgoing email account"),
            OK if outgoing else WARNING,
            outgoing,
            "" if outgoing else _("Emails (password reset, notifications) will not be sent."),
        )
    ]
    failed = await grunt.db.count(
        "EmailQueue", {"status": "Error", "created_at__gte": _since(timedelta(days=7))}
    )
    rows.append(row(cat, _("Sending errors in 7 days"), OK if not failed else WARNING, failed))
    stuck = await grunt.db.count(
        "EmailQueue",
        {"status__in": ["Pending", "Sending"], "created_at__lt": _since(STUCK_EMAIL_AFTER)},
    )
    rows.append(
        row(
            cat,
            _("Stuck emails"),
            OK if not stuck else WARNING,
            stuck,
            _("Emails have been waiting over 30 min; check the worker and SMTP.") if stuck else "",
        )
    )
    return rows


# ── Users & security ──────────────────────────────────────────────────────


async def check_users() -> list[Row]:
    cat = _("Users and security")
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
        row(cat, _("Active users"), INFO, active),
        row(cat, _("Active sessions"), INFO, sessions),
        row(
            cat,
            _("Administrators without 2FA"),
            OK if not without_mfa else WARNING,
            len(without_mfa),
            ", ".join(without_mfa[:5]) if without_mfa else "",
        ),
        row(cat, _("Locked accounts"), OK if not locked else WARNING, locked),
    ]


async def check_config() -> list[Row]:
    from grunt.config import DEFAULT_SECRET_KEY, settings

    cat = _("Configuration")
    return [
        row(
            cat,
            _("Debug mode"),
            WARNING if settings.debug else OK,
            _("enabled") if settings.debug else _("disabled"),
            _("DEBUG=true in production exposes extra error details.") if settings.debug else "",
        ),
        row(
            cat,
            _("Secret key"),
            ERROR if settings.secret_key == DEFAULT_SECRET_KEY else OK,
            _("default") if settings.secret_key == DEFAULT_SECRET_KEY else _("custom"),
            _("Set SECRET_KEY: with the default key, tokens can be forged.")
            if settings.secret_key == DEFAULT_SECRET_KEY
            else "",
        ),
    ]


# ── Storage ───────────────────────────────────────────────────────────────


async def check_storage() -> list[Row]:
    from grunt.site.manager import site_manager

    cat = _("Files")
    count = await grunt.db.count("File")
    [agg] = await grunt.db.aggregate("File", aggregations={"size": "sum(file_size)"})
    rows = [row(cat, _("Files"), INFO, f"{count} · {human_size(agg.get('size') or 0)}")]
    site_dir = site_manager.sites_dir / site_manager.get_active_site()
    usage = shutil.disk_usage(site_dir)
    free = usage.free / usage.total
    status = OK if free >= DISK_WARN_FREE else WARNING if free >= DISK_ERROR_FREE else ERROR
    rows.append(
        row(
            cat,
            _("Free disk space"),
            status,
            _("%(free)s of %(total)s")
            % {"free": human_size(usage.free), "total": human_size(usage.total)}
            + f" ({free:.0%})",
            "" if status == OK else _("Free up space: uploads and the database may stop working."),
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

    cat = _("WebSockets")
    channels = manager._connections
    users = {c for c, conns in channels.items() if c.startswith("user:") and conns}
    rows = [
        row(
            cat,
            _("Connections (this process)"),
            INFO,
            _("%(connections)s connections, %(users)s users")
            % {"connections": manager._total_connections(), "users": len(users)},
        )
    ]
    if not settings.redis_url:
        rows.append(
            row(
                cat,
                _("Cross-process relay"),
                INFO,
                _("no Redis"),
                _(
                    "Messages reach only this process's clients, which is enough for a single "
                    "server process without a separate worker."
                ),
            )
        )
        return rows

    from grunt.utils.redis import connect

    key = f"grunt:ws:__health__:{uuid.uuid4().hex}"
    r = connect(socket_connect_timeout=1)
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
        row(cat, _("Redis relay"), OK, f"{_('working')}, {got * 1000:.0f} {_('ms')}")
        if got is not None
        else row(
            cat,
            _("Redis relay"),
            ERROR,
            _("not working"),
            _(
                "Messages from the worker and other processes (import progress, notifications) "
                "will not reach the browser."
            ),
        )
    )
    listening = manager.redis_listener_alive or not channels
    rows.append(
        row(
            cat,
            _("Redis listener in this process"),
            OK if listening else WARNING,
            _("working") if manager.redis_listener_alive else _("not working"),
            ""
            if listening
            else _(
                "There are connections but the listener is down: Redis messages are not delivered."
            ),
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


# ── Backups ───────────────────────────────────────────────────────────────


async def check_backups() -> list[Row]:
    from grunt.backups import list_backups
    from grunt.site.manager import site_manager
    from grunt.site.settings import get_setting

    cat = _("Backups")
    site = site_manager.get_active_site()
    backups = list_backups(site)
    enabled = bool(await get_setting("backup_enabled", True))
    interval = int(await get_setting("backup_interval_hours", 24) or 24)
    rows = []
    if not enabled:
        rows.append(
            row(
                cat,
                _("Schedule"),
                WARNING,
                _("disabled"),
                _("Enable it in System Settings → Backups."),
            )
        )
    if not backups:
        rows.append(
            row(
                cat,
                _("Latest backup"),
                ERROR,
                _("none"),
                _("Click Create now in Backups, or run `grunt db backup`."),
            )
        )
        return rows
    last = backups[0]
    age = datetime.now(UTC) - last.created_at
    hours = age.total_seconds() / 3600
    # One missed run is a warning, two an error (the worker or scheduler is down).
    status = OK if hours < interval + 2 else WARNING if hours < 2 * interval + 2 else ERROR
    rows.append(
        row(
            cat,
            _("Latest backup"),
            status,
            _("%(hours)s h ago") % {"hours": f"{hours:.0f}"} + f" · {human_size(last.size())}",
            ""
            if status == OK
            else _(
                "Backups are not being created on schedule; check the worker and the error log."
            ),
        )
    )
    if "database" not in last.files:
        rows.append(row(cat, _("Database in the latest backup"), ERROR, _("missing")))
    rows.append(
        row(
            cat,
            _("Backups kept"),
            INFO,
            f"{len(backups)} · {human_size(sum(b.size() for b in backups))}",
        )
    )
    return rows


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
            _("App dependencies"),
            _("Apps' Python packages"),
            ERROR if missing else OK,
            _("%(count)s missing") % {"count": len(missing)}
            if missing
            else _("%(count)s apps, all installed") % {"count": len(apps)},
            (_("Run `grunt app deps`. Missing:") + " " + ", ".join(missing)) if missing else "",
        )
    ]


# ── Offline mode (server side) ────────────────────────────────────────────


async def check_offline_build() -> list[Row]:
    """The service worker exists only in the production build — check it is there."""
    import json

    cat = _("Offline mode")
    manifest = FRONTEND_DIST / "precache-manifest.json"
    if not manifest.exists():
        return [
            row(
                cat,
                _("Production build"),
                WARNING,
                _("missing"),
                _(
                    "No dist/precache-manifest.json: offline mode works only with a production "
                    "build (`npm run build`). In development (Vite dev) the service worker is "
                    "not registered."
                ),
            )
        ]
    files = json.loads(manifest.read_text())
    built = datetime.fromtimestamp(manifest.stat().st_mtime, UTC)
    rows = [
        row(
            cat,
            _("Production build"),
            OK,
            _("%(count)s files") % {"count": len(files)} + f", {built:%d.%m.%Y %H:%M} UTC",
        )
    ]
    dist_sw = FRONTEND_DIST / "sw.js"
    if not dist_sw.exists():
        rows.append(row(cat, _("Service worker in the build"), ERROR, _("missing")))
    elif SERVICE_WORKER_SRC.exists() and dist_sw.read_bytes() != SERVICE_WORKER_SRC.read_bytes():
        rows.append(
            row(
                cat,
                _("Service worker in the build"),
                WARNING,
                _("outdated"),
                _("public/sw.js changed after the build; rebuild the frontend."),
            )
        )
    else:
        rows.append(row(cat, _("Service worker in the build"), OK, _("up to date")))
    return rows


# ── Runner ────────────────────────────────────────────────────────────────

CHECKS: list[tuple[str, Callable[[], Awaitable[list[Row]]]]] = [
    (N_("Database"), check_database),
    (N_("Background jobs"), check_background_jobs),
    (N_("Scheduler"), check_scheduler),
    (N_("Errors"), check_errors),
    (N_("Email"), check_email),
    (N_("Users and security"), check_users),
    (N_("Configuration"), check_config),
    (N_("Files"), check_storage),
    (N_("Backups"), check_backups),
    (N_("WebSockets"), check_realtime),
    (N_("App dependencies"), check_app_dependencies),
    (N_("Offline mode"), check_offline_build),
]


async def _safe(category: str, fn: Callable[[], Awaitable[Any]]) -> Any:
    try:
        # Savepoint: on PostgreSQL a failed query would poison the whole transaction.
        async with _session().begin_nested():
            return await fn()
    except Exception as e:  # noqa: BLE001 - a broken subsystem is a finding, not a crash
        log.warning("health.check_failed", check=fn.__name__, error=str(e))
        return [
            row(_(category), fn.__name__.removeprefix("check_"), ERROR, _("check failed"), str(e))
        ]


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
