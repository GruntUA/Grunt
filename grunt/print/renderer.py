"""Print template renderer using Jinja2.

Supports:
- Standard template (auto-generated from DocType fields)
- Custom PrintFormat templates (stored in DB or files)
- Output formats: HTML, PDF (headless Chromium via Playwright), DOCX (docxtpl), XLSX (openpyxl)
"""

from __future__ import annotations

import base64
import io
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, FileSystemLoader, TemplateNotFound, select_autoescape
from markupsafe import Markup

from grunt import log
from grunt.app import GruntDB
from grunt.document.meta import LAYOUT_FIELDTYPES
from grunt.i18n.jinja import install as install_i18n
from grunt.local import _session_ctx
from grunt.print.filters import JINJA_FILTERS
from grunt.site.manager import site_manager

# Core templates directory
_CORE_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_template_dirs() -> list[str]:
    """Collect all template directories from installed apps."""
    dirs: list[str] = []
    ext_apps_dir = site_manager.bench_dir / "apps"
    if ext_apps_dir.is_dir():
        for tpl_dir in ext_apps_dir.glob("*/*/templates"):
            dirs.append(str(tpl_dir))
    if _CORE_TEMPLATE_DIR.exists():
        dirs.append(str(_CORE_TEMPLATE_DIR))
    return dirs


def _get_jinja_env() -> Environment:
    """Create a Jinja2 environment with all template directories."""
    dirs = _get_template_dirs()
    env = Environment(
        loader=FileSystemLoader(dirs) if dirs else BaseLoader(),
        autoescape=select_autoescape(["html"]),
    )
    env.filters.update(JINJA_FILTERS)

    return install_i18n(env)


def render_template(template_name: str, doc: dict[str, Any]) -> str:
    """Render a named Jinja2 print template with document data."""
    env = _get_jinja_env()
    template = env.get_template(template_name)
    return template.render(doc=doc, now=datetime.now(UTC))


def render_standard(
    doctype_label: str,
    fields: list[Any],
    doc: dict[str, Any],
) -> str:
    """Render the standard print template for any DocType."""
    env = _get_jinja_env()
    try:
        template = env.get_template("standard.html")
    except TemplateNotFound:
        # Fallback: inline minimal template
        return _render_fallback(doctype_label, fields, doc)

    return template.render(
        doctype_label=doctype_label,
        fields=fields,
        doc=doc,
        now=datetime.now(UTC),
    )


def render_from_string(template_str: str, doc: dict[str, Any], **extra: Any) -> str:
    """Render a Jinja2 template from a raw string (for DB-stored PrintFormats)."""
    env = _get_jinja_env()
    template = env.from_string(template_str)
    return template.render(doc=doc, now=datetime.now(UTC), **extra)


async def get_print_format_template(
    session: Any,
    doctype: str,
    format_name: str | None = None,
) -> tuple[str, str] | None:
    """Load a PrintFormat template from DB.

    Args:
        session: DB session.
        doctype: DocType name.
        format_name: Specific format name, or None for default.

    Returns:
        Tuple of (template_content, template_type) or None.
    """
    token = _session_ctx.set(session)
    try:
        rows = await GruntDB().get_all(
            "PrintFormat",
            filters={"name": format_name}
            if format_name
            else {"ref_doctype": doctype, "is_default": True},
            fields=["template", "template_type"],
            limit=1,
        )
    finally:
        _session_ctx.reset(token)

    if rows:
        row = rows[0]
        return (str(row.get("template") or ""), str(row.get("template_type") or "html"))
    return None


# Letter heads


_BODY_OPEN = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
_BODY_CLOSE = re.compile(r"</body\s*>", re.IGNORECASE)


async def _image_data_uri(url: str | None) -> str | None:
    """An uploaded image (``get_content?file_id=`` URL) as a ``data:`` URI.

    Print HTML must be self-contained - the PDF engine loads no URLs.
    """
    from grunt.storage import files
    from grunt.storage.references import file_ids_in

    ids = file_ids_in(url or "")
    if not ids:
        return url or None
    file_id = next(iter(ids))
    try:
        content = await files.read(file_id)
        mime = await GruntDB().get_value("File", file_id, "content_type") or "image/png"
    except Exception:
        log.warning("print.letter_head_logo_missing", file_id=file_id)
        return None
    return f"data:{mime};base64,{base64.b64encode(content).decode()}"


async def load_letter_head(name: str | None = None) -> dict[str, Any] | None:
    """The named letterhead, else the default one; ``None`` if none / disabled."""
    filters: dict[str, Any] = {"name": name} if name else {"is_default": True}
    rows = await GruntDB().get_all(
        "LetterHead",
        filters={**filters, "disabled": False},
        fields=["name", "logo", "header", "footer"],
        limit=1,
    )
    if not rows:
        return None
    row = dict(rows[0])
    row["logo"] = await _image_data_uri(row.get("logo"))
    return row


