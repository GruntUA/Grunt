"""Print template renderer using Jinja2.

Supports:
- Standard template (auto-generated from DocType fields)
- Custom PrintFormat templates (stored in DB or files)
- Output formats: HTML, PDF (WeasyPrint), DOCX (docxtpl), XLSX (openpyxl)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from jinja2 import BaseLoader, Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from grunt.print.filters import JINJA_FILTERS

logger = structlog.get_logger()

# Core templates directory
_CORE_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_template_dirs() -> list[str]:
    """Collect all template directories from installed apps."""
    from grunt.site.manager import site_manager  # noqa: PLC0415

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
    return env


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
    from grunt.app import GruntDB  # noqa: PLC0415
    from grunt.context import _session_ctx  # noqa: PLC0415

    token = _session_ctx.set(session)
    try:
        rows = await GruntDB().get_all(
            "PrintFormat",
            filters={"name": format_name}
            if format_name
            else {"doctype": doctype, "is_default": True},
            fields=["template", "template_type"],
            limit=1,
        )
    finally:
        _session_ctx.reset(token)

    if rows:
        row = rows[0]
        return (str(row.get("template") or ""), str(row.get("template_type") or "html"))
    return None


def render_docx(template_path: str, doc: dict[str, Any]) -> bytes:
    """Render a DOCX template using docxtpl.

    Args:
        template_path: Path to the .docx template file.
        doc: Document data for template variables.

    Returns:
        DOCX file content as bytes.
    """
    import io

    from docxtpl import DocxTemplate  # noqa: PLC0415

    tpl = DocxTemplate(template_path)
    tpl.render({"doc": doc, "now": datetime.now(UTC)})

    buf = io.BytesIO()
    tpl.save(buf)
    return buf.getvalue()


def _render_fallback(doctype_label: str, fields: list[Any], doc: dict[str, Any]) -> str:
    """Minimal HTML fallback when no template file exists."""
    rows = ""
    for field in fields:
        if field.fieldtype in ("Section", "Column", "Tab", "Table"):
            continue
        if field.hidden:
            continue
        val = doc.get(field.fieldname, "")
        if val is None:
            val = ""
        rows += f"<tr><th>{field.label}</th><td>{val}</td></tr>\n"

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{font-family:Arial;margin:2cm}}h1{{color:#2D6A4F}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:6px;background:#f0f4f0;width:35%}}
td{{padding:6px;border-bottom:1px solid #eee}}</style>
</head><body>
<h1>{doctype_label}</h1>
<p>{doc.get("name", "")}</p>
<table>{rows}</table>
</body></html>"""
