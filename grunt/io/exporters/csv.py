"""CSV exporter - UTF-8 with BOM for Excel compatibility."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

from grunt.io.exporters.registry import Exporter
from grunt.io.exporters.sanitize import escape_formula

if TYPE_CHECKING:
    from grunt.metadata.field import DocField


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        if "lat" in value and "lng" in value:
            return escape_formula(f"{value['lat']}, {value['lng']}")
        return escape_formula(str(value))
    return escape_formula(str(value))


class CsvExporter(Exporter):
    id = "csv"
    label = "CSV"
    content_type = "text/csv; charset=utf-8-sig"
    file_extension = "csv"

    async def export(
        self,
        doctype: str,
        rows: list[dict[str, Any]],
        fields: list[DocField],
    ) -> bytes:
        exportable = [f for f in fields if f.is_physical]
        col_labels = [f.label for f in exportable]
        col_names = [f.fieldname for f in exportable]

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(col_labels)
        for row in rows:
            writer.writerow([_fmt(row.get(c)) for c in col_names])

        return buf.getvalue().encode("utf-8-sig")  # BOM for Excel
