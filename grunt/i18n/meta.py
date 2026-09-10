"""Serve-time translation of DocType metadata.

The frontend renders labels/descriptions/Select options straight from the
compiled DocType schema, so those strings never pass through ``_()``. This
module translates them on the way out, keyed by a stable ``msgctxt`` convention
so a translator (or the Translate app) can target a specific field:

    meta:<DocType>                → the DocType's own label / description
    meta:<DocType>.<fieldname>    → a field's label / description / placeholder
    select:<DocType>.<fieldname>  → one option value of a Select field
    status:<DocType>              → a status-indicator label

``translation_service.pgettext`` returns the source string unchanged when there
is no entry (and always for ``lang == "en"``), so this is a safe no-op until
translations exist.
"""

from __future__ import annotations

from typing import Any

from grunt.i18n.service import translation_service


def _tr(ctx: str, text: Any, lang: str) -> Any:
    if not text or not isinstance(text, str):
        return text
    return translation_service.pgettext(ctx, text, lang=lang)


def translate_doctype_meta(data: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    """Translate *data* (a ``DocType.model_dump()``) in place for *lang*."""
    lang = lang or translation_service.get_lang()
    name = data.get("name")
    if not name:
        return data

    dt_ctx = f"meta:{name}"
    data["label"] = _tr(dt_ctx, data.get("label"), lang)
    data["description"] = _tr(dt_ctx, data.get("description"), lang)

    for field in data.get("fields") or []:
        fieldname = field.get("fieldname") or ""
        fctx = f"meta:{name}.{fieldname}"
        field["label"] = _tr(fctx, field.get("label"), lang)
        field["description"] = _tr(fctx, field.get("description"), lang)
        field["placeholder"] = _tr(fctx, field.get("placeholder"), lang)

        if field.get("fieldtype") == "Select":
            _translate_select_options(field, f"select:{name}.{fieldname}", lang)

    for indicator in data.get("status_indicators") or []:
        indicator["label"] = _tr(f"status:{name}", indicator.get("label"), lang)

    return data


def _translate_select_options(field: dict[str, Any], ctx: str, lang: str) -> None:
    options = field.get("options")
    if isinstance(options, str):
        field["options"] = "\n".join(
            _tr(ctx, line, lang) if line.strip() else line
            for line in options.split("\n")
        )
    elif isinstance(options, list):
        field["options"] = [
            _tr(ctx, opt, lang) if isinstance(opt, str) and opt.strip() else opt
            for opt in options
        ]
