"""CSV importer."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING, Any

from grunt.io.importers.registry import Importer

if TYPE_CHECKING:
    from pathlib import Path


class CsvImporter(Importer):
    id = "csv"
    label = "CSV"
    accepted_extensions = ["csv", "txt"]

    def read(self, file_path: Path, limit: int | None = None) -> list[list[Any]]:
        with open(file_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows: list[list[Any]] = []
            for i, row in enumerate(reader):
                if limit is not None and i >= limit:
                    break
                rows.append(row)
        return rows
