"""Saved list filters (FRAPPE_GAP_PLAN #6).

RPC: grunt.api.v1.saved_filters.list_saved_filters / save_saved_filter /
delete_saved_filter

A ``SavedFilter`` is its owner's (the DocType's rule ``owner == user``: only
they change or delete it). ``shared_with`` lets others apply it too: ``Roles``
- the users holding one of ``roles``, ``Everyone`` - every user who can read
the DocType. Sharing with single users isn't there (yet).
"""

from typing import Any

from grunt.api.context import whitelist
from grunt.db.api import GruntDB
from grunt.errors import unprocessable
from grunt.i18n import _
from grunt.local import require_session_user
from grunt.permissions.guards import read_guard
from grunt.permissions.roles import get_roles
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

_DOCTYPE = "SavedFilter"
SHARING = ("Nobody", "Roles", "Everyone")
_FIELDS = ["name", "title", "filters", "shared_with", "roles", "owner"]


def _shape(row: dict[str, Any], user: str) -> dict[str, Any]:
    return {
        "name": row["name"],
        "title": row.get("title") or "",
        "filters": row.get("filters") or [],
        "shared_with": row.get("shared_with") or "Nobody",
        "roles": row.get("roles") or [],
        "mine": row.get("owner") == user,
    }


@whitelist()
async def list_saved_filters(doctype: str) -> list[dict[str, Any]]:
    """The filters the current user can apply on *doctype*: their own and the
    ones shared with everyone or with one of their roles. Needs read access to
    the DocType."""
    await read_guard(doctype)
    user = require_session_user()
    roles = set(await get_roles(user))
    rows = await _db.get_all(
        _DOCTYPE,
        filters={"ref_doctype": doctype},
        fields=_FIELDS,
        order_by="title",
        order="asc",
        limit=None,
    )
    visible = [
        row
        for row in rows
        if row.owner == user
        or row.shared_with == "Everyone"
        or (row.shared_with == "Roles" and roles.intersection(row.roles or []))
    ]
    return [_shape(row, user) for row in visible]


@whitelist()
async def save_saved_filter(
    doctype: str,
    title: str,
    filters: list[dict[str, Any]],
    shared_with: str = "Nobody",
    roles: list[str] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Create the current user's filter, or update theirs (*name*). A title
    they already use on this DocType is replaced."""
    await read_guard(doctype)
    title = (title or "").strip()
    if not title or not isinstance(filters, list) or not filters:
        raise unprocessable(_("A title and at least one filter are needed"))
    if shared_with not in SHARING:
        raise unprocessable(_("Invalid sharing"))
    roles = sorted({str(r) for r in roles or [] if r}) if shared_with == "Roles" else []
    if shared_with == "Roles" and not roles:
        raise unprocessable(_("Choose at least one role"))
    values = {
        "ref_doctype": doctype,
        "title": title,
        "filters": filters,
        "shared_with": shared_with,
        "roles": roles,
    }
    user = require_session_user()
    if name is None:
        # As the user: the rule owner == user finds only their own.
        same = await documents.get_list(
            _DOCTYPE,
            filters={"ref_doctype": doctype, "title": title},
            fields=["name"],
            limit=1,
            include_total=False,
        )
        name = same[0]["name"] if same else None
    if name:
        row = await documents.save_doc(_DOCTYPE, name, values)
    else:
        row = await documents.new_doc(_DOCTYPE, values)
    return _shape({**row, "owner": row.owner or user}, user)


@whitelist()
async def delete_saved_filter(name: str) -> None:
    """Delete the current user's filter (someone else's is refused)."""
    await documents.delete_doc(_DOCTYPE, name)
