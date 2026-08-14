"""Regression: User/Role/UserRole/SystemSettings/EmailAccount/OutgoingWebhook
used to ship with no `permissions` at all — "no permissions defined = open
(dev mode)" meant ANY authenticated user could write to them via the generic
docs CRUD, including setting `is_superadmin: true` on their own User record
(instant self-service privilege escalation to full superadmin) or reading
another user's hashed_password/mfa_secret/refresh_token/reset_token.

These tests load the *actual* shipped DocType JSON (not a hand-built
fixture) and exercise `permission_checker` directly — deliberately not
through the full grunt.save_doc/get_doc facade, which for create/update/
delete forces a DocType reload via DocTypeRegistry._lazy_load(). That reload
goes through `site_manager`, which in this test process still points at the
real configured site (session/engine DI overrides in conftest.py only cover
FastAPI-injected routes) — so a full end-to-end facade test here would
silently read the live site's `grunt_meta_doctype` row instead of the
DocType this test just constructed. Testing permission_checker directly
against the real JSON avoids that trap while still proving the actual
shipped permissions are correct.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.rbac import permission_checker

_GRUNT_ROOT = Path(__file__).resolve().parents[2] / "grunt"

_DOCTYPE_JSON = {
    "User": _GRUNT_ROOT / "auth/doctypes/User/User.json",
    "Role": _GRUNT_ROOT / "auth/doctypes/Role/Role.json",
    "UserRole": _GRUNT_ROOT / "auth/doctypes/UserRole/UserRole.json",
    "SystemSettings": _GRUNT_ROOT / "site/doctypes/SystemSettings/SystemSettings.json",
    "EmailAccount": _GRUNT_ROOT / "email/doctypes/EmailAccount/EmailAccount.json",
    "OutgoingWebhook": _GRUNT_ROOT / "webhook/doctypes/OutgoingWebhook/OutgoingWebhook.json",
}


def _load(doctype_name: str) -> DocType:
    data = json.loads(_DOCTYPE_JSON[doctype_name].read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _plain_user(email: str = "plain@example.com") -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=[], is_superadmin=False)


def _system_manager(email: str = "admin@example.com") -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=["System Manager"], is_superadmin=False)


def _superadmin(email: str = "root@example.com") -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=[], is_superadmin=True)


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
def test_shipped_doctype_has_permissions_defined(doctype_name):
    """The bug was literally "permissions key missing" — guard against it
    quietly coming back (e.g. someone reverting the JSON edit by accident).
    """
    dt = _load(doctype_name)
    assert dt.permissions, f"{doctype_name} must declare permissions, not be open by default"


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.parametrize("action", ["read", "write", "create", "delete"])
@pytest.mark.asyncio
async def test_plain_user_has_no_access(doctype_name, action):
    dt = _load(doctype_name)
    allowed = await permission_checker.check(_plain_user(), dt, action)
    assert allowed is False


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.parametrize("action", ["read", "write", "create", "delete"])
@pytest.mark.asyncio
async def test_system_manager_has_full_access(doctype_name, action):
    dt = _load(doctype_name)
    allowed = await permission_checker.check(_system_manager(), dt, action)
    assert allowed is True


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.asyncio
async def test_superadmin_bypasses_regardless(doctype_name):
    """Superadmin bootstrap (first registered user) must still work — it
    bypasses DocTypePermission entirely, so restricting these DocTypes to
    System Manager can't lock out the bootstrap admin.
    """
    dt = _load(doctype_name)
    assert await permission_checker.check(_superadmin(), dt, "write") is True


@pytest.mark.asyncio
async def test_self_promotion_to_superadmin_denied_by_permission_check():
    """The exact exploit: a plain user has no `write` on User at all, so the
    generic write_guard()/save_doc("User", own_id, {"is_superadmin": True})
    path is refused before a single field is touched.
    """
    dt = _load("User")
    attacker = _plain_user("victim@example.com")
    allowed = await permission_checker.check(attacker, dt, "write")
    assert allowed is False
