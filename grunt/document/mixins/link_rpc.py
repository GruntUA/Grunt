"""Link field search, exposed as a static method of ``Document``.

RPC: grunt.document.base.Document.link_search

Provides a dedicated search API optimised for Link field dropdowns:
  - Always searches `name` AND `title_field` (OR condition).
  - Also includes `search_fields` declared on the DocType.
  - Accepts arbitrary extra filters (from ``link_filters`` on DocField or JS).
  - Returns a compact payload: [{id, name, title, subtitle}].
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt.metadata.registry import doctype_registry


def _doctype_fieldnames(dt: Any) -> set[str]:
    """Collect DocType fieldnames from metadata objects or dicts."""
    names: set[str] = {"name"}
    for field in list(getattr(dt, "fields", None) or []):
        if isinstance(field, dict):
            fieldname = field.get("fieldname")
        else:
            fieldname = getattr(field, "fieldname", None)
        if isinstance(fieldname, str) and fieldname:
            names.add(fieldname)
    return names


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
        from grunt.app import grunt as grunt_app

        dt = await doctype_registry.get(doctype)
        extra_filters: dict[str, Any] = filters or {}

        # Virtual DocType — delegate to its controller's get_list
        if dt.is_virtual:
            from grunt.document.virtual import _get_virtual_controller

            ctrl = _get_virtual_controller(doctype, grunt.get_user())
            result = await ctrl.get_list(search=search, page=1, per_page=per_page)
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
                        "subtitle": name_val if title_val != name_val else None,
                    }
                )
            return items

        title_field: str = (dt.title_field or "name") if hasattr(dt, "title_field") else "name"
        doctype_fields = _doctype_fieldnames(dt)

        # ── Columns to fetch ─────────────────────────────────────────────────
        cols_needed: list[str] = ["name"]
        if title_field and title_field != "name" and title_field in doctype_fields:
            cols_needed.append(title_field)
        # Include search_fields for display as subtitle
        search_fields: list[str] = list(getattr(dt, "search_fields", None) or [])
        for sf in search_fields:
            if sf in doctype_fields and sf not in cols_needed:
                cols_needed.append(sf)

        query = search.strip()
        rows = await grunt_app.get_list(
            doctype,
            filters=extra_filters if extra_filters else None,
            fields=cols_needed,
            limit=per_page,
            search=query or None,
        )

        # ── Shape response ────────────────────────────────────────────────
        items = []
        for row in rows:
            name_val = str(row.get("name") or "")
            title_val = str(row.get(title_field) or name_val) if title_field else name_val

            # If title_field is effectively "name", use the first search_field value
            # as a more human-readable title when available.
            if title_val == name_val:
                for sf in search_fields:
                    # Prefer resolved label for Link fields
                    # (injected as sf__label by _resolve_link_labels)
                    candidate = row.get(f"{sf}__label") or row.get(sf)
                    if candidate is not None:
                        candidate_str = str(candidate)
                        if candidate_str:
                            title_val = candidate_str
                            break

            subtitle_val: str | None = None
            for sf in search_fields:
                # Prefer resolved label for Link fields (injected as sf__label
                # by _resolve_link_labels)
                candidate = row.get(f"{sf}__label") or row.get(sf)
                if candidate is None:
                    continue
                candidate_str = str(candidate)
                if candidate_str and candidate_str != title_val:
                    subtitle_val = candidate_str
                    break
            # Fall back to name as subtitle when title differs (name is human-readable, not a UUID)
            if subtitle_val is None and title_val != name_val:
                subtitle_val = name_val

            items.append(
                {
                    "id": name_val,
                    "name": name_val,
                    "title": title_val,
                    "subtitle": subtitle_val,
                }
            )

        return items
