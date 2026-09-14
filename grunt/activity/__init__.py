from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import grunt as _grunt
from grunt.app import grunt
from grunt.document.versioning import _SKIP_FIELDS
from grunt.log import log


async def _doctype_meta(doctype: str):
    """Best-effort metadata lookup — unknown doctypes are treated as "log it"."""
    from grunt.metadata.registry import doctype_registry

    try:
        return await doctype_registry.get(doctype)
    except Exception:
        return None


async def should_log_activity(doctype: str) -> bool:
    """Whether ``doctype`` writes ActivityLog rows at all (``DocType.track_activity``)."""
    dt = await _doctype_meta(doctype)
    return getattr(dt, "track_activity", True) if dt is not None else True


def _feed_hidden(dt: Any) -> bool:
    """True for doctypes that never log at all (``track_activity=False``) as well as
    ones that log but opt out of the global feed only (``hide_from_activity_feed``)
    — config/admin records that stay visible in a specific document's own timeline.
    """
    return not getattr(dt, "track_activity", True) or getattr(dt, "hide_from_activity_feed", False)


async def is_feed_hidden(doctype: str | None) -> bool:
    """Whether a doctype's entries should be excluded from the *global* activity feed."""
    if not doctype:
        return False
    dt = await _doctype_meta(doctype)
    return _feed_hidden(dt) if dt is not None else False


async def feed_hidden_doctypes() -> list[str]:
    """All doctype names currently excluded from the global activity feed."""
    from grunt.metadata.registry import doctype_registry

    return [dt.name for dt in await doctype_registry.list_all() if _feed_hidden(dt)]


_ACTION_MAP = {
    "after_insert": "Create",
    "after_update": "Update",
    "after_delete": "Delete",
}


async def record_activity(
    doctype: str,
    doc_id: str,
    action: str,
    *,
    user_email: str,
    details: dict | None = None,
    broadcast: bool = True,
) -> None:
    """Write one ActivityLog entry and (optionally) broadcast it live.

    The single write path for the activity feed. Must be called within an
    active grunt context (ambient session/user). Skips system churn centrally.

    Writes as SYSTEM_USER, not the ambient caller: `create` on ActivityLog
    is restricted to System Manager (write/delete always were, to keep the
    audit trail tamper-proof) precisely so a regular user can't forge an
    entry via the generic docs CRUD — attributing an action to someone else,
    or inventing one that never happened. This is the *only* legitimate
    write path, so it must work regardless of the acting user's own role.
    """
    if not doctype or not await should_log_activity(doctype):
        return
    try:
        async with grunt.system_context(grunt._require_session()):
            doc = await grunt.new_doc(
                "ActivityLog",
                {
                    "doctype": doctype,
                    "doc_id": str(doc_id),
                    "user": user_email,
                    "action": action,
                    "details": details,
                },
            )
    except Exception as e:
        log.warning("activity.log_failed", error=str(e), doctype=doctype, doc_id=doc_id)
        return

    if broadcast:
        await _broadcast_activity(doc, doctype, str(doc_id), action, user_email)


async def _broadcast_activity(
    doc: dict[str, Any], doctype: str, doc_id: str, action: str, user_email: str
) -> None:
    """Push a live activity event to the global site WebSocket channel.

    Resolves the document title and the user's full name up front — same as
    the REST feed (``list_activity``) — so a live-pushed entry never flashes a
    raw doc_id/email while the feed's own re-fetch would have shown a name.
    """
    try:
        from grunt.api.v1.ws import manager
        from grunt.document.titles import resolve_reference_titles

        titles = await resolve_reference_titles([(doctype, doc_id)])
        title = titles.get((doctype, doc_id)) or doc_id

        user_name = user_email
        try:
            # System context: the "All" role can only read its own User row
            # (match: name == user) — the broadcaster must resolve the
            # *acting* user's name regardless of who ends up viewing the feed.
            async with grunt.system_context(grunt._require_session()):
                rows = await grunt.get_list(
                    "User", filters={"name": user_email}, fields=["full_name"], limit=1
                )
            if rows and rows[0].get("full_name"):
                user_name = rows[0]["full_name"]
        except Exception:
            pass

        created_at = doc.get("created_at")
        # "site" is the authenticated site-wide channel. Never "public:site" —
        # that endpoint takes no token, which would stream user emails and
        # document ids to anyone who knows the URL.
        await manager.broadcast(
            "site",
            "activity",
            {
                "name": doc.get("name"),
                "doctype": doctype,
                "doc_id": doc_id,
                "title": title,
                "action": action,
                "user": user_email,
                "user_name": user_name,
                "created_at": created_at.isoformat()
                if isinstance(created_at, datetime)
                else str(created_at or ""),
            },
        )
    except Exception:
        log.debug("activity.broadcast_failed", doctype=doctype, doc_id=doc_id)


