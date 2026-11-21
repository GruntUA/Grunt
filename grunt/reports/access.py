"""Who may run a ``Report`` - one rule for the engine, menus and the desk.

A report runs for a user when it is not ``disabled`` and:

* ``roles`` set - the user holds one of them (System Manager always does);
* on a DocType (``ref_doctype``) - the user has ``report`` on it as well;
* neither - only a System Manager: a Query/Script report reads the database
  around row-level permissions, so it is not everyone's by default.
"""

from collections.abc import Iterable
from typing import Any

from grunt.errors import forbidden
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.permissions.query import allowed_doctypes
from grunt.permissions.roles import get_roles

SYSTEM_MANAGER = "System Manager"

#: What :func:`runnable` needs of a report row.
ACCESS_FIELDS = ["report_name", "ref_doctype", "roles", "disabled"]


def _roles_allow(report: dict[str, Any], held: set[str]) -> bool:
    if SYSTEM_MANAGER in held:
        return True
    wanted = set(report.get("roles") or [])
    if wanted:
        return bool(wanted & held)
    return bool(report.get("ref_doctype"))  # no DocType, no roles - System Manager only


async def runnable(reports: Iterable[dict[str, Any]], user: str) -> list[dict[str, Any]]:
    """Those of *reports* (rows with :data:`ACCESS_FIELDS`) *user* may run."""
    reports = [r for r in reports if not r.get("disabled")]
    if not reports:
        return []
    held = set(await get_roles(user))
    reports = [r for r in reports if _roles_allow(r, held)]
    refs = sorted({r["ref_doctype"] for r in reports if r.get("ref_doctype")})
    metas = [m for n in refs if (m := await doctype_registry.get_meta(n))]
    allowed = await allowed_doctypes(metas, "report", user=user) if metas else set()
    return [r for r in reports if not r.get("ref_doctype") or r["ref_doctype"] in allowed]


async def require_runnable(report: dict[str, Any], user: str) -> None:
    """Raise unless *user* may run *report* (a row with :data:`ACCESS_FIELDS`)."""
    if report.get("disabled"):
        raise forbidden(_("Report “%(name)s” is disabled") % {"name": report.get("report_name")})
    if not await runnable([report], user):
        raise forbidden(
            _("You are not allowed to run report “%(name)s”") % {"name": report.get("report_name")}
        )
