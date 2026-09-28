"""DataExport controller.

Зберігає конфігурацію експорту і виконує його асинхронно.
Результат зберігається як File-документ і прикріплюється до запису.
"""

from __future__ import annotations

import json
from typing import Any

from grunt import log
from grunt.document.base import Document
from grunt.io.doctypes.DataImport.data_import import DataImport


class DataExport(Document):
    """DocType controller for DataExport."""

    async def run(self) -> None:
        """Execute the export, save result as a File, update status."""
        self.status = "In Progress"
        await self.session.commit()

        try:
            filters: dict[str, Any] | None = None
            if self.filters:
                raw = self.filters if isinstance(self.filters, str) else json.dumps(self.filters)
                filters = json.loads(raw)

            fields: list[str] | None = None
            if self.fields_to_export:
                raw = (
                    self.fields_to_export
                    if isinstance(self.fields_to_export, str)
                    else json.dumps(self.fields_to_export)
                )
                fields = json.loads(raw)

            fmt = (self.export_format or "csv").lower()
            limit = int(self.limit or 10_000)

            file_bytes, filename = await DataImport.export_doctype(
                self.grunt,
                self.doctype_name,
                filters=filters,
                fields=fields,
                fmt=fmt,
                limit=limit,
            )

            # Save as File document and attach to this record
            file_doc = await self._save_file(filename, file_bytes, fmt)

            exported_rows = (
                len(file_bytes.splitlines()) - 1
                if fmt == "csv"
                else self._count_xlsx_rows(file_bytes)
            )

            self.status = "Success"
            self.exported_rows = max(0, exported_rows)
            self.file = file_doc["file_url"]
            self.error = ""

        except Exception as exc:
            log.exception("data_export.failed", doctype=self.doctype_name)
            self.status = "Failed"
            self.error = f"{type(exc).__name__}: {exc}"

        await self.session.commit()

    async def _save_file(self, filename: str, content: bytes, fmt: str) -> dict[str, Any]:
        """Store export bytes as a private File record."""
        from grunt.storage import store

        mime = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if fmt == "xlsx"
            else "text/csv"
        )
        file_doc = await store(content, filename, mime)
        return file_doc

    @staticmethod
    def _count_xlsx_rows(file_bytes: bytes) -> int:
        import io

        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
            ws = wb.active
            count = ws.max_row - 1 if ws is not None else 0  # subtract header row
            wb.close()
            return max(0, count)
        except Exception:
            return 0
