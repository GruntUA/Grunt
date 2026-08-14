"""Regression: Comment used to have no `permissions` at all — the dedicated
endpoints (grunt/api/v1/docs/collaboration.py) correctly check read access
on the *referenced* document before listing/adding a comment, and ownership
before deleting one, but none of that mattered: the generic docs CRUD
(POST/GET/DELETE /api/v1/docs/Comment) bypassed all of it, letting any
authenticated user read every comment on every document (including ones
they can't otherwise access), post a comment attached to an arbitrary
reference_doctype/reference_id, or delete someone else's comment outright.

Same File-style two-row model: read/create stay broadly available (the
deeper "can you even see the referenced document" check still only lives in
collaboration.py — match can't express a cross-doctype condition, so this
doesn't fully close that read gap, only the same-doctype-CRUD one), write/
delete are scoped to the comment's own author.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.rbac import permission_checker

_COMMENT_JSON = Path(__file__).resolve().parents[2] / "grunt/document/doctypes/Comment/Comment.json"


def _load_comment_doctype() -> DocType:
    data = json.loads(_COMMENT_JSON.read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _user(email: str) -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=[], is_superadmin=False)


def test_comment_has_permissions_defined():
    dt = _load_comment_doctype()
    assert dt.permissions, "Comment must declare permissions, not be open by default"


@pytest.mark.asyncio
async def test_any_authenticated_user_can_read_and_create():
    dt = _load_comment_doctype()
    user = _user("someone-else@example.com")
    assert await permission_checker.check(user, dt, "read") is True
    assert await permission_checker.check(user, dt, "create") is True


@pytest.mark.asyncio
async def test_author_can_edit_and_delete_own_comment():
    dt = _load_comment_doctype()
    author = _user("author@example.com")
    own_comment = {"owner": "author@example.com", "content": "hello"}
    assert await permission_checker.check(author, dt, "write", own_comment) is True
    assert await permission_checker.check(author, dt, "delete", own_comment) is True


@pytest.mark.asyncio
async def test_other_user_cannot_edit_or_delete_someone_elses_comment():
    dt = _load_comment_doctype()
    attacker = _user("attacker@example.com")
    someone_elses_comment = {"owner": "author@example.com", "content": "hello"}
    assert await permission_checker.check(attacker, dt, "write", someone_elses_comment) is False
    assert await permission_checker.check(attacker, dt, "delete", someone_elses_comment) is False
