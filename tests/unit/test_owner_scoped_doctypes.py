"""Regression: Bookmark, DocTag and ToDo used to have no `permissions` at
all — personal/per-user data (which documents someone bookmarked, tagged,
or was assigned a task for) readable and writable by any authenticated
user, not just its own owner/assignee.

Three slightly different shapes, each mirroring an existing precedent
already covered elsewhere:
- Bookmark: single row, all actions scoped to `owner == user` (same shape
  as DocumentShare).
- DocTag: read/create broad, write/delete scoped to `owner == user` (same
  two-row shape as Comment/File — tags are meant to be visible to anyone
  who can see the tagged document, tagging is cheap/low-risk to leave open;
  only *removing/editing* someone else's tag needed closing).
- ToDo: read/write scoped to `assigned_to == user` for regular users (the
  assignee needs to update their own task's status), plus a second row
  giving System Manager unrestricted access (assignment-rule-driven
  creation runs under grunt.system_context(), so it isn't gated by either
  row — see grunt/assignment/service.py:_create_todo).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.rbac import permission_checker

_GRUNT_ROOT = Path(__file__).resolve().parents[2] / "grunt"

_BOOKMARK_JSON = _GRUNT_ROOT / "site/doctypes/Bookmark/Bookmark.json"
_DOCTAG_JSON = _GRUNT_ROOT / "document/doctypes/DocTag/DocTag.json"
_TODO_JSON = _GRUNT_ROOT / "tasks/doctypes/ToDo/ToDo.json"


def _load(path: Path) -> DocType:
    return DocType.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _user(email: str, roles: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=roles or [], is_superadmin=False)


# ── Bookmark ──────────────────────────────────────────────────────────────


def test_bookmark_has_permissions_defined():
    assert _load(_BOOKMARK_JSON).permissions


@pytest.mark.asyncio
async def test_bookmark_owner_can_manage_own_row():
    dt = _load(_BOOKMARK_JSON)
    owner = _user("owner@example.com")
    own_row = {"owner": "owner@example.com"}
    assert await permission_checker.check(owner, dt, "read", own_row) is True
    assert await permission_checker.check(owner, dt, "write", own_row) is True
    assert await permission_checker.check(owner, dt, "delete", own_row) is True


@pytest.mark.asyncio
async def test_bookmark_other_user_cannot_see_or_touch_it():
    dt = _load(_BOOKMARK_JSON)
    attacker = _user("attacker@example.com")
    someone_elses_row = {"owner": "owner@example.com"}
    assert await permission_checker.check(attacker, dt, "read", someone_elses_row) is False
    assert await permission_checker.check(attacker, dt, "write", someone_elses_row) is False
    assert await permission_checker.check(attacker, dt, "delete", someone_elses_row) is False


# ── DocTag ────────────────────────────────────────────────────────────────


def test_doctag_has_permissions_defined():
    assert _load(_DOCTAG_JSON).permissions


@pytest.mark.asyncio
async def test_doctag_any_authenticated_user_can_read_and_create():
    dt = _load(_DOCTAG_JSON)
    user = _user("someone-else@example.com")
    assert await permission_checker.check(user, dt, "read") is True
    assert await permission_checker.check(user, dt, "create") is True


@pytest.mark.asyncio
async def test_doctag_owner_can_edit_and_delete_own_tag():
    dt = _load(_DOCTAG_JSON)
    owner = _user("owner@example.com")
    own_tag = {"owner": "owner@example.com"}
    assert await permission_checker.check(owner, dt, "write", own_tag) is True
    assert await permission_checker.check(owner, dt, "delete", own_tag) is True


@pytest.mark.asyncio
async def test_doctag_other_user_cannot_edit_or_delete_someone_elses_tag():
    dt = _load(_DOCTAG_JSON)
    attacker = _user("attacker@example.com")
    someone_elses_tag = {"owner": "owner@example.com"}
    assert await permission_checker.check(attacker, dt, "write", someone_elses_tag) is False
    assert await permission_checker.check(attacker, dt, "delete", someone_elses_tag) is False


# ── ToDo ──────────────────────────────────────────────────────────────────


def test_todo_has_permissions_defined():
    assert _load(_TODO_JSON).permissions


@pytest.mark.asyncio
async def test_todo_assignee_can_read_and_update_own_task():
    dt = _load(_TODO_JSON)
    assignee = _user("assignee@example.com")
    own_task = {"assigned_to": "assignee@example.com"}
    assert await permission_checker.check(assignee, dt, "read", own_task) is True
    assert await permission_checker.check(assignee, dt, "write", own_task) is True


@pytest.mark.asyncio
async def test_todo_other_user_cannot_read_or_touch_someone_elses_task():
    dt = _load(_TODO_JSON)
    attacker = _user("attacker@example.com")
    someone_elses_task = {"assigned_to": "victim@example.com"}
    assert await permission_checker.check(attacker, dt, "read", someone_elses_task) is False
    assert await permission_checker.check(attacker, dt, "write", someone_elses_task) is False


@pytest.mark.asyncio
async def test_todo_system_manager_has_full_access_regardless_of_assignee():
    dt = _load(_TODO_JSON)
    admin = _user("admin@example.com", roles=["System Manager"])
    someone_elses_task = {"assigned_to": "victim@example.com"}
    assert await permission_checker.check(admin, dt, "read", someone_elses_task) is True
    assert await permission_checker.check(admin, dt, "write", someone_elses_task) is True
    assert await permission_checker.check(admin, dt, "create") is True
    assert await permission_checker.check(admin, dt, "delete", someone_elses_task) is True
