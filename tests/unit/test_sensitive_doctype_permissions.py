"""Regression: User/Role/UserRole/SystemSettings/EmailAccount/OutgoingWebhook
used to ship with no `permissions` at all — "no permissions defined = open
(dev mode)" meant ANY authenticated user could write to them via the generic
docs CRUD, including setting `is_superadmin: true` on their own User record
(instant self-service privilege escalation to full superadmin) or reading
another user's hashed_password/mfa_secret/refresh_token/reset_token.

DocType/DocField/DocTypeStatusIndicator had the exact same gap: without
explicit `permissions`, an unprivileged user could reach them via the
generic docs CRUD. DocType is the worst of these — a write to it would take
effect on the next hot-reload (`_apply_hot_reload_if_triggered` clears the
DocType cache), bypassing the `is_superadmin` gate that
`api/v1/meta.py:save_doctype` puts on the *intended* schema-editing path.
Permissions now live only inline on the DocType (edited in the Studio
builder, persisted in `grunt_meta_doctype.data`), so locking DocType down to
System Manager also closes the "grant yourself access" path.

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
from typing import TYPE_CHECKING

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.rbac import permission_checker
from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

_GRUNT_ROOT = Path(__file__).resolve().parents[2] / "grunt"

_DOCTYPE_JSON = {
    "User": _GRUNT_ROOT / "auth/doctypes/User/User.json",
    "Role": _GRUNT_ROOT / "auth/doctypes/Role/Role.json",
    "UserRole": _GRUNT_ROOT / "auth/doctypes/UserRole/UserRole.json",
    "SystemSettings": _GRUNT_ROOT / "site/doctypes/SystemSettings/SystemSettings.json",
    "EmailAccount": _GRUNT_ROOT / "email/doctypes/EmailAccount/EmailAccount.json",
    "OutgoingWebhook": _GRUNT_ROOT / "webhook/doctypes/OutgoingWebhook/OutgoingWebhook.json",
    "DocType": _GRUNT_ROOT / "metadata/doctypes/DocType/DocType.json",
    "DocField": _GRUNT_ROOT / "metadata/doctypes/DocField/DocField.json",
    "DocTypeStatusIndicator": (
        _GRUNT_ROOT / "metadata/doctypes/DocTypeStatusIndicator/DocTypeStatusIndicator.json"
    ),
    "ClientScript": _GRUNT_ROOT / "scripting/doctypes/ClientScript/ClientScript.json",
    "GruntInstalledApp": (
        _GRUNT_ROOT / "startup/doctypes/GruntInstalledApp/GruntInstalledApp.json"
    ),
    "WebsiteSettings": _GRUNT_ROOT / "site/doctypes/WebsiteSettings/WebsiteSettings.json",
    "DocVersion": _GRUNT_ROOT / "document/doctypes/DocVersion/DocVersion.json",
    "EmailQueue": _GRUNT_ROOT / "email/doctypes/EmailQueue/EmailQueue.json",
    "NotificationRule": (
        _GRUNT_ROOT / "notification/doctypes/NotificationRule/NotificationRule.json"
    ),
    "WebhookLog": _GRUNT_ROOT / "webhook/doctypes/WebhookLog/WebhookLog.json",
    "WebForm": _GRUNT_ROOT / "site/doctypes/WebForm/WebForm.json",
    "NamingSeries": _GRUNT_ROOT / "naming/doctypes/NamingSeries/NamingSeries.json",
}


def _load(doctype_name: str) -> DocType:
    data = json.loads(_DOCTYPE_JSON[doctype_name].read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _plain_user(email: str = "plain@example.com") -> User:
    return make_user(email)


def _system_manager(email: str = "admin@example.com") -> User:
    return make_user(email, roles=["System Manager"])


def _superadmin(email: str = "root@example.com") -> User:
    return make_user(email, is_superadmin=True)


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
def test_shipped_doctype_has_permissions_defined(doctype_name):
    """The bug was literally "permissions key missing" — guard against it
    quietly coming back (e.g. someone reverting the JSON edit by accident).
    """
    dt = _load(doctype_name)
    assert dt.permissions, f"{doctype_name} must declare permissions, not be open by default"


# User is the one exception: it also ships a `{"role": "All", "match":
# "name == user"}` row so a signed-in user can save *their own* profile via the
# generic form. Its self-service model is covered by the dedicated tests below.
_GENERIC_LOCKED = [n for n in _DOCTYPE_JSON if n != "User"]


@pytest.mark.parametrize("doctype_name", _GENERIC_LOCKED)
@pytest.mark.parametrize("action", ["read", "write", "create", "delete"])
@pytest.mark.asyncio
async def test_plain_user_has_no_access(doctype_name, action):
    dt = _load(doctype_name)
    allowed = await permission_checker.check(_plain_user(), dt, action)
    assert allowed is False


@pytest.mark.parametrize("action", ["create", "delete"])
@pytest.mark.asyncio
async def test_plain_user_cannot_create_or_delete_users(action):
    """The "All" row grants only read+write — never create/delete."""
    dt = _load("User")
    assert await permission_checker.check(_plain_user(), dt, action) is False


@pytest.mark.asyncio
async def test_plain_user_write_is_scoped_to_own_row():
    """`match: "name == user"` — a plain user may write their own User row but
    not anyone else's. (Which *fields* they may change is enforced by the User
    controller — see test_auth.test_self_edit_scope.)"""
    dt = _load("User")
    attacker = _plain_user("victim@example.com")
    assert (
        await permission_checker.check(
            attacker, dt, "write", {"name": "someone-else@example.com"}
        )
        is False
    )
    assert (
        await permission_checker.check(attacker, dt, "write", {"name": "victim@example.com"})
        is True
    )


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
    bypasses permission checks entirely, so restricting these DocTypes to
    System Manager can't lock out the bootstrap admin.
    """
    dt = _load(doctype_name)
    assert await permission_checker.check(_superadmin(), dt, "write") is True


@pytest.mark.asyncio
async def test_self_promotion_to_superadmin_denied():
    """A plain user can save their own profile, but `is_superadmin` /
    `is_active` / `signup_state` / roles / password / MFA are blocked by the
    User controller (`_enforce_self_edit_scope`). The permission layer here
    proves the second line of defence — no `create` on User — and the
    controller test (test_auth.test_self_edit_scope) proves the field guard.
    """
    dt = _load("User")
    attacker = _plain_user("victim@example.com")
    assert await permission_checker.check(attacker, dt, "create") is False


@pytest.mark.asyncio
async def test_self_grant_via_doctype_edit_denied_by_permission_check():
    """Permissions live inline on the DocType now, so the only way to grant
    yourself access is to write the DocType itself — a plain user has no
    `write` on DocType, so that path is refused before anything is saved.
    """
    dt = _load("DocType")
    attacker = _plain_user("attacker@example.com")
    allowed = await permission_checker.check(attacker, dt, "write")
    assert allowed is False
