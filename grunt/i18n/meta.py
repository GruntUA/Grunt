"""Serve-time translation of DocType metadata.

The frontend renders labels/descriptions/Select options straight from the
compiled DocType schema, so those strings never pass through ``_()``. This
module translates them on the way out, keyed by a stable ``msgctxt`` convention
so a translator (or the Translate app) can target a specific field:

    meta:<DocType>                → the DocType label
    meta:<DocType>.<fieldname>    → a field label
    help:<DocType>[.<fieldname>]  → a description / help text
    hint:<DocType>.<fieldname>    → a field placeholder
    select:<DocType>.<fieldname>  → one option value of a Select field
    status:<DocType>              → a status-indicator label

label / description / placeholder each get their own context so they never share
a row in the Translate registry. ``pgettext`` also falls back to a context-free
translation of the same string, so a term needs translating only once.
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

    data["label"] = _tr(f"meta:{name}", data.get("label"), lang)
    data["description"] = _tr(f"help:{name}", data.get("description"), lang)

    for field in data.get("fields") or []:
        fieldname = field.get("fieldname") or ""
        field["label"] = _tr(f"meta:{name}.{fieldname}", field.get("label"), lang)
        field["description"] = _tr(f"help:{name}.{fieldname}", field.get("description"), lang)
        field["placeholder"] = _tr(f"hint:{name}.{fieldname}", field.get("placeholder"), lang)

        if field.get("fieldtype") == "Select":
            _translate_select_options(field, f"select:{name}.{fieldname}", lang)

    for indicator in data.get("status_indicators") or []:
        indicator["label"] = _tr(f"status:{name}", indicator.get("label"), lang)

    return data


def _translate_select_options(field: dict[str, Any], ctx: str, lang: str) -> None:
    options = field.get("options")
    if isinstance(options, str):
        field["options"] = "\n".join(
            _tr(ctx, line, lang) if line.strip() else line for line in options.split("\n")
        )
    elif isinstance(options, list):
        field["options"] = [
            _tr(ctx, opt, lang) if isinstance(opt, str) and opt.strip() else opt for opt in options
        ]
