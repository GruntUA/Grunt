"""Regression: ActivityLog used to have no `permissions` at all, so the
audit trail wasn't tamper-proof — any authenticated user could edit or
delete any entry via the generic docs CRUD (hiding their tracks, or someone
else's), or forge one outright (attributing an action to a different user,
or inventing an action that never happened) by setting an arbitrary `user`
field directly.

Fixed asymmetrically, not with the usual single-role lockdown: `read` stays
open to everyone (the activity feed is an intentionally org-wide view, see
[[project_grunt]] on the public:site broadcast), but `write`/`create`/
`delete` are System Manager only. That only works because the one
legitimate write path — grunt.activity.record_activity(), which used to run
under the acting user's own ambient context — was moved to run under
grunt.system_context() (SYSTEM_USER), so it keeps working regardless of the
acting user's role while the generic CRUD path is now actually closed.
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

_ACTIVITY_LOG_JSON = (
    Path(__file__).resolve().parents[2] / "grunt/activity/doctypes/ActivityLog/ActivityLog.json"
)


def _load() -> DocType:
    data = json.loads(_ACTIVITY_LOG_JSON.read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _plain_user(email: str = "plain@example.com") -> User:
    return make_user(email)


def _system_manager(email: str = "admin@example.com") -> User:
    return make_user(email, roles=["System Manager"])


def test_activity_log_has_permissions_defined():
    assert _load().permissions


@pytest.mark.asyncio
async def test_any_authenticated_user_can_read():
    dt = _load()
    assert await permission_checker.check(_plain_user(), dt, "read") is True


@pytest.mark.asyncio
async def test_plain_user_cannot_create_write_or_delete():
    """The forgery case: a plain user must not be able to write an
    ActivityLog row directly (which would let them set an arbitrary `user`
    field and attribute an action to someone else), nor edit/delete an
    existing entry to cover their tracks.
    """
    dt = _load()
    user = _plain_user()
    assert await permission_checker.check(user, dt, "create") is False
    assert await permission_checker.check(user, dt, "write") is False
    assert await permission_checker.check(user, dt, "delete") is False


@pytest.mark.asyncio
async def test_system_manager_has_full_access():
    dt = _load()
    admin = _system_manager()
    assert await permission_checker.check(admin, dt, "read") is True
    assert await permission_checker.check(admin, dt, "create") is True
    assert await permission_checker.check(admin, dt, "write") is True
    assert await permission_checker.check(admin, dt, "delete") is True


@pytest.mark.asyncio
async def test_record_activity_still_works_for_a_plain_user(ctx, db_session, engine):
    """End-to-end: record_activity() must keep working for a user with no
    roles at all — it now writes as SYSTEM_USER specifically so locking down
    ActivityLog.create doesn't break logging for everyone but admins.
    """
    from grunt.activity import record_activity
    from grunt.app import grunt

    async with grunt.context(db_session, engine, _plain_user("nobody@example.com")):
        await record_activity(
            "SomeDoctype",
            "some-id",
            "Create",
            user_email="nobody@example.com",
            broadcast=False,
        )
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _system_manager()):
        rows = await grunt.get_list(
            "ActivityLog",
            filters={"doctype": "SomeDoctype", "doc_id": "some-id"},
        )
    assert any(r["user"] == "nobody@example.com" and r["action"] == "Create" for r in rows)
