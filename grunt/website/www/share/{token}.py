from __future__ import annotations

from typing import Any

# Framework bookkeeping fields never shown in the read-only share view.
_SKIP_FIELDS = {"id", "name", "owner", "created_at", "modified_at", "modified_by", "docstatus"}
_MULTILINE = {"LongText", "Text", "HTML"}


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    """Render a publicly shared document by token — server-side twin of the
    former ``DocumentShareView.vue``. Reuses the guest-accessible
    :func:`grunt.api.v1.share.get_shared_document` service directly.
    """
    from fastapi import HTTPException

    from grunt.api.messages import ApplicationError
    from grunt.api.v1.share import get_shared_document

    token = (context.get("path_params") or {}).get("token", "")
    context["title"] = "Перегляд документа"

    try:
        share = await get_shared_document(token)
    except ApplicationError as exc:
        context["error"] = exc.message
        return context
    except HTTPException as exc:
        context["error"] = str(exc.detail) or "Посилання недоступне"
        return context

    rows: list[dict[str, Any]] = []
    for field in share["fields"]:
        if field["fieldname"] in _SKIP_FIELDS:
            continue
        raw = share["doc"].get(field["fieldname"])
        if raw in (None, ""):
            value = "—"
        elif field["fieldtype"] == "Check":
            value = "Так" if str(raw) in ("1", "true", "True") else "Ні"
        else:
            value = raw
        rows.append(
            {
                "label": field["label"],
                "value": value,
                "multiline": field["fieldtype"] in _MULTILINE,
            }
        )

    expires_at = share.get("expires_at")
    if isinstance(expires_at, str) and len(expires_at) >= 16:
        expires_display = expires_at[:16].replace("T", " ")
    else:
        expires_display = expires_at or ""

    context["share"] = share
    context["rows"] = rows
    context["doc_title"] = share["doc"].get("name") or share["doc_id"]
    context["expires_display"] = expires_display
    return context
