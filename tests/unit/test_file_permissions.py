"""Regression: File used to have no `permissions` at all — any authenticated
user could write/delete *any* File document (not just their own), including
flipping `is_public` on someone else's private attachment to make it
downloadable via the guest-accessible get_content() endpoint, or destroying
someone else's file outright via remove().

Loads the actual shipped File.json (not a hand-built fixture) and exercises
permission_checker directly — see test_sensitive_doctype_permissions.py's
module docstring for why: File is a core DocType already seeded on this
process's configured site, so driving this through the full grunt.save_doc/
delete_doc facade would trip DocTypeRegistry._lazy_load()'s live-site fetch
mid-test and silently swap in that site's on-disk DocType definition instead
of the one this test just edited. The end-to-end mechanism (write_guard +
match-on-existing-doc) is proven separately, against a disposable test-only
DocType, by test_permission_row_level.py's write/delete tests.
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

_FILE_JSON = Path(__file__).resolve().parents[2] / "grunt/storage/doctypes/File/File.json"


def _load_file_doctype() -> DocType:
    data = json.loads(_FILE_JSON.read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _user(email: str) -> User:
    return make_user(email)


def test_file_has_permissions_defined():
    dt = _load_file_doctype()
    assert dt.permissions, "File must declare permissions, not be open by default"


@pytest.mark.asyncio
async def test_any_authenticated_user_can_read_and_create():
    """Broad read/create must be preserved — upload()/get_list() (any
    authenticated user, no role check) rely on it, as does viewing files
    attached to a document someone else uploaded.
    """
    dt = _load_file_doctype()
    user = _user("someone-else@example.com")
    assert await permission_checker.check(user, dt, "read") is True
    assert await permission_checker.check(user, dt, "create") is True


@pytest.mark.asyncio
async def test_owner_can_write_and_delete_own_file():
    dt = _load_file_doctype()
    owner = _user("owner@example.com")
    own_file = {"owner": "owner@example.com", "file_name": "mine.pdf"}
    assert await permission_checker.check(owner, dt, "write", own_file) is True
    assert await permission_checker.check(owner, dt, "delete", own_file) is True


@pytest.mark.asyncio
async def test_non_owner_cannot_write_or_delete_others_file():
    dt = _load_file_doctype()
    attacker = _user("attacker@example.com")
    someone_elses_file = {"owner": "owner@example.com", "file_name": "secret.pdf"}
    assert await permission_checker.check(attacker, dt, "write", someone_elses_file) is False
    assert await permission_checker.check(attacker, dt, "delete", someone_elses_file) is False
