"""Regression: PushSubscription and Notification used to ship with no
`permissions` at all -- any authenticated user could read/write/delete any
row via the generic docs CRUD, not just their own.

PushSubscription rows carry the Web Push endpoint URL + p256dh/auth keys
for a specific user; a plain user reading everyone else's rows can hijack
another user's push channel (read their keys, or overwrite their `endpoint`
to redirect future pushes to an attacker-controlled URL). Notification rows
carry `subject`/`message` text addressed to a specific user; the intended
access path (grunt/api/v1/notifications.py:list_notifications) already
filters by `user == current user`, but that filter is app-code discipline,
not enforcement -- the generic docs CRUD ignored it entirely.

Both are fixed the same way as File (see test_file_permissions.py): broad
`create` isn't needed (rows are created via system_context, which bypasses
DocTypePermission entirely), and read/write/delete are scoped with
`match: "user == user"`.

Same rationale as test_file_permissions.py for testing permission_checker
directly rather than through the full facade: both are core doctypes
already seeded on this process's configured site, so driving this through
grunt.new_doc/save_doc would trip DocTypeRegistry._lazy_load()'s live-site
fetch mid-test.
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

_GRUNT_ROOT = Path(__file__).resolve().parents[2] / "grunt"

_DOCTYPE_JSON = {
    "PushSubscription": _GRUNT_ROOT / "webpush/doctypes/PushSubscription/PushSubscription.json",
    "Notification": _GRUNT_ROOT / "notification/doctypes/Notification/Notification.json",
}

_USER_SESSION_JSON = _GRUNT_ROOT / "auth/doctypes/UserSession/UserSession.json"


def _load(doctype_name: str) -> DocType:
    data = json.loads(_DOCTYPE_JSON[doctype_name].read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _user(email: str) -> User:
    return make_user(email)


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
def test_shipped_doctype_has_permissions_defined(doctype_name):
    dt = _load(doctype_name)
    assert dt.permissions, f"{doctype_name} must declare permissions, not be open by default"


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.asyncio
async def test_owner_can_access_own_row(doctype_name):
    dt = _load(doctype_name)
    owner = _user("owner@example.com")
    own_row = {"user": "owner@example.com"}
    assert await permission_checker.check(owner, dt, "read", own_row) is True
    assert await permission_checker.check(owner, dt, "write", own_row) is True
    assert await permission_checker.check(owner, dt, "delete", own_row) is True


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.asyncio
async def test_other_user_cannot_access_row(doctype_name):
    dt = _load(doctype_name)
    attacker = _user("attacker@example.com")
    someone_elses_row = {"user": "victim@example.com"}
    assert await permission_checker.check(attacker, dt, "read", someone_elses_row) is False
    assert await permission_checker.check(attacker, dt, "write", someone_elses_row) is False
    assert await permission_checker.check(attacker, dt, "delete", someone_elses_row) is False


def _load_user_session() -> DocType:
    data = json.loads(_USER_SESSION_JSON.read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def test_user_session_has_permissions_defined():
    assert _load_user_session().permissions


@pytest.mark.asyncio
async def test_user_session_owner_can_read_and_deactivate_own_session():
    dt = _load_user_session()
    owner = _user("owner@example.com")
    own_row = {"user": "owner@example.com"}
    assert await permission_checker.check(owner, dt, "read", own_row) is True
    assert await permission_checker.check(owner, dt, "write", own_row) is True


@pytest.mark.asyncio
async def test_user_session_other_user_cannot_read_or_touch_it():
    dt = _load_user_session()
    attacker = _user("attacker@example.com")
    someone_elses_row = {"user": "victim@example.com"}
    assert await permission_checker.check(attacker, dt, "read", someone_elses_row) is False
    assert await permission_checker.check(attacker, dt, "write", someone_elses_row) is False
