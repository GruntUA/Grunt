"""HTML exporter - the list view as a standalone, printable page.

The page itself is ``templates/list_export.html``; this module prepares its
context (visible columns, rows or groups, status indicators) and the ``fmt``
filter that prints a value the way the desk does (``formatValue`` on the
frontend): dates in SystemSettings ``date_format`` / ``timezone``, numbers
with the UI language's separators, durations, byte sizes.
"""

import functools
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

import grunt
from grunt import _
from grunt.i18n.jinja import install as install_i18n
from grunt.i18n.meta import translate_doctype_meta
from grunt.i18n.service import translation_service
from grunt.io.exporters.registry import Exporter, ListExportContext
from grunt.site.settings import get_system_settings
lazy from grunt.metadata.field import DocField, is_numeric_fieldtype

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# Rows past this many were cut off - the list endpoints cap at 10 000.
_EXPORT_CAP = 10_000

_DURATION_UNITS = (
    ("{n} d", 86_400_000),
    ("{n} h", 3_600_000),
    ("{n} min", 60_000),
    ("{n} s", 1_000),
)
_BYTE_UNITS = ("KB", "MB", "GB", "TB")

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


class _Formatter:
    """Plain-text values for one export - settings are read once, not per cell."""

    def __init__(self, date_format: str, tz: ZoneInfo | None, lang: str) -> None:
        self.date_format = date_format
        self.tz = tz
        # uk (and the rest of continental Europe): `1 234,5`; en: `1,234.5`.
        self.comma_decimal = lang != "en"

    def number(self, n: float) -> str:
        s = f"{n:,.3f}".rstrip("0").rstrip(".")
        if self.comma_decimal:
            s = s.replace(",", " ").replace(".", ",")
        return s

    def date(self, value: Any, *, time: bool = False) -> str:
        d = _to_datetime(value)
        if d is None:
            return str(value)
        if time and isinstance(d, datetime):
            # Server timestamps are UTC; a naive one is tagged before converting.
            if d.tzinfo is None:
                d = d.replace(tzinfo=UTC)
            if self.tz:
                d = d.astimezone(self.tz)
        y, m, day = f"{d.year:04d}", f"{d.month:02d}", f"{d.day:02d}"
        match self.date_format:
            case "yyyy-mm-dd":
                out = f"{y}-{m}-{day}"
            case "dd/mm/yyyy":
                out = f"{day}/{m}/{y}"
            case _:
                out = f"{day}.{m}.{y}"
        if time and isinstance(d, datetime):
            out += f" {d.hour:02d}:{d.minute:02d}"
        return out

    def duration(self, value: Any, field: _Column | DocField) -> str:
        n = _to_float(value)
        if n is None:
            return str(value)
        ms_unit = (field.options or "").strip().lower() == "ms"
        sign = "−" if n < 0 else ""
        rest = round(abs(n) * (1 if ms_unit else 1000))
        if ms_unit and rest < 1000:
            return sign + _("{n} ms").replace("{n}", str(rest))
        rest = round(rest / 1000) * 1000
        parts = []
        for key, size in _DURATION_UNITS:
            count, rest = divmod(rest, size)
            if count:
                parts.append(_(key).replace("{n}", str(count)))
        return sign + (" ".join(parts) or _("{n} s").replace("{n}", "0"))

    def bytes(self, n: float) -> str:
        if abs(n) < 1024:
            return f"{self.number(n)} {_('B')}"
        value, i = n / 1024, 0
        while abs(value) >= 1024 and i < len(_BYTE_UNITS) - 1:
            value /= 1024
            i += 1
        return f"{self.number(round(value, 1 if abs(value) < 10 else 0))} {_(_BYTE_UNITS[i])}"

    def __call__(self, value: Any, field: _Column | DocField) -> str:
        if value is None or value == "":
            return "—"
        match field.fieldtype:
            case "Date":
                return self.date(value)
            case "Datetime":
                return self.date(value, time=True)
            case "Duration":
                return self.duration(value, field)
            case "Check":
                return "✓" if value in (True, 1, "1", "true") else "✗"
            case "Geolocation" if isinstance(value, dict) and "lat" in value and "lng" in value:
                return f"{float(value['lat']):.5f}, {float(value['lng']):.5f}"
        if is_numeric_fieldtype(field.fieldtype) and (n := _to_float(value)) is not None:
            if field.fieldtype == "Int" and field.options == "Bytes":
                return self.bytes(n)
            return self.number(n)
        return str(value)


def _to_datetime(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        s = str(value).strip()
        return datetime.fromisoformat(s) if len(s) > 10 else date.fromisoformat(s)
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    try:
        n = float(value)
    except TypeError, ValueError:
        return None
    return n if math.isfinite(n) else None


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
        meta = await grunt.get_meta(doctype)
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

        settings = await get_system_settings()
        tz_name = settings.get("timezone")
        fmt = _Formatter(
            settings.get("date_format") or "dd.mm.yyyy",
            ZoneInfo(tz_name) if tz_name else None,
            translation_service.get_lang(),
        )

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
