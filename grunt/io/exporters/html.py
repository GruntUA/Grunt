"""HTML exporter - the list view as a standalone, printable page.

The page itself is ``templates/list_export.html``; this module prepares its
context (visible columns, rows or groups, status indicators) and the ``fmt``
filter that prints a value the way the desk does (``formatValue`` on the
frontend), see :mod:`grunt.i18n.values`.
"""

import functools
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from grunt.i18n.jinja import install as install_i18n
from grunt.i18n.meta import translate_doctype_meta
from grunt.i18n.values import site_value_formatter
from grunt.io.exporters.registry import Exporter, ListExportContext
from grunt.metadata.registry import doctype_registry
lazy from grunt.metadata.field import DocField

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# Rows past this many were cut off - the list endpoints cap at 10 000.
_EXPORT_CAP = 10_000

# #hex, a named colour or rgb()/hsl() - anything else would escape the style attribute.
_CSS_COLOR = re.compile(r"^#?[\w\s(),.%-]+$")


@dataclass
class _Column:
    """A visible column - the field with its translated label / option captions."""

    fieldname: str
    label: str
    fieldtype: str
    options: str | None = None
    option_labels: dict[str, str] = field(default_factory=dict)


def _css_color(value: Any) -> str:
    s = str(value).strip()
    return s if _CSS_COLOR.match(s) else "transparent"


@functools.cache
def _env() -> Environment:
    # Our own file, not user-authored like a PrintFormat - no sandbox needed.
    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)
    env.filters["css_color"] = _css_color
    return install_i18n(env)


def _group(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """Rows sharing a value of *field*, groups in first-seen order."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = row.get(field)
        groups.setdefault("" if value is None else str(value), []).append(row)
    return [{"key": key, "rows": items} for key, items in groups.items()]


class HtmlExporter(Exporter):
    id = "html"
    label = "HTML"
    content_type = "text/html; charset=utf-8"
    file_extension = "html"

    async def export(
        self,
        doctype: str,
        rows: list[dict[str, Any]],
        fields: list[DocField],
    ) -> bytes:
        return await self.export_list(doctype, rows, fields, ListExportContext(total=len(rows)))

    async def export_list(
        self,
        doctype: str,
        rows: list[dict[str, Any]],
        fields: list[DocField],
        ctx: ListExportContext,
    ) -> bytes:
        meta = await doctype_registry.get_meta(doctype)
        dt = translate_doctype_meta(meta.doc.model_dump()) if meta else {}
        translated = {f["fieldname"]: f for f in dt.get("fields") or []}
        columns = [
            _Column(
                fieldname=f.fieldname,
                label=translated.get(f.fieldname, {}).get("label") or f.label,
                fieldtype=f.fieldtype,
                options=f.options,
                option_labels=translated.get(f.fieldname, {}).get("option_labels") or {},
            )
            for f in fields
            if f.is_physical
        ]
        group_by = ctx.group_by or None
        group_field = translated.get(group_by or "")

        fmt = await site_value_formatter()

        env = _env().overlay()
        env.filters["fmt"] = fmt
        html = env.get_template("list_export.html").render(
            doctype_name=doctype,
            doctype_label=dt.get("label") or doctype,
            columns=columns,
            rows=rows,
            groups=_group(rows, group_by) if group_by else None,
            group_by=group_by,
            group_by_label=(group_field or {}).get("label") or group_by,
            status_field=dt.get("status_field"),
            indicators={i["value"]: i for i in dt.get("status_indicators") or []},
            row_count=len(rows),
            total=ctx.total,
            is_partial=len(rows) < ctx.total and ctx.total > _EXPORT_CAP,
            filter_summary=ctx.filter_summary,
            generated_at=fmt.date(datetime.now(UTC), time=True),
        )
        return html.encode("utf-8")
