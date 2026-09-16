from __future__ import annotations

from typing import Any

# Framework bookkeeping fields never shown in the read-only share view.
_SKIP_FIELDS = {"id", "name", "owner", "created_at", "modified_at", "modified_by", "docstatus"}
_MULTILINE = {"LongText", "Text", "HTML", "Code", "Markdown"}
_IMAGE_TYPES = {"Image", "Attach Image"}
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp")
# Non-data fieldtypes that carry no value to show in a read-only layout.
_NON_DATA = {"Tab", "Section", "Column", "HTML", "Button", "Fold"}


def _is_image_value(fieldtype: str, raw: Any) -> bool:
    """An ``Image`` field always renders as a picture; a plain ``Attach`` only
    when its URL clearly points at one."""
    if not raw:
        return False
    if fieldtype in _IMAGE_TYPES:
        return True
    if fieldtype == "Attach":
        return str(raw).split("?", 1)[0].lower().endswith(_IMAGE_EXTS)
    return False


def _fmt_dt(raw: Any) -> str:
    """`2026-09-08T14:20:12+00:00` → `2026-09-08 14:20`."""
    return raw[:16].replace("T", " ") if isinstance(raw, str) and len(raw) >= 16 else (raw or "")


def _row(
    label: str, fieldtype: str, raw: Any, description: str | None, display: Any = None
) -> dict[str, Any]:
    if _is_image_value(fieldtype, raw):
        return {"label": label, "image_url": raw, "description": description}
    if raw in (None, ""):
        value = "—"
    elif fieldtype == "Check":
        value = "Так" if str(raw) in ("1", "true", "True") else "Ні"
    elif fieldtype == "Link" and display not in (None, ""):
        value = display
    else:
        value = raw
    return {
        "label": label,
        "value": value,
        "multiline": fieldtype in _MULTILINE,
        "description": description,
    }


def _build_tabs(all_fields: list[Any], exposed: set[str], doc: dict[str, Any]) -> list[dict]:
    """Walk the DocType's ordered field list and rebuild its Tab → Section →
    Column layout, keeping only the data fields the share actually exposes.
    """
    tabs: list[dict] = []
    tab: dict = {"label": "", "sections": []}
    section: dict = {"label": "", "cols": [[]]}
    tab["sections"].append(section)
    tabs.append(tab)

    for f in all_fields:
        ftype = f.fieldtype
        if ftype == "Tab":
            tab = {"label": f.label or "", "sections": []}
            section = {"label": "", "cols": [[]]}
            tab["sections"].append(section)
            tabs.append(tab)
        elif ftype == "Section":
            section = {"label": f.label or "", "cols": [[]]}
            tab["sections"].append(section)
        elif ftype == "Column":
            section["cols"].append([])
        elif ftype in _NON_DATA:
            continue
        else:
            if f.hidden or f.fieldname in _SKIP_FIELDS:
                continue
            if exposed and f.fieldname not in exposed:
                continue
            section["cols"][-1].append(
                _row(
                    f.label or f.fieldname,
                    ftype,
                    doc.get(f.fieldname),
                    f.description,
                    doc.get(f"{f.fieldname}__label"),
                )
            )

    # Drop empty columns / sections / tabs so the layout has no hollow chrome.
    for t in tabs:
        for s in t["sections"]:
            s["cols"] = [c for c in s["cols"] if c]
        t["sections"] = [s for s in t["sections"] if s["cols"]]
    return [t for t in tabs if t["sections"]]


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
            _FlatField(f["fieldname"], f["label"], f["fieldtype"]) for f in share["fields"]
        ]
    else:
        all_fields = list(dt.fields)
        title_field = getattr(dt, "title_field", None) or "name"

    tabs = _build_tabs(all_fields, exposed, doc)

    meta: list[dict[str, str]] = [
        {"label": "Тип документа", "value": share["doctype_label"]},
        {"label": "Ідентифікатор", "value": share["doc_id"]},
    ]
    if doc.get("created_at"):
        meta.append({"label": "Створено", "value": _fmt_dt(doc["created_at"])})
    if doc.get("modified_at"):
        meta.append({"label": "Оновлено", "value": _fmt_dt(doc["modified_at"])})
    if share.get("expires_at"):
        meta.append({"label": "Дійсно до", "value": _fmt_dt(share["expires_at"])})

    context["share"] = share
    context["tabs"] = tabs
    context["meta"] = meta
    context["doc_title"] = (
        (doc.get(title_field) if title_field != "name" else None)
        or doc.get("name")
        or share["doc_id"]
    )
    return context


class _FlatField:
    """Minimal DocField stand-in for the no-metadata fallback path."""

    hidden = False
    description = None

    def __init__(self, fieldname: str, label: str, fieldtype: str) -> None:
        self.fieldname = fieldname
        self.label = label
        self.fieldtype = fieldtype