async def log_activity(event: str, **kwargs) -> None:
    """Hook adapter: map a lifecycle event to an ActivityLog entry."""
    action = _ACTION_MAP.get(event)
    doc = kwargs.get("doc") or kwargs.get("doc_id")
    user = kwargs.get("user")
    doctype = kwargs.get("doctype")

    if not action or not doc or not user or not doctype:
        return

    doc_id = str(doc.get("name") or "") if isinstance(doc, dict) else str(doc)
    if not doc_id:
        return
    user_email = user.email if hasattr(user, "email") else str(user)

    details: dict | None = None
    if action == "Update":
        changed = [f for f in (kwargs.get("changed_fields") or []) if f not in _SKIP_FIELDS]
        if changed:
            details = {"changed_fields": changed}

    await record_activity(doctype, doc_id, action, user_email=user_email, details=details)


# View-log throttle: at most one ViewLog row per (user, document) per hour.
_VIEW_LOG_THROTTLE = timedelta(hours=1)


async def record_view(event: str, **kwargs: Any) -> None:
    """``after_read`` hook: record per-user "seen" state and ViewLog entries.

    Acts only for DocTypes that opt in via ``track_seen`` / ``track_views``, and
    only for single-document reads — the ``after_read`` fired by list, get_value
    and get_all passes ``method=`` and/or no ``doc`` dict, so those are skipped.
    """
    from grunt.metadata.registry import doctype_registry

    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    if kwargs.get("method") or not doctype or not isinstance(doc, dict):
        return
    doc_id = doc.get("name")
    if not doc_id:
        return

    try:
        dt = await doctype_registry.get(doctype)
    except Exception:
        return
    # ``track_activity`` is not consulted here: seen/view tracking is a separate,
    # opt-in concern via the flags below — none of the high-churn system logs set
    # them. An operational log that *does* opt in (e.g. ErrorLog, so an admin can
    # tell which errors they've already triaged) is honoured regardless.
    if not (getattr(dt, "track_seen", False) or getattr(dt, "track_views", False)):
        return

    user_obj = kwargs.get("user")
    user_email = getattr(user_obj, "email", None) or str(user_obj or "")
    if not user_email or user_email in ("guest@grunt.local", "system", "Guest"):
        return

    session = grunt._require_session()

    if getattr(dt, "track_seen", False):
        seen = doc.get("_seen")
        seen = list(seen) if isinstance(seen, list) else []
        if user_email not in seen:
            seen.append(user_email)
            try:
                async with grunt.system_context(session):
                    await grunt.db.set_value(doctype, str(doc_id), "_seen", seen)
                doc["_seen"] = seen
            except Exception as e:
                log.warning("view.seen_failed", error=str(e), doctype=doctype, doc_id=doc_id)

    if getattr(dt, "track_views", False):
        try:
            async with grunt.system_context(session):
                recent = await grunt.db.get_all(
                    "ViewLog",
                    filters={
                        "doctype": doctype,
                        "doc_id": str(doc_id),
                        "viewed_by": user_email,
                        "viewed_at__gte": datetime.now(UTC) - _VIEW_LOG_THROTTLE,
                    },
                    fields=["name"],
                    limit=1,
                )
                if not recent:
                    await grunt.new_doc(
                        "ViewLog",
                        {
                            "doctype": doctype,
                            "doc_id": str(doc_id),
                            "viewed_by": user_email,
                            "viewed_at": datetime.now(UTC),
                        },
                    )
        except Exception as e:
            log.warning("view.log_failed", error=str(e), doctype=doctype, doc_id=doc_id)


@_grunt.whitelist()
async def get_view_info(doctype: str, doc_id: str) -> dict[str, Any]:
    """Return ``{"seen": [...emails], "views": <int>, "viewers": <int>}`` for a document.

    ``seen`` comes from the document's ``_seen`` column (track_seen); ``views`` is
    the total ViewLog row count and ``viewers`` the distinct viewer count
    (track_views). Fields the DocType hasn't opted into come back empty/zero.
    """
    from grunt.metadata.registry import doctype_registry

    dt = await doctype_registry.get(doctype)
    out: dict[str, Any] = {"seen": [], "views": 0, "viewers": 0}

    if getattr(dt, "track_seen", False):
        seen = await grunt.db.get_value(doctype, doc_id, "_seen")
        out["seen"] = seen if isinstance(seen, list) else []

    if getattr(dt, "track_views", False):
        rows = await grunt.db.get_all(
            "ViewLog",
            filters={"doctype": doctype, "doc_id": str(doc_id)},
            fields=["viewed_by"],
            limit=100000,
        )
        out["views"] = len(rows)
        out["viewers"] = len({r["viewed_by"] for r in rows})

    return out
