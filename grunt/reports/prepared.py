"""Prepared reports - a heavy report calculated in the background.

A ``Report`` with ``prepared_report`` set doesn't run on screen. The viewer
asks for it (:func:`prepare`): a ``PreparedReport`` row is queued and a worker
runs the report *as that user* (their permissions, so the result is theirs
alone - ``PreparedReport`` is readable by its ``user``), stores the result as
a private gzipped-JSON ``File`` attached to the row and pings the user over
the websocket. Opening the report shows the latest result for the same
filters (:func:`latest`); "Recalculate" queues a new one.

One result per report, user and filters is kept - a finished run removes the
older ones; ``retention_days`` on the DocType removes the rest.
"""

import gzip
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from grunt.db.api import GruntDB
from grunt.errors import ApplicationError
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.publish import publish
from grunt.reports.engine import report_engine
from grunt.site.manager import site_manager
from grunt.storage.backends import get_storage_backend
from grunt.storage.files import create_file
from grunt.storage.files import read as read_file
from grunt.tasks.broker import task
from grunt.tasks.enqueue import enqueue
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

#: Realtime event a user gets when their prepared report is done (or failed).
EVENT = "prepared_report"

PENDING = ("Queued", "Started")

#: A pending run older than this (plus the report's own timeout) is taken for
#: lost - a worker stopped mid-run, a broker dropped the task - and replaced.
STALE_AFTER = timedelta(hours=1)

_FIELDS = [
    "name",
    "report",
    "status",
    "filters",
    "started_at",
    "finished_at",
    "rows",
    "time_ms",
    "error",
    "result_file",
    "created_at",
]


def filters_hash(filters: dict[str, Any] | None) -> str:
    """Key of a filter set - the same filters in any order hash alike."""
    canonical = json.dumps(filters or {}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


async def latest(
    report_id: str, user: str, filters: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The newest ``PreparedReport`` of *user* for *report_id* and *filters* - any status."""
    rows = await _db.get_all(
        "PreparedReport",
        filters={"report": report_id, "user": user, "filters_hash": filters_hash(filters)},
        fields=_FIELDS,
        order_by="created_at",
        order="desc",
        limit=1,
    )
    return rows[0] if rows else None


async def prepare(
    report: dict[str, Any], filters: dict[str, Any] | None, user: str
) -> dict[str, Any]:
    """Queue *report* (a row ``report_engine.load`` returned for *user*) with
    *filters*; an unfinished run for the same filters is returned instead."""
    current = await latest(report["name"], user, filters)
    if current and current["status"] in PENDING:
        if not _stale(current, report):
            return current
        await _db.set_value(
            "PreparedReport",
            current["name"],
            {"status": "Error", "error": "Interrupted: the background run didn't finish"},
        )
    now = datetime.now(UTC)
    row = {
        "name": uuid.uuid4().hex,
        "owner": user,
        "created_at": now,
        "modified_at": now,
        "modified_by": user,
        "report": report["name"],
        "user": user,
        "status": "Queued",
        "filters": filters or {},
        "filters_hash": filters_hash(filters),
    }
    async with system_context(require_session()):
        await _db.insert_one("PreparedReport", row)
    enqueue(generate, site=site_manager.get_active_site(), prepared_id=row["name"])
    log.info("reports.prepared_queued", report=report.get("report_name"), user=user)
    return {k: row.get(k) for k in _FIELDS}


def _aware(value: datetime | str | None) -> datetime | None:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def _stale(row: dict[str, Any], report: dict[str, Any]) -> bool:
    """A pending *row* nobody will finish any more."""
    since = _aware(row.get("started_at") if row["status"] == "Started" else row.get("created_at"))
    limit = STALE_AFTER + timedelta(seconds=report.get("timeout") or 0)
    return since is not None and datetime.now(UTC) - since > limit


async def load_result(prepared: dict[str, Any]) -> dict[str, Any] | None:
    """The stored ``{columns, data, meta}`` of a completed *prepared* row."""
    if prepared.get("status") != "Completed" or not prepared.get("result_file"):
        return None
    return json.loads(gzip.decompress(await read_file(prepared["result_file"])))


def _error_text(exc: BaseException) -> str:
    detail = getattr(exc, "detail", None) or getattr(exc, "message", None)
    return str(detail or exc) or type(exc).__name__


async def _store_result(prepared_id: str, user: str, result: dict[str, Any]) -> str:
    content = gzip.compress(json.dumps(result, default=str, ensure_ascii=False).encode())
    key, size = await get_storage_backend().put(content)
    file = await create_file(
        key,
        size,
        f"{prepared_id}.json.gz",
        "application/gzip",
        attached_to_doctype="PreparedReport",
        attached_to_id=prepared_id,
        uploaded_by=user,
    )
    return str(file["name"])


async def _drop_older(prepared: dict[str, Any]) -> None:
    """Remove the finished runs this one replaces (with their files)."""
    older = await _db.get_all(
        "PreparedReport",
        filters={
            "report": prepared["report"],
            "user": prepared["user"],
            "filters_hash": prepared["filters_hash"],
            "status__in": ["Completed", "Error"],
            "name__ne": prepared["name"],
            # Only older runs: a slower, older run finishing last keeps a newer result.
            "created_at__lt": prepared["created_at"],
        },
        pluck="name",
        limit=None,
    )
    for name in older:
        await documents.delete_doc("PreparedReport", name)


async def run_prepared(prepared_id: str) -> None:
    """Calculate the ``PreparedReport`` *prepared_id* - inside a system context."""
    session = require_session()
    rows = await _db.get_all(
        "PreparedReport",
        filters={"name": prepared_id},
        fields=["name", "report", "user", "status", "filters", "filters_hash", "created_at"],
        limit=1,
    )
    if not rows or rows[0]["status"] != "Queued":
        return  # deleted meanwhile, or already picked up
    prepared = rows[0]
    user = prepared["user"]
    await _db.set_value(
        "PreparedReport", prepared_id, {"status": "Started", "started_at": datetime.now(UTC)}
    )
    await session.commit()

    report_name: str | None = None
    start = time.monotonic()
    values: dict[str, Any]
    try:  # from here on every way out records a terminal status
        report_name = await _db.get_value("Report", prepared["report"], "report_name")
        if not report_name:
            raise ApplicationError("Report not found", code="NOT_FOUND")
        report = await report_engine.load(report_name, user, session)
        result = await report_engine.execute(
            report, prepared.get("filters") or {}, user, session, background=True
        )
        values = {
            "status": "Completed",
            "result_file": await _store_result(prepared_id, user, result),
            "rows": len(result.get("data") or []),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - the error is the run's outcome
        await session.rollback()
        log.warning("reports.prepared_failed", report=report_name, user=user, error=str(exc))
        values = {"status": "Error", "error": _error_text(exc)}
    values["finished_at"] = datetime.now(UTC)
    values["time_ms"] = int((time.monotonic() - start) * 1000)
    await _db.set_value("PreparedReport", prepared_id, values)
    if values["status"] == "Completed":
        await _drop_older(prepared)
    await publish(
        user=user,
        event=EVENT,
        data={"report": report_name, "name": prepared_id, "status": values["status"]},
    )
    await session.commit()


@task
async def generate(*, site: str, prepared_id: str) -> None:
    """Worker side of :func:`prepare`."""
    maker = site_manager.get_session_maker(site)
    engine = site_manager.get_engine(site)
    async with maker() as session, system_context(session, engine):
        await run_prepared(prepared_id)