def render_letter_head(letter_head: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """Render a letterhead's header/footer against *doc* -> ``letter_head`` context."""
    from grunt.config import settings

    ctx = {
        "doc": doc,
        "letter_head": {"name": letter_head["name"], "logo": letter_head.get("logo")},
        "site_url": settings.app_url.rstrip("/"),
        "now": datetime.now(UTC),
    }
    env = _get_jinja_env()
    parts = {
        part: Markup(env.from_string(letter_head.get(part) or "").render(**ctx))
        for part in ("header", "footer")
    }
    return {**ctx["letter_head"], **parts}


def apply_letter_head(html: str, letter_head: dict[str, Any]) -> str:
    """Put the rendered header right after ``<body>`` and the footer before ``</body>``."""
    header = (
        f'<div class="letter-head">{letter_head["header"]}</div>' if letter_head["header"] else ""
    )
    footer = (
        f'<div class="letter-foot">{letter_head["footer"]}</div>' if letter_head["footer"] else ""
    )
    if header:
        m = _BODY_OPEN.search(html)
        html = html[: m.end()] + header + html[m.end() :] if m else header + html
    if footer:
        matches = list(_BODY_CLOSE.finditer(html))
        html = (
            html[: matches[-1].start()] + footer + html[matches[-1].start() :]
            if matches
            else html + footer
        )
    return html


async def render_print_html(
    doctype: str,
    doc: dict[str, Any],
    print_format: str | None = None,
) -> str:
    """The document's print HTML: its PrintFormat (or the standard one) + letterhead.

    A template that mentions ``letter_head`` places ``letter_head.header`` /
    ``letter_head.footer`` itself; any other gets them inserted around the body.
    """
    import grunt

    meta = await grunt.get_meta(doctype)
    if meta is None:
        raise ValueError(f"DocType {doctype!r} not found")
    rows = await GruntDB().get_all(
        "PrintFormat",
        filters={"name": print_format}
        if print_format
        else {"ref_doctype": doctype, "is_default": True},
        fields=["template", "template_type", "letter_head", "no_letter_head"],
        limit=1,
    )
    pf = dict(rows[0]) if rows and (rows[0].get("template_type") or "html") == "html" else None

    letter_head = None
    if not (pf and pf.get("no_letter_head")):
        loaded = await load_letter_head(pf.get("letter_head") if pf else None)
        if loaded is not None:
            letter_head = render_letter_head(loaded, doc)

    html = None
    template = str(pf.get("template") or "") if pf else ""
    if template:
        try:
            html = render_from_string(
                template,
                doc,
                doctype_label=meta.doc.label,
                fields=meta.doc.fields,
                letter_head=letter_head,
            )
        except Exception:
            log.warning(
                "print.template_failed", doctype=doctype, print_format=print_format, exc_info=True
            )
    if html is None:
        template = ""
        html = render_standard(meta.doc.label, meta.doc.fields, doc)

    if letter_head and "letter_head" not in template:
        html = apply_letter_head(html, letter_head)
    return html


def render_docx(template_path: str, doc: dict[str, Any]) -> bytes:
    """Render a DOCX template using docxtpl.

    Args:
        template_path: Path to the .docx template file.
        doc: Document data for template variables.

    Returns:
        DOCX file content as bytes.
    """
    from docxtpl import DocxTemplate

    tpl = DocxTemplate(template_path)
    tpl.render({"doc": doc, "now": datetime.now(UTC)})

    buf = io.BytesIO()
    tpl.save(buf)
    return buf.getvalue()


def _render_fallback(doctype_label: str, fields: list[Any], doc: dict[str, Any]) -> str:
    """Minimal HTML fallback when no template file exists.

    Built by hand (not through Jinja, which autoescapes) because there's no
    template to render - every interpolated value is therefore document data
    or a label and MUST be escaped explicitly, or a field value containing
    HTML/script becomes a stored XSS in the print/HTML view every viewer of
    that document opens.
    """
    rows = ""
    for field in fields:
        if field.fieldtype in LAYOUT_FIELDTYPES or field.fieldtype == "Table":
            continue
        if field.hidden:
            continue
        val = doc.get(field.fieldname, "")
        if val is None:
            val = ""
        rows += f"<tr><th>{escape(field.label)}</th><td>{escape(str(val))}</td></tr>\n"

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{font-family:Arial;margin:2cm}}h1{{color:#2D6A4F}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:6px;background:#f0f4f0;width:35%}}
td{{padding:6px;border-bottom:1px solid #eee}}</style>
</head><body>
<h1>{escape(doctype_label)}</h1>
<p>{escape(str(doc.get("name", "")))}</p>
<table>{rows}</table>
</body></html>"""
