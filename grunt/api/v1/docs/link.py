"""Link field search endpoint.

Provides a dedicated search API optimised for Link field dropdowns:
  - Always searches `name` AND `title_field` (OR condition).
  - Also includes `search_fields` declared on the DocType.
  - Accepts arbitrary extra filters (from ``link_filters`` on DocField or JS).
  - Returns a compact payload: [{id, name, title, subtitle}].
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, Query

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt as grunt_app
from grunt.auth.dependencies import current_user
from grunt.auth.doctypes.User.User import User
from grunt.metadata.registry import doctype_registry

router = GruntRouter()


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


@router.get("/{doctype}/link_search")
async def link_search(
    doctype: str,
    q: str = Query(default="", description="Search string"),
    filters: str = Query(default="{}", description="JSON-encoded extra filters"),
    page_length: int = Query(default=10, ge=1, le=100),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Search documents for a Link field dropdown."""
    dt = await doctype_registry.get(doctype)

    # Virtual DocType — delegate to its controller's get_list
    if dt.is_virtual:
        from grunt.document.virtual import _get_virtual_controller  # noqa: PLC0415

        ctrl = _get_virtual_controller(doctype, user)
        result = await ctrl.get_list(search=q, page=1, per_page=page_length)
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
        return ok(items)

    title_field: str = (dt.title_field or "name") if hasattr(dt, "title_field") else "name"
    doctype_fields = _doctype_fieldnames(dt)

    # ── Columns to fetch ─────────────────────────────────────────────────────
    cols_needed: list[str] = ["name"]
    if title_field and title_field != "name" and title_field in doctype_fields:
        cols_needed.append(title_field)
    # Include search_fields for display as subtitle
    search_fields: list[str] = list(getattr(dt, "search_fields", None) or [])
    for sf in search_fields:
        if sf in doctype_fields and sf not in cols_needed:
            cols_needed.append(sf)

    # ── Parse extra filters ───────────────────────────────────────────────────
    try:
        parsed = json.loads(filters) if filters and filters != "{}" else {}
        raw_filters: dict[str, Any] = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError, ValueError:
        raw_filters = {}

    # Normalise Frappe-style filters: {"field": ["in", [...]]} → {"field__in": [...]}
    extra_filters: dict[str, Any] = {}
    for k, v in raw_filters.items():
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
            op, operand = v[0].lower(), v[1]
            extra_filters[f"{k}__{op}"] = operand
        else:
            extra_filters[k] = v

    query = q.strip()
    rows = await grunt_app.get_list(
        doctype,
        filters=extra_filters if extra_filters else None,
        fields=cols_needed,
        limit=page_length,
        search=query or None,
    )

    # ── Shape response ────────────────────────────────────────────────────────
    items = []
    for row in rows:
        name_val = str(row.get("name") or "")
        title_val = str(row.get(title_field) or name_val) if title_field else name_val

        # If title_field is effectively "name", use the first search_field value
        # as a more human-readable title when available.
        if title_val == name_val:
            for sf in search_fields:
                # Prefer resolved label for Link fields (injected as sf__label by _resolve_link_labels)
                candidate = row.get(f"{sf}__label") or row.get(sf)
                if candidate is not None:
                    candidate_str = str(candidate)
                    if candidate_str:
                        title_val = candidate_str
                        break

        subtitle_val: str | None = None
        for sf in search_fields:
            # Prefer resolved label for Link fields (injected as sf__label by _resolve_link_labels)
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

    return ok(items)
