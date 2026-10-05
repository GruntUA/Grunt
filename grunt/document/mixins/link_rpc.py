"""Link field search, exposed as a static method of ``Document``.

RPC: grunt.document.base.Document.link_search

Provides a dedicated search API optimised for Link field dropdowns:
  - Always searches `name` AND `title_field` (OR condition).
  - Also includes `search_fields` declared on the DocType.
  - Accepts arbitrary extra filters (from ``link_filters`` on DocField or JS).
  - Returns a compact payload: [{id, name, title, subtitle, fields}], where
    ``fields`` carries every configured ``search_field`` (label + value) so the
    dropdown can show the data the user searched by.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

import grunt
from grunt import _


async def _identifier_search(
    dt: Any,
    cols_needed: list[str],
    query: str,
    filters: dict[str, Any],
    per_page: int,
) -> list[dict[str, Any]]:
    """Search a DocType's identifier columns only (name + title + search
    fields) - the ``select``-permission path, which must not touch row-level
    filters, hidden-field masking or read hooks.

    Filters are honoured only on identifier columns; any other key is dropped
    so a select-only caller can't probe non-identifier values.
    """

    table = dt.table
    allowed = {c for c in cols_needed if c in table.c}

    stmt = select(*[table.c[c] for c in cols_needed if c in table.c])
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(*[table.c[c].ilike(like) for c in allowed]))
    for key, value in (filters or {}).items():
        base = key.split("__", 1)[0]
        if base in allowed:
            stmt = stmt.where(table.c[base] == value)
    stmt = stmt.limit(per_page)

    result = await grunt.get_session().execute(stmt)
    return [dict(r._mapping) for r in result]


def _doctype_field_labels(dt: Any) -> dict[str, str]:
    """Map DocType fieldnames -> display label (falling back to the fieldname)."""
    labels: dict[str, str] = {"name": "ID"}
    for field in list(getattr(dt, "fields", None) or []):
        if isinstance(field, dict):
            fieldname = field.get("fieldname")
            label = field.get("label")
        else:
            fieldname = getattr(field, "fieldname", None)
            label = getattr(field, "label", None)
        if isinstance(fieldname, str) and fieldname:
            labels[fieldname] = label or fieldname
    return labels


def _doctype_fieldnames(dt: Any) -> set[str]:
    """Collect DocType fieldnames from metadata objects or dicts."""
    return set(_doctype_field_labels(dt))


class DocumentLinkRPCMixin:
    """Link-field search, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def link_search(
        doctype: str,
        search: str = "",
        per_page: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search documents for a Link field dropdown."""
        from grunt.errors import not_found
        from grunt.local import require_user
        from grunt.permissions.access import RoleAccess
        from grunt.permissions.rbac import permission_checker

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        extra_filters: dict[str, Any] = filters or {}
        # A numeric search term ("12345") can arrive coerced to int - normalise.
        search = str(search or "").strip()

        # Gate, in order of precedence:
        #   1. unrestricted "read"      -> normal row-filtered, field-masked path
        #   2. explicit "select" grant  -> identifier-only search of every row
        #   3. row-scoped "read" only   -> normal path (returns the user's subset)
        #   4. neither                  -> 403 naming the DocType
        # (2) has to beat (3): a role granted "select" alongside a match-scoped
        # "read" wants an unfiltered picker, and check(user, dt, "read") can't
        # see that its "read" is row-scoped when there's no doc to match against.
        user = require_user()
        access = RoleAccess(dt.doc, user)
        if access.has_unrestricted_read:
            has_read = True
        elif access.has_explicit_select:
            has_read = False
        elif await permission_checker.check(user, dt.doc, "read"):
            has_read = True
        else:
            await permission_checker.require(user, dt.doc, "select")  # raises 403
            has_read = False

        # Virtual DocType - delegate to its controller's get_list
        if dt.is_virtual:
            from grunt.document.virtual import _get_virtual_controller

            ctrl = _get_virtual_controller(doctype, grunt.get_user())
            result = await ctrl.get_list(search=search, page=1, per_page=per_page) if ctrl else {}
            title_field = dt.title_field or "name"
            items = []
            for row in result.get("data", []):
                name_val = str(row.get("name") or "")
                title_val = str(row.get(title_field) or name_val)
                items.append(
                    {
                        "id": name_val,
                        "name": name_val,
                        "title": title_val,
                        "subtitle": None,
                        "fields": [],
                    }
                )
            return items

        title_field: str = (dt.title_field or "name") if hasattr(dt, "title_field") else "name"
        field_labels = _doctype_field_labels(dt)
        doctype_fields = set(field_labels)

        # Columns to fetch
        cols_needed: list[str] = ["name"]
        if title_field and title_field != "name" and title_field in doctype_fields:
            cols_needed.append(title_field)
        # Include search_fields for display as subtitle
        search_fields: list[str] = list(getattr(dt, "search_fields", None) or [])
        for sf in search_fields:
            if sf in doctype_fields and sf not in cols_needed:
                cols_needed.append(sf)

        query = search
        if has_read:
            rows = await grunt.get_list(
                doctype,
                filters=extra_filters if extra_filters else None,
                fields=cols_needed,
                limit=per_page,
                search=query or None,
            )
        else:
            rows = await _identifier_search(dt, cols_needed, query, extra_filters, per_page)

        # Shape response
        items = []
        for row in rows:
            name_val = str(row.get("name") or "")
            title_val = str(row.get(title_field) or name_val) if title_field else name_val

            # Resolve a display value for every configured search_field, in the
            # order they were declared. Link fields carry a resolved label
            # (``sf__label``, injected by _resolve_link_labels); prefer it.
            search_values: list[dict[str, str]] = []
            for sf in search_fields:
                if sf not in doctype_fields:
                    continue
                candidate = row.get(f"{sf}__label")
                if candidate is None:
                    candidate = row.get(sf)
                if candidate is None:
                    continue
                candidate_str = str(candidate).strip()
                if not candidate_str:
                    continue
                search_values.append(
                    {
                        "fieldname": sf,
                        "label": field_labels.get(sf, sf),
                        "value": candidate_str,
                    }
                )

            # If title_field is effectively "name", promote the first
            # search_field value to a more human-readable title.
            if title_val == name_val and search_values:
                title_val = search_values[0]["value"]

            # Everything not already shown as the title is handed to the
            # dropdown so it can render the field the user searched by. The
            # document id (``name``) is never surfaced here.
            fields_out = [sv for sv in search_values if sv["value"] != title_val]
            subtitle_val: str | None = fields_out[0]["value"] if fields_out else None

            items.append(
                {
                    "id": name_val,
                    "name": name_val,
                    "title": title_val,
                    "subtitle": subtitle_val,
                    "fields": fields_out,
                }
            )

        return items
