"""XLSX importer."""

from pathlib import Path
from typing import Any

import openpyxl

from grunt.io.importers.registry import Importer


class XlsxImporter(Importer):
    id = "xlsx"
    label = "Excel (XLSX)"
    accepted_extensions = ["xlsx", "xls"]

    def read(self, file_path: Path, limit: int | None = None) -> list[list[Any]]:
        # A file object, not the path: stored blobs have no extension, and
        # openpyxl rejects a path that doesn't end in .xlsx.
        with open(file_path, "rb") as f:
            wb = openpyxl.load_workbook(f, data_only=True, read_only=True)
            ws = wb.active
            rows: list[list[Any]] = []
            for i, row in enumerate(ws.iter_rows(values_only=True) if ws is not None else []):
                if limit is not None and i >= limit:
                    break
                rows.append(list(row))
            wb.close()
        return rows
