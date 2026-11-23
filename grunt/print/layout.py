"""The standard print layout of a document - what ``standard.html`` draws.

The DocType's own form layout, read the way the form reads it: a Tab opens a
part with a heading, a Section a block, a Column a column within it. Every
value is formatted here, on the server, the way the desk shows it: a Link's
title instead of its id, a Select's caption, numbers with ``precision`` and the
language's separators, dates in the site's format, RichText as sanitized HTML,
images inline. Child tables become tables of their ``in_list_view`` columns.

Not printed: hidden and ``print_hide`` fields, secrets, layout-only and JSON
fields, and empty values (``print_hide_if_no_value`` also drops a zero /
unchecked one). Sections and parts left with nothing in them are dropped.
``depends_on`` is a form-side (JavaScript) condition and is not evaluated - a
field it would hide usually has no value anyway.
"""

import base64
from dataclasses import dataclass, field
from html import escape
from typing import Any

from markupsafe import Markup

from grunt.db.api import GruntDB
from grunt.i18n.meta import translate_doctype_meta
from grunt.i18n.values import ValueFormatter, site_value_formatter
from grunt.log import log
from grunt.metadata.field import DocField, get_storage_class
from grunt.metadata.registry import doctype_registry
from grunt.utils.sanitize import sanitize_html
lazy from grunt.document.titles import resolve_reference_titles
lazy from grunt.storage import files
lazy from grunt.storage.references import file_ids_in

# Columns a child table gets when none of its fields is ``in_list_view``.
_DEFAULT_TABLE_COLUMNS = 6

# Image sources an <img> may print - not ``javascript:`` or other schemes.
_IMAGE_SOURCES = ("data:image/", "https://", "http://", "/")

# Long text that takes the whole width of its section instead of a label / value row.
_WIDE_FIELDTYPES = frozenset({"LongText", "Code", "Signature"})


@dataclass
class PrintField:
    label: str
    value: Markup
    fieldname: str
    fieldtype: str
    # Text that reads better under its label, over the full width.
    wide: bool = False


@dataclass
class PrintTable:
    label: str
    fieldname: str
    # (label, numeric) per column - numbers are right-aligned.
    columns: list[tuple[str, bool]]
    rows: list[list[Markup]]


