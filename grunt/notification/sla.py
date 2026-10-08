"""Service levels (SLA) - deadlines on documents, early warnings, escalation.

A ``ServiceLevel`` policy says: documents of DocType X (optionally matching a
condition) must reach a "done" status within N hours / days / working days.
For every such document a ``ServiceLevelStatus`` row tracks the clock:

    On track -> At risk (warned) -> Breached (escalated)
             \\-> Met / Met late (done)

- :func:`on_document_saved` (``after_save`` hook, every DocType) starts the
  clock, follows a hand-edited deadline field, and stops it when done.
- :func:`check_deadlines` (scheduler, every 10 minutes) sends the warnings and
  breach escalations.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import grunt
from grunt import _, log
from grunt.config import settings
from grunt.tasks.broker import retryable_task

POLICY = "ServiceLevel"
STATUS = "ServiceLevelStatus"
OPEN_STATES = ("On track", "At risk", "Breached")

_CACHE_TTL = 60.0
_policies: dict[str, list[dict[str, Any]]] | None = None
_loaded_at = 0.0


# Policy cache


def invalidate(**_kwargs: object) -> None:
    """Doc-event hook for ServiceLevel changes; also the test reset."""
    global _policies
    _policies = None


async def policies_for(doctype: str) -> list[dict[str, Any]]:
    """Enabled policies of *doctype* - cached, so the hook on every save is cheap."""
    global _policies, _loaded_at
    if doctype in (POLICY, STATUS):
        return []
    if _policies is None or time.monotonic() - _loaded_at > _CACHE_TTL:
        async with grunt.system_context(grunt.get_session()):
            rows = await grunt.db.get_all(POLICY, filters={"is_enabled": True}, limit=10_000)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["ref_doctype"], []).append(dict(row))
        _policies, _loaded_at = grouped, time.monotonic()
    return _policies.get(doctype, [])


# Time arithmetic


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.default_timezone)


def as_datetime(value: Any, *, end_of_day: bool = False) -> datetime | None:
    """A Date/Datetime value as an aware UTC datetime.

    A bare date means local midnight - or the end of that local day for a
    deadline (``end_of_day``), so "due on the 15th" lasts the whole day.
    """
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        value = date.fromisoformat(text) if len(text) == 10 else datetime.fromisoformat(text)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)
    if isinstance(value, date):
        local = datetime(value.year, value.month, value.day, tzinfo=_tz())
        if end_of_day:
            local += timedelta(days=1, microseconds=-1)
        return local.astimezone(UTC)
    return None


def deadline(start: datetime, target: int, unit: str) -> datetime:
    """*start* plus *target* hours / days / working days (Mon-Fri, local time).

    Day-based deadlines end at the close of the local day they fall on.
    """
    if unit == "Hours":
        return start + timedelta(hours=target)
    day = start.astimezone(_tz()).date()
    if unit == "Working days":
        left = target
        while left > 0:
            day += timedelta(days=1)
            if day.weekday() < 5:
                left -= 1
    else:
        day += timedelta(days=target)
    result = as_datetime(day, end_of_day=True)
    assert result is not None
    return result


# Policy evaluation


def _eval(expr: str | None, doc: dict[str, Any]) -> bool | None:
    """Evaluate a policy expression; ``None`` when empty, ``False`` when it fails."""
    if not (expr or "").strip():
        return None
    from simpleeval import simple_eval

    try:
        return bool(simple_eval(expr, names={"doc": doc}))
    except Exception:
        log.warning("sla.expression_failed", expression=expr)
        return False


async def _is_done(policy: dict[str, Any], doctype: str, doc: dict[str, Any]) -> bool:
    states = {s.strip() for s in (policy.get("done_states") or "").splitlines() if s.strip()}
    if states:
        meta = await grunt.get_meta(doctype)
        status_field = getattr(getattr(meta, "doc", None), "status_field", None) or "status"
        if str(doc.get(status_field) or "") in states:
            return True
    return bool(_eval(policy.get("done_condition"), doc))


async def _planned_due(policy: dict[str, Any], doc: dict[str, Any]) -> datetime | None:
    """The deadline: a hand-set deadline field wins, else start + allowed time."""
    if due := as_datetime(doc.get(policy.get("due_field") or ""), end_of_day=True):
        return due
    start = as_datetime(doc.get(policy.get("start_field") or "created_at")) or datetime.now(UTC)
    return deadline(start, int(policy["target"]), policy.get("target_unit") or "Days")


def _status_for(due: datetime, warn_hours: int, now: datetime) -> str:
    if now > due:
        return "Breached"
    if warn_hours and now >= due - timedelta(hours=warn_hours):
        return "At risk"
    return "On track"


# Hooks


async def on_document_saved(**kwargs: Any) -> None:
    """``after_save`` on every DocType: start, adjust or stop SLA clocks."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    if not doctype or not isinstance(doc, dict) or not doc.get("name"):
        return
    policies = await policies_for(doctype)
    if not policies:
        return
    async with grunt.system_context(grunt.get_session()):
        for policy in policies:
            try:
                await _track(policy, doctype, doc)
            except Exception:
                log.exception("sla.track_failed", policy=policy["name"], doc=doc.get("name"))


