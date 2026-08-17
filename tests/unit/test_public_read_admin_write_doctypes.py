"""Regression: Page, AppMenu, Dashboard, NumberCard, DashboardChart and
WebPage used to have no `permissions` at all. All six had a dedicated
whitelisted method gating create/delete to `is_superadmin` (register_page/
delete_page, save_workspace/delete_workspace, ...) or no dedicated writer at
all (Dashboard/NumberCard/DashboardChart/WebPage are managed purely through
the generic docs CRUD) — either way, that admin-only intent was never
actually enforced, since the generic docs CRUD bypassed it completely.

Page and Dashboard are the sharpest case: their widgets compute aggregate
data via `grunt.db.aggregate()`, which bypasses `doctype.permissions`
entirely (a separate, pre-existing, wider gap — see project memory). Without
this fix, any authenticated user could create a *published* Page/Dashboard
with a widget aggregating a locked-down DocType (e.g. User) and read
cross-permission-boundary aggregate data just by viewing their own page.

WebPage additionally renders `content` (RichText) directly on the public
website — unrestricted write there is a stored-XSS-to-every-visitor vector,
not just a defacement one.

Fixed the same way for all six: `read` stays open (these are meant to be
broadly/publicly visible once published), `write`/`create`/`delete` are
System Manager only.
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
    "Page": _GRUNT_ROOT / "site/doctypes/Page/Page.json",
    "AppMenu": _GRUNT_ROOT / "site/doctypes/AppMenu/AppMenu.json",
    "WebPage": _GRUNT_ROOT / "site/doctypes/WebPage/WebPage.json",
    "Dashboard": _GRUNT_ROOT / "reports/doctypes/Dashboard/Dashboard.json",
    "NumberCard": _GRUNT_ROOT / "reports/doctypes/NumberCard/NumberCard.json",
    "DashboardChart": _GRUNT_ROOT / "reports/doctypes/DashboardChart/DashboardChart.json",
}


def _load(doctype_name: str) -> DocType:
    data = json.loads(_DOCTYPE_JSON[doctype_name].read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _plain_user() -> User:
    return make_user("plain@example.com")


def _system_manager() -> User:
    return make_user("admin@example.com", roles=["System Manager"])


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
def test_shipped_doctype_has_permissions_defined(doctype_name):
    dt = _load(doctype_name)
    assert dt.permissions, f"{doctype_name} must declare permissions, not be open by default"


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.asyncio
async def test_any_authenticated_user_can_read(doctype_name):
    dt = _load(doctype_name)
    assert await permission_checker.check(_plain_user(), dt, "read") is True


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.parametrize("action", ["write", "create", "delete"])
@pytest.mark.asyncio
async def test_plain_user_cannot_write_create_or_delete(doctype_name, action):
    """The exact exploit: a plain user creating a published Page/Dashboard
    with a widget targeting a locked-down DocType to read its aggregate
    data via the grunt.db.aggregate() permission-bypass.
    """
    dt = _load(doctype_name)
    assert await permission_checker.check(_plain_user(), dt, action) is False


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.parametrize("action", ["write", "create", "delete"])
@pytest.mark.asyncio
async def test_system_manager_can_write_create_and_delete(doctype_name, action):
    dt = _load(doctype_name)
    assert await permission_checker.check(_system_manager(), dt, action) is True