@dataclass
class PrintSection:
    label: str = ""
    # Set on the first section of a Tab - printed as the part's heading.
    tab_label: str = ""
    columns: list[list[PrintField | PrintTable]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(self.columns)


@dataclass
class _Context:
    """What formatting a document needs, fetched up front in a few queries."""

    fmt: ValueFormatter
    # (doctype, id) -> title
    titles: dict[tuple[str, str], str] = field(default_factory=dict)
    # file id -> file name
    file_names: dict[str, str] = field(default_factory=dict)
    # image URL -> data: URI
    images: dict[str, str] = field(default_factory=dict)


# Building


async def build_print_layout(doctype: str, doc: dict[str, Any]) -> list[PrintSection]:
    """*doc*'s printable sections, in form order, values formatted."""

    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise ValueError(f"DocType {doctype!r} not found")

    tables = {
        f.fieldname: child
        for f in meta.doc.fields
        if f.has_trait("table") and (child := await doctype_registry.get_meta(f.options or ""))
    }
    ctx = _Context(fmt=await site_value_formatter())
    await _prefetch(ctx, meta.doc.fields, doc, tables)

    captions = _captions(meta.doc)
    sections: list[PrintSection] = []
    current = PrintSection(columns=[[]])
    pending_tab = ""

    def close() -> None:
        nonlocal pending_tab
        if not current.is_empty:
            if pending_tab and not current.tab_label:
                current.tab_label = pending_tab
            pending_tab = ""
            current.columns = [c for c in current.columns if c]
            sections.append(current)

    for f in meta.doc.fields:
        label = captions.get(f.fieldname, {}).get("label") or f.label
        if f.fieldtype == "Tab":
            close()
            pending_tab = label
            current = PrintSection(columns=[[]])
        elif f.fieldtype == "Section":
            close()
            current = PrintSection(label=label, columns=[[]])
        elif f.fieldtype == "Column":
            current.columns.append([])
        elif f.fieldname in tables:
            if _printable(f):
                rows = doc.get(f.fieldname)
                table = _table(f, label, rows if isinstance(rows, list) else [], tables, ctx)
                if table is not None:
                    current.columns[-1].append(table)
        elif (item := _field(f, label, doc, captions, ctx)) is not None:
            current.columns[-1].append(item)
    close()
    return sections


def _captions(dt: Any) -> dict[str, dict[str, Any]]:
    """Translated label / option captions of *dt*'s fields, by fieldname."""
    translated = translate_doctype_meta(dt.model_dump())
    return {f["fieldname"]: f for f in translated.get("fields") or []}


def _printable(f: DocField) -> bool:
    if f.is_layout or f.hidden or f.print_hide or f.has_trait("sensitive"):
        return False
    if f.has_trait("table") or f.fieldtype == "MultiLink":
        return True
    # No column (Button, HTML) or structured data (JSON, EmbeddedForm...) -
    # nothing a reader could read; a choice list or a point on the map is.
    storage = get_storage_class(f.fieldtype)
    if storage == "none":
        return False
    if storage == "json":
        return f.has_trait("options") or f.fieldtype == "Geolocation"
    return True


def _has_value(f: DocField, value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return False
    return not (f.print_hide_if_no_value and (value is False or value == 0))


def _field(
    f: DocField,
    label: str,
    doc: dict[str, Any],
    captions: dict[str, dict[str, Any]],
    ctx: _Context,
) -> PrintField | None:
    if not _printable(f):
        return None
    value = doc.get(f.fieldname)
    if not _has_value(f, value):
        return None
    html = _value_html(f, value, doc, captions.get(f.fieldname, {}), ctx)
    if not html:
        return None
    wide = f.fieldtype in _WIDE_FIELDTYPES or f.has_trait("html")
    return PrintField(
        label=label, value=html, fieldname=f.fieldname, fieldtype=f.fieldtype, wide=wide
    )


def _table(
    f: DocField,
    label: str,
    rows: list[Any],
    tables: dict[str, Any],
    ctx: _Context,
) -> PrintTable | None:
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return None
    child = tables[f.fieldname]
    captions = _captions(child.doc)
    candidates = [c for c in child.doc.fields if _printable(c) and not c.has_trait("table")]
    columns = [c for c in candidates if c.in_list_view] or candidates[:_DEFAULT_TABLE_COLUMNS]

    cells = [
        [
            _value_html(c, row.get(c.fieldname), row, captions.get(c.fieldname, {}), ctx)
            if _has_value(c, row.get(c.fieldname))
            else Markup("")
            for c in columns
        ]
        for row in rows
    ]
    # A column empty in every row says nothing.
    keep = [i for i in range(len(columns)) if any(row[i] for row in cells)]
    if not keep:
        return None
    return PrintTable(
        label=label,
        fieldname=f.fieldname,
        columns=[
            (
                captions.get(columns[i].fieldname, {}).get("label") or columns[i].label,
                columns[i].is_numeric,
            )
            for i in keep
        ],
        rows=[[row[i] for i in keep] for row in cells],
    )


# Values


def _value_html(
    f: DocField,
    value: Any,
    doc: dict[str, Any],
    caption: dict[str, Any],
    ctx: _Context,
) -> Markup:
    """*value* of *f* as safe HTML."""

    if f.has_trait("html"):
        return Markup(sanitize_html(str(value)))
    if f.has_trait("options"):
        labels = caption.get("option_labels") or {}
        values = value if isinstance(value, list) else [value]
        captions = (str(labels.get(v, v)) for v in values if v not in (None, ""))
        return Markup(escape(", ".join(captions)))
    if f.has_trait("link") or f.has_trait("dynamic_link") or f.fieldtype == "MultiLink":
        target = _link_doctype(f, doc)
        names = value if isinstance(value, list) else [value]
        return Markup(
            escape(", ".join(ctx.titles.get((target, str(n)), str(n)) for n in names if n))
        )
    if f.fieldtype == "Signature" or (f.has_trait("file") and f.fieldtype == "Image"):
        src = ctx.images.get(str(value)) or str(value)
        if not src.startswith(_IMAGE_SOURCES):
            return Markup("")
        return Markup('<img class="print-image" src="{}" alt="">').format(src)
    if f.has_trait("file"):
        ids = file_ids_in(str(value))
        name = ctx.file_names.get(next(iter(ids))) if ids else None
        return Markup(escape(name or str(value).rsplit("/", 1)[-1]))
    if f.fieldtype == "Code":
        return Markup("<pre>{}</pre>").format(str(value))
    text = ctx.fmt(value, f, doc)
    if f.fieldtype == "LongText":
        return Markup("<br>").join(text.splitlines())
    return Markup(escape(text))


def _link_doctype(f: DocField, doc: dict[str, Any]) -> str:
    if f.has_trait("dynamic_link"):
        return str(doc.get(f.options or "") or "")
    return f.options or ""


# Prefetch: titles, file names, images


async def _prefetch(
    ctx: _Context,
    fields: list[DocField],
    doc: dict[str, Any],
    tables: dict[str, Any],
) -> None:
    refs: set[tuple[str, str]] = set()
    file_urls: set[str] = set()
    image_urls: set[str] = set()

    def collect(fields: list[DocField], row: dict[str, Any]) -> None:
        for f in fields:
            value = row.get(f.fieldname)
            if not value or not _printable(f):
                continue
            if f.has_trait("link") or f.has_trait("dynamic_link") or f.fieldtype == "MultiLink":
                target = _link_doctype(f, row)
                for name in value if isinstance(value, list) else [value]:
                    if target and name:
                        refs.add((target, str(name)))
            elif f.has_trait("file"):
                (image_urls if f.fieldtype == "Image" else file_urls).add(str(value))

    collect(fields, doc)
    for fieldname, child in tables.items():
        for row in doc.get(fieldname) or []:
            if isinstance(row, dict):
                collect(child.doc.fields, row)

    if refs:
        ctx.titles = await resolve_reference_titles(sorted(refs))
    ids = {i for url in file_urls for i in file_ids_in(url)}
    if ids:
        rows = await GruntDB().get_all(
            "File", filters={"name__in": sorted(ids)}, fields=["name", "file_name"]
        )
        ctx.file_names = {r.name: r.file_name for r in rows if r.file_name}
    for url in image_urls:
        if uri := await image_data_uri(url):
            ctx.images[url] = uri


async def image_data_uri(url: str | None) -> str | None:
    """An uploaded image (``get_content?file_id=`` URL) as a ``data:`` URI.

    Print HTML must be self-contained - the PDF engine loads no URLs.
    """

    ids = file_ids_in(url or "")
    if not ids:
        return url or None
    file_id = next(iter(ids))
    try:
        content = await files.read(file_id)
        mime = await GruntDB().get_value("File", file_id, "content_type") or "image/png"
    except Exception:
        log.warning("print.image_missing", file_id=file_id)
        return None
    return f"data:{mime};base64,{base64.b64encode(content).decode()}"
