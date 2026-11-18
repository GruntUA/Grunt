"""A user's list settings on the server (FRAPPE_GAP_PLAN #6).

RPC: grunt.api.v1.view_settings.get_view_settings / save_view_settings

Each row of ``UserViewSettings`` is one view of one DocType for its owner -
``columns``, ``list`` (view, sorting, grouping, page size), ``quick_filters``,
``report``; ``ref_doctype`` ``*`` holds what isn't tied to a DocType (``recent``
documents). The client keeps a localStorage copy as a cache and writes here
with a debounce (frontend/src/core/composables/useViewSetting.ts).

Rows are read and written as the user: the DocType's rule ``owner == user``
keeps everyone to their own.
"""

import json
from typing import Any

from grunt.api.context import whitelist
from grunt.api.v1.meta import get_doctype, save_doctype
from grunt.errors import not_found, unprocessable
from grunt.i18n import _
from grunt.metadata.compiler import STANDARD_COLUMNS
from grunt.metadata.registry import doctype_registry
lazy from grunt.document.api import documents

_DOCTYPE = "UserViewSettings"
# Not tied to a DocType (recent documents).
ANY_DOCTYPE = "*"
_MAX_BYTES = 64 * 1024


async def _check_doctype(doctype: str) -> None:
    if doctype != ANY_DOCTYPE and await doctype_registry.get_meta(doctype) is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})


async def _rows(doctype: str, view: str | None = None) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"ref_doctype": doctype}
    if view is not None:
        filters["view"] = view
    return list(
        await documents.get_list(
            _DOCTYPE,
            filters=filters,
            fields=["name", "view", "settings"],
            limit=100,
            include_total=False,
        )
    )


@whitelist()
async def get_view_settings(doctype: str) -> dict[str, Any]:
    """The current user's settings for *doctype*, ``{view: settings}``."""
    await _check_doctype(doctype)
    return {row["view"]: row.get("settings") for row in await _rows(doctype)}


@whitelist()
async def save_view_settings(doctype: str, view: str, settings: Any = None) -> None:
    """Store the current user's *settings* of *view* for *doctype*; ``None`` -
    back to the defaults (the row is removed)."""
    await _check_doctype(doctype)
    if not view or len(view) > 64:
        raise unprocessable(_("Invalid view"))
    if settings is not None and len(json.dumps(settings)) > _MAX_BYTES:
        raise unprocessable(_("The settings are too large"))
    rows = await _rows(doctype, view)
    if settings is None:
        for row in rows:
            await documents.delete_doc(_DOCTYPE, row["name"])
        return
    if rows:
        await documents.save_doc(_DOCTYPE, rows[0]["name"], {"settings": settings})
        for extra in rows[1:]:  # a race made two - keep one
            await documents.delete_doc(_DOCTYPE, extra["name"])
    else:
        await documents.new_doc(
            _DOCTYPE, {"ref_doctype": doctype, "view": view, "settings": settings}
        )


@whitelist(perm="grunt.manage_doctypes")
async def save_list_defaults(
    doctype: str,
    columns: list[str] | None = None,
    sort_field: str | None = None,
    sort_order: str | None = None,
    default_view: str | None = None,
    quick_filters: list[str] | None = None,
) -> dict[str, Any]:
    """ "Save as default for all": the current list settings become the DocType's
    own - ``list_columns``, ``sort_field`` / ``sort_order``, ``default_view`` and
    the fields' ``in_quick_filter``. Stored like any DocType change (exported to
    the app's file in developer mode). A user's own settings still win; their
    "Reset" goes back to these. Only the arguments given change."""
    data = await get_doctype(doctype, raw=True)
    known = {f["fieldname"] for f in data.get("fields") or []} | set(STANDARD_COLUMNS)
    if columns is not None:
        data["list_columns"] = [c for c in columns if c in known] or None
    if sort_field is not None:
        data["sort_field"] = sort_field if sort_field in known else None
    if sort_order in ("asc", "desc"):
        data["sort_order"] = sort_order
    if default_view is not None:
        data["default_view"] = default_view or None
    if quick_filters is not None:
        chosen = set(quick_filters)
        for field in data.get("fields") or []:
            field["in_quick_filter"] = field["fieldname"] in chosen
    return await save_doctype(data)
