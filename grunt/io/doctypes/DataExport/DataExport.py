"""DataExport controller.

Зберігає конфігурацію експорту і виконує його асинхронно.
Результат зберігається як File-документ і прикріплюється до запису.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from grunt.io.doctypes.DataImport.DataImport import DataImport
from grunt.document.base import Document

logger = structlog.get_logger()


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
            self.file = f"/api/v1/files/{file_doc['id']}"
            self.error = ""

        except Exception as exc:
            logger.exception("data_export.failed", doctype=self.doctype_name)
            self.status = "Failed"
            self.error = f"{type(exc).__name__}: {exc}"

        await self.session.commit()

    async def _save_file(self, filename: str, content: bytes, fmt: str) -> dict[str, Any]:
        """Store export bytes via the storage backend and create a File record."""
        from grunt.storage import get_storage_backend  # noqa: PLC0415

        mime = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if fmt == "xlsx"
            else "text/csv"
        )
        storage = get_storage_backend()
        path = await storage.save(content=content, filename=filename, content_type=mime)

        user = self.grunt.session
        file_doc = await self.grunt.new_doc(
            "File",
            {
                "file_name": filename,
                "path": path,
                "content_type": mime,
                "file_size": len(content),
                "uploaded_by": user.user,
                "is_public": False,
            },
        )
        file_id = str(file_doc["id"])
        file_url = f"/api/v1/files/{file_id}"
        await self.grunt.save_doc("File", file_id, {"file_url": file_url})
        file_doc["id"] = file_id
        return file_doc

    @staticmethod
    def _count_xlsx_rows(file_bytes: bytes) -> int:
        import io  # noqa: PLC0415

        import openpyxl  # noqa: PLC0415

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
            ws = wb.active
            count = ws.max_row - 1  # subtract header row
            wb.close()
            return max(0, count)
        except Exception:
            return 0
