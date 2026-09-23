"""ErrorLog — the journal of unhandled framework/app errors.

Covers the DocType shape (append-only log, opt-in seen tracking), the
``grunt.log_error`` write path, the fact that seen tracking now works for an
opt-in operational log, and the settings-driven retention fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.rbac import permission_checker
from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

_ERROR_LOG_JSON = (
    Path(__file__).resolve().parents[2] / "grunt/monitoring/doctypes/ErrorLog/ErrorLog.json"
)


def _load() -> DocType:
    return DocType.model_validate(json.loads(_ERROR_LOG_JSON.read_text(encoding="utf-8")))


def _plain_user() -> User:
    return make_user("plain@example.com")


def _system_manager() -> User:
    return make_user("admin@example.com", roles=["System Manager"])


# ── DocType shape ────────────────────────────────────────────────────────


def test_error_log_is_a_seen_tracking_log():
    dt = _load()
    assert dt.is_log is True
    assert dt.track_seen is True
    assert dt.track_changes is False
    # No per-DocType retention override — it must fall back to SystemSettings.
    assert dt.retention_days is None


def test_error_log_permissions_are_read_delete_for_system_manager_only():
    assert _load().permissions


@pytest.mark.asyncio
async def test_plain_user_has_no_access():
    dt = _load()
    for action in ("read", "write", "create", "delete"):
        assert await permission_checker.check(_plain_user(), dt, action) is False


@pytest.mark.asyncio
async def test_system_manager_can_read_and_delete_but_not_write():
    dt = _load()
    admin = _system_manager()
    assert await permission_checker.check(admin, dt, "read") is True
    assert await permission_checker.check(admin, dt, "delete") is True
    assert await permission_checker.check(admin, dt, "write") is False
    assert await permission_checker.check(admin, dt, "create") is False


# ── grunt.log_error write path ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_error_from_exception(ctx):
    from grunt.monitoring.error_log import record_error

    session = ctx.db._session()
    try:
        raise ValueError("boom happened")
    except ValueError as exc:
        name = await record_error(
            exc=exc,
            context="Controller",
            method="SomeDocType.validate",
            session=session,
        )

    assert name
    row = await ctx.get_doc("ErrorLog", name)
    assert row["error_type"] == "ValueError"
    assert row["error_message"] == "boom happened"
    assert row["context"] == "Controller"
    assert row["title"].startswith("ValueError: boom happened")
    assert "ValueError" in (row["traceback"] or "")


@pytest.mark.asyncio
async def test_record_error_never_raises_on_bad_input(ctx):
    from grunt.monitoring.error_log import record_error

    # No exc, no message, no usable session context detail — must still not blow up.
    result = await record_error(session=ctx.db._session(), title="x" * 5000)
    assert result  # a row was still written, title clipped
    row = await ctx.get_doc("ErrorLog", result)
    assert len(row["title"]) <= 200


@pytest.mark.asyncio
async def test_grunt_log_error_is_exported():
    import grunt
    from grunt.monitoring.error_log import record_error

    assert grunt.log_error is record_error


# ── seen tracking works for this opt-in log ──────────────────────────────


@pytest.mark.asyncio
async def test_record_view_marks_error_log_seen(ctx):
    """ErrorLog has track_activity=False, but track_seen must still win."""
    from grunt.activity import record_view
    from grunt.monitoring.error_log import record_error

    session = ctx.db._session()
    name = await record_error(exc=RuntimeError("seen me"), session=session)
    await session.commit()

    doc = await ctx.get_doc("ErrorLog", name)
    await record_view(event="after_read", doctype="ErrorLog", doc=dict(doc), user=_plain_user())

    stored = await ctx.db.get_value("ErrorLog", name, "_seen")
    assert "plain@example.com" in (stored or [])


@pytest.mark.asyncio
async def test_seen_column_is_selectable_in_list(ctx):
    """The list view pulls ``_seen`` per row to mark unread rows — it must be
    a real, selectable column on the ErrorLog table."""
    from grunt.monitoring.error_log import record_error

    session = ctx.db._session()
    await record_error(exc=RuntimeError("list me"), session=session)
    await session.commit()

    result = await ctx.get_list("ErrorLog", fields=["name", "title", "_seen"])
    rows = result.to_dict()["data"]
    assert rows
    assert "_seen" in rows[0]


# ── retention fallback ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retention_falls_back_to_system_settings(ctx):
    from grunt.site.settings import clear_settings_cache, get_setting
    from grunt.tasks.retention import DEFAULT_LOG_RETENTION_DAYS

    assert DEFAULT_LOG_RETENTION_DAYS == 30

    await ctx.save_doc("SystemSettings", "SystemSettings", {"log_retention_days": 7})
    await ctx.db._session().commit()
    clear_settings_cache()

    assert await get_setting("log_retention_days", DEFAULT_LOG_RETENTION_DAYS) == 7
