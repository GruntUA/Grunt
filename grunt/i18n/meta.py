"""Serve-time translation of DocType metadata.

The frontend renders labels/descriptions/Select options straight from the
compiled DocType schema, so those strings never pass through ``_()``. This
module translates them on the way out, keyed by a stable ``msgctxt`` convention
so a translator (or the Translate app) can target a specific field:

    meta:<DocType>                -> the DocType label
    meta:<DocType>.<fieldname>    -> a field label
    help:<DocType>[.<fieldname>]  -> a description / help text
    hint:<DocType>.<fieldname>    -> a field placeholder
    select:<DocType>.<fieldname>  -> one option caption of a ``translatable`` Select
    status:<DocType>              -> a status-indicator label
    record:<DocType>.<fieldname>  -> the value of a ``translatable`` text field in
                                     a standard record (see :func:`translate_record`)

label / description / placeholder each get their own context so they never share
a row in the Translate registry. ``pgettext`` also falls back to a context-free
translation of the same string, so a term needs translating only once.
"""

from typing import Any

from grunt.i18n.service import translation_service
from grunt.metadata.field import fieldtypes_with
lazy import grunt

# Types whose value is picked from ``options`` - their choices get translated.
SELECT_FIELDTYPES = fieldtypes_with("options")


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

        if field.get("translatable") and field.get("fieldtype") in SELECT_FIELDTYPES:
            labels = option_labels(field.get("options"), f"select:{name}.{fieldname}", lang)
            if labels:
                field["option_labels"] = labels

    for indicator in data.get("status_indicators") or []:
        indicator["label"] = _tr(f"status:{name}", indicator.get("label"), lang)

    return data


def option_values(options: Any) -> list[str]:
    """Stored values of a Select ``options`` spec (newline string or list); an
    ``value|IconName`` line contributes only ``value``."""
    lines = options.split("\n") if isinstance(options, str) else options or []
    return [v for v in (str(line).split("|", 1)[0].strip() for line in lines) if v]


def option_labels(options: Any, ctx: str, lang: str) -> dict[str, str]:
    """``{value: caption}`` for the options whose translation differs. The option
    values themselves are what gets stored, so they are never rewritten."""
    labels = {}
    for value in option_values(options):
        caption = _tr(ctx, value, lang)
        if caption != value:
            labels[value] = caption
    return labels


async def translate_record(doc: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    """Translate the ``translatable`` text fields of *doc* and its child rows in place.

    For records an app ships in English (standard records): the extractor
    collects these values from the record files, the reader shows them in the
    user's language.
    """

    meta = await grunt.get_meta(doc.get("doctype") or "")
    if meta is None:
        return doc
    lang = lang or translation_service.get_lang()
    name = meta.doc.name
    for field in meta.doc.fields:
        value = doc.get(field.fieldname)
        if field.fieldname in meta.get_table_fieldnames() and isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    await translate_record(row, lang)
        elif field.translatable and field.fieldtype not in SELECT_FIELDTYPES:
            doc[field.fieldname] = _tr(f"record:{name}.{field.fieldname}", value, lang)
    return doc