async def _track(policy: dict[str, Any], doctype: str, doc: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    rows = await grunt.db.get_all(
        STATUS,
        filters={"service_level": policy["name"], "ref_doctype": doctype, "ref_name": doc["name"]},
        limit=1,
    )
    row = rows[0] if rows else None
    done = await _is_done(policy, doctype, doc)

    if row is None:
        if done or _eval(policy.get("condition"), doc) is False:
            return
        due = await _planned_due(policy, doc)
        assert due is not None
        await grunt.new_doc(
            STATUS,
            {
                "service_level": policy["name"],
                "ref_doctype": doctype,
                "ref_name": doc["name"],
                "started_at": now,
                "due_at": due,
                "status": _status_for(due, 0, now),
            },
        )
        await _fill_due_field(policy, doctype, doc, due)
        return

    if row["status"] not in OPEN_STATES:
        return  # history: the clock already stopped
    due = as_datetime(row["due_at"])
    assert due is not None
    if done:
        late = row["status"] == "Breached" or now > due
        status = "Met late" if late else "Met"
        await grunt.db.set_value(STATUS, row["name"], {"status": status, "met_at": now})
        return
    # A deadline edited by hand on the document moves the clock.
    planned = as_datetime(doc.get(policy.get("due_field") or ""), end_of_day=True)
    if planned and planned != due:
        await grunt.db.set_value(
            STATUS,
            row["name"],
            {
                "due_at": planned,
                "status": _status_for(planned, 0, now),
                "warned_at": None,
                "breached_at": None,
            },
        )


async def _fill_due_field(
    policy: dict[str, Any], doctype: str, doc: dict[str, Any], due: datetime
) -> None:
    field = policy.get("due_field")
    if not field or doc.get(field):
        return
    meta = await grunt.get_meta(doctype)
    fdef = meta.get_field(field) if meta else None
    if fdef is None:
        return
    value: Any = due.astimezone(_tz()).date() if fdef.fieldtype == "Date" else due
    await grunt.db.set_value(doctype, doc["name"], field, value)
    doc[field] = value


async def on_document_deleted(**kwargs: Any) -> None:
    """``after_delete`` on every DocType: drop that document's SLA rows."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    name = doc.get("name") if isinstance(doc, dict) else kwargs.get("doc_id")
    if not doctype or not name or not await policies_for(doctype):
        return
    async with grunt.system_context(grunt.get_session()):
        await grunt.db.delete(STATUS, {"ref_doctype": doctype, "ref_name": name})


# Scheduler


async def _recipients(spec: str | None, doctype: str, doc: dict[str, Any]) -> set[str]:
    """Resolve a recipients spec (NotificationRule syntax + ``{field:link.field}``)."""
    from grunt.notification.service import notification_service

    plain: list[str] = []
    emails: set[str] = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if part.startswith("{field:") and part.endswith("}") and "." in part:
            link_field, target_field = part[7:-1].split(".", 1)
            meta = await grunt.get_meta(doctype)
            fdef = meta.get_field(link_field) if meta else None
            if fdef and fdef.fieldtype == "Link" and fdef.options and doc.get(link_field):
                value = await grunt.db.get_value(fdef.options, doc[link_field], target_field)
                if isinstance(value, str) and "@" in value:
                    emails.add(value)
        elif part:
            plain.append(part)
    found, roles = notification_service._resolve_recipients(",".join(plain), doc, "")
    emails.update(found)
    if roles:
        emails.update(
            await notification_service._resolve_role_recipients(roles, grunt.get_session())
        )
    return emails


async def _notify(policy: dict[str, Any], row: dict[str, Any], *, breached: bool) -> None:
    from grunt.notification.service import notification_service

    doctype, name = row["ref_doctype"], row["ref_name"]
    doc = await grunt.db.get_doc(doctype, name)
    if doc is None:
        return
    recipients = await _recipients(policy.get("notify"), doctype, doc)
    if breached:
        recipients |= await _recipients(policy.get("escalate_to"), doctype, doc)
    due = as_datetime(row["due_at"])
    assert due is not None
    when = due.astimezone(_tz()).strftime("%Y-%m-%d %H:%M")
    params = {"doctype": _(doctype), "name": name, "due": when}
    if breached:
        subject = _("Deadline missed: %(doctype)s %(name)s") % params
    else:
        subject = _("Deadline approaching: %(doctype)s %(name)s") % params
    message = _("%(policy)s - due %(due)s") % {"policy": policy["title"], "due": when}
    email = policy.get("channel") in ("email", "both")
    for user in sorted(recipients):
        await notification_service.notify(
            grunt.get_session(),
            user=user,
            doctype=doctype,
            doc_id=name,
            subject=subject,
            message=message,
            email=email,
        )


async def process_deadlines(now: datetime | None = None) -> dict[str, int]:
    """Warn and escalate open SLA rows; runs inside a system context."""
    now = now or datetime.now(UTC)
    counts = {"warned": 0, "breached": 0}
    rows = await grunt.db.get_all(
        STATUS,
        filters={"status__in": ["On track", "At risk"]},
        order_by="due_at",
        order="asc",
        limit=10_000,
    )
    policies: dict[str, dict[str, Any] | None] = {}
    for row in rows:
        name = row["service_level"]
        if name not in policies:
            policies[name] = await grunt.db.get_doc(POLICY, name)
        policy = policies[name]
        due = as_datetime(row["due_at"])
        if policy is None or due is None:
            continue
        status = _status_for(due, int(policy.get("warn_before") or 0), now)
        if status == row["status"]:
            continue
        stamp = "breached_at" if status == "Breached" else "warned_at"
        await grunt.db.set_value(STATUS, row["name"], {"status": status, stamp: now})
        try:
            await _notify(policy, row, breached=status == "Breached")
        except Exception:
            log.exception("sla.notify_failed", status_row=row["name"])
        counts["breached" if status == "Breached" else "warned"] += 1
    if any(counts.values()):
        log.info("sla.deadlines_processed", **counts)
    return counts


@retryable_task()
async def check_deadlines() -> dict[str, int]:
    """Scheduler entry point (every 10 minutes)."""
    from grunt.site.manager import site_manager

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        counts = await process_deadlines()
        await session.commit()
    return counts
