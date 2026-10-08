"""Milestones - when a document entered each value of a field, and for how long.

A ``MilestoneTracker`` names a DocType and a field (its status by default).
Every save that changes that field closes the open ``Milestone`` row (stamps
``left_at`` and ``duration_hours``) and opens one for the new value, so

    grunt.aggregate("Milestone", filters={"ref_doctype": "IncomingLetter"},
                    group_by="value", aggregations={"avg": "avg(duration_hours)"})

answers "how long do letters stay in each status" - with the viewer's
permissions, since milestone rows inherit read access from their document.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import grunt
from grunt import log

TRACKER = "MilestoneTracker"
MILESTONE = "Milestone"
MAX_SEED = 100_000

_CACHE_TTL = 60.0
_trackers: dict[str, list[str]] | None = None
_loaded_at = 0.0


def invalidate(**_kwargs: object) -> None:
    """Doc-event hook for MilestoneTracker changes; also the test reset."""
    global _trackers
    _trackers = None


async def tracked_fields(doctype: str) -> list[str]:
    """Fields tracked on *doctype* (cached - the save hook runs on every DocType)."""
    global _trackers, _loaded_at
    if doctype in (TRACKER, MILESTONE):
        return []
    if _trackers is None or time.monotonic() - _loaded_at > _CACHE_TTL:
        async with grunt.system_context(grunt.get_session()):
            rows = await grunt.db.get_all(
                TRACKER,
                filters={"disabled": False},
                fields=["ref_doctype", "track_field"],
                limit=10_000,
            )
        grouped: dict[str, list[str]] = {}
        for row in rows:
            grouped.setdefault(row["ref_doctype"], []).append(row["track_field"])
        _trackers, _loaded_at = grouped, time.monotonic()
    return _trackers.get(doctype, [])


def _value(doc: dict[str, Any], field: str) -> str:
    value = doc.get(field)
    return "" if value is None else str(value)


def _hours(start: Any, end: datetime) -> float:
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return round(max((end - start).total_seconds(), 0) / 3600, 2)


async def _open_row(doctype: str, name: str, field: str) -> dict[str, Any] | None:
    rows = await grunt.db.get_all(
        MILESTONE,
        filters={
            "ref_doctype": doctype,
            "ref_name": name,
            "track_field": field,
            "left_at__isnull": True,
        },
        order_by="entered_at",
        order="desc",
        limit=1,
    )
    return rows[0] if rows else None


async def record(
    doctype: str,
    doc: dict[str, Any],
    field: str,
    *,
    user: str | None = None,
    at: datetime | None = None,
    approximate: bool = False,
) -> bool:
    """Bring *doc*'s milestones for *field* up to date; True when a row was opened."""
    now = at or datetime.now(UTC)
    value = _value(doc, field)
    current = await _open_row(doctype, str(doc["name"]), field)
    if current is not None:
        if current["value"] == value:
            return False
        await grunt.db.set_value(
            MILESTONE,
            current["name"],
            {"left_at": now, "duration_hours": _hours(current["entered_at"], now)},
        )
    await grunt.new_doc(
        MILESTONE,
        {
            "ref_doctype": doctype,
            "ref_name": str(doc["name"]),
            "track_field": field,
            "value": value,
            "previous_value": current["value"] if current else None,
            "entered_at": now,
            "entered_by": user,
            "approximate": approximate,
        },
    )
    return True


async def on_document_saved(**kwargs: Any) -> None:
    """``after_save`` on every DocType: open/close milestones of tracked fields."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    if not doctype or not isinstance(doc, dict) or not doc.get("name"):
        return
    fields = await tracked_fields(doctype)
    if not fields:
        return
    user = getattr(kwargs.get("user"), "email", None)
    async with grunt.system_context(grunt.get_session()):
        for field in fields:
            try:
                await record(doctype, doc, field, user=user)
            except Exception:
                log.exception("milestone.record_failed", doctype=doctype, doc=doc.get("name"))


async def on_document_deleted(**kwargs: Any) -> None:
    """``after_delete`` on every DocType: drop that document's milestones."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    name = doc.get("name") if isinstance(doc, dict) else kwargs.get("doc_id")
    if not doctype or not name or not await tracked_fields(doctype):
        return
    async with grunt.system_context(grunt.get_session()):
        await grunt.db.delete(MILESTONE, {"ref_doctype": doctype, "ref_name": name})


async def seed(doctype: str, field: str) -> int:
    """Open a milestone for every existing document that has none for *field*.

    The real entry time is unknown, so the document's last modification is
    used and the row is marked ``approximate``. Returns rows created.
    """
    created = 0
    rows = await grunt.db.get_all(doctype, fields=["name", field, "modified_at"], limit=MAX_SEED)
    for row in rows:
        if await _open_row(doctype, str(row["name"]), field) is not None:
            continue
        at = row.get("modified_at") or datetime.now(UTC)
        if isinstance(at, str):
            at = datetime.fromisoformat(at)
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        await record(doctype, dict(row), field, at=at, approximate=True)
        created += 1
    log.info("milestone.seeded", doctype=doctype, field=field, rows=created)
    return created


async def history(doctype: str, name: str) -> list[dict[str, Any]]:
    """A document's milestones, oldest first - for the form sidebar."""
    if not await tracked_fields(doctype):
        return []
    rows = await grunt.get_list(
        MILESTONE,
        filters={"ref_doctype": doctype, "ref_name": name},
        fields=[
            "name",
            "track_field",
            "value",
            "entered_at",
            "left_at",
            "duration_hours",
            "approximate",
        ],
        order_by="entered_at",
        order="asc",
        limit=200,
        include_total=False,
    )
    return [dict(r) for r in rows]
