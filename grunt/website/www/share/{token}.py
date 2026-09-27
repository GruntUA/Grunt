from __future__ import annotations

from typing import Any

from grunt.website.doc_layout import FlatField, build_tabs, fmt_dt


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    """Render a publicly shared document by token — server-side twin of the
    former ``DocumentShareView.vue``. Reuses the guest-accessible
    :func:`grunt.api.v1.share.get_shared_document` service directly, then lays
    the fields out with the target DocType's own Tab/Section/Column structure.
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

    doc = share["doc"]
    exposed = {f["fieldname"] for f in share["fields"]}

    all_fields: list[Any] = []
    title_field = "name"
    from grunt.app import grunt as grunt_app

    dt = await grunt_app.get_meta(share["doctype"])
    if dt is None:  # metadata unavailable — fall back to a flat single section
        all_fields = [
            FlatField(f["fieldname"], f["label"], f["fieldtype"]) for f in share["fields"]
        ]
    else:
        all_fields = list(dt.fields)
        title_field = getattr(dt, "title_field", None) or "name"

    tabs = build_tabs(all_fields, doc, exposed)

    meta: list[dict[str, str]] = [
        {"label": "Тип документа", "value": share["doctype_label"]},
        {"label": "Ідентифікатор", "value": share["doc_id"]},
    ]
    if doc.get("created_at"):
        meta.append({"label": "Створено", "value": fmt_dt(doc["created_at"])})
    if doc.get("modified_at"):
        meta.append({"label": "Оновлено", "value": fmt_dt(doc["modified_at"])})
    if share.get("expires_at"):
        meta.append({"label": "Дійсно до", "value": fmt_dt(share["expires_at"])})

    context["share"] = share
    context["tabs"] = tabs
    context["meta"] = meta
    context["doc_title"] = (
        (doc.get(title_field) if title_field != "name" else None)
        or doc.get("name")
        or share["doc_id"]
    )
    return context
