"""A document laid out by its DocType's Tab → Section → Column structure,
for the server-rendered read-only views (``/share/{token}``, web view pages).
"""

from __future__ import annotations

from typing import Any

# Framework bookkeeping fields never shown in the read-only share view.
_SKIP_FIELDS = {"id", "name", "owner", "created_at", "modified_at", "modified_by", "docstatus"}
_MULTILINE = {"LongText", "Text", "HTML", "Code", "Markdown"}
# Sanitized HTML (grunt.utils.sanitize) — a web view renders it as markup (``row.html``).
_RICH = {"RichText"}
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


def fmt_dt(raw: Any) -> str:
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
        "html": fieldtype in _RICH and raw not in (None, ""),
        "description": description,
    }


def build_tabs(
    all_fields: list[Any],
    doc: dict[str, Any],
    exposed: set[str] | None = None,
    skip: set[str] | None = None,
) -> list[dict]:
    """Walk the DocType's ordered field list and rebuild its Tab → Section →
    Column layout, keeping only the data fields in *exposed* (all when empty)
    and never those in *skip*.
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
            if skip and f.fieldname in skip:
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


class FlatField:
    """Minimal DocField stand-in for the no-metadata fallback path."""

    hidden = False
    description = None

    def __init__(self, fieldname: str, label: str, fieldtype: str) -> None:
        self.fieldname = fieldname
        self.label = label
        self.fieldtype = fieldtype
