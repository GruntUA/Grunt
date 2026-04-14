"""XLSX importer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl

from grunt.core.io.importers.registry import Importer


class XlsxImporter(Importer):
    id = "xlsx"
    label = "Excel (XLSX)"
    accepted_extensions = ["xlsx", "xls"]

    def read(self, file_path: Path, limit: int | None = None) -> list[list[Any]]:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        ws = wb.active
        rows: list[list[Any]] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if limit is not None and i >= limit:
                break
            rows.append(list(row))
        wb.close()
        return rows
