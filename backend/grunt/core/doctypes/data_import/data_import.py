import json
from pathlib import Path
from typing import Any

import structlog

from grunt.core.document.base import Document
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

# Field types that are skippable in import/export templates
_SKIP_FIELDTYPES = frozenset({"Section", "Column", "Tab", "Table", "MultiLink", "HTML", "Heading"})


class DataImport(Document):
    """DocType controller for DataImport."""

    async def after_insert(self) -> None:
        """Trigger the import task after the document is created."""
        if self.data.get("status") == "Pending":
            from grunt.core.data_import.tasks import run_data_import  # noqa: PLC0415

            logger.info("data_import.triggering_task", id=self.data["id"])
            await run_data_import.kiq(self.data["id"])

    async def get_preview(self) -> dict[str, Any]:
        """Extract headers and first 5 data rows for column mapping."""
        file_path = await self._resolve_file_path()
        data = self._read_file(file_path, limit=6)  # header + 5 rows
        dt = await doctype_registry.get(self.doctype_name)

        headers = [str(h) if h is not None else "" for h in (data[0] if data else [])]
        suggestions: dict[str, str] = {}
        for header in headers:
            for field in dt.fields:
                if (
                    field.label.lower() == header.lower()
                    or field.fieldname.lower() == header.lower()
                ):
                    suggestions[header] = field.fieldname
                    break

        return {
            "headers": headers,
            "preview_rows": data[1:] if len(data) > 1 else [],
            "suggested_mapping": suggestions,
            "doctype_fields": [
                {"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype, "required": f.required}
                for f in dt.fields
                if f.fieldtype not in _SKIP_FIELDTYPES
            ],
        }

    async def run(self) -> None:
        """Execute the import process (or dry-run validation)."""
        self.status = "In Progress"
        await self.session.commit()

        try:
            file_path = await self._resolve_file_path()
        except FileNotFoundError as exc:
            self.status = "Failed"
            self.error_log = json.dumps([{"row": 0, "error": str(exc)}])
            await self.session.commit()
            return

        all_rows = self._read_file(file_path)
        if not all_rows:
            self.status = "Failed"
            self.error_log = json.dumps([{"row": 0, "error": "File is empty"}])
            await self.session.commit()
            return

        headers = [str(h) if h is not None else "" for h in all_rows[0]]
        rows = all_rows[1:]

        mapping: dict[str, str] = self.mapping
        if isinstance(mapping, str):
            mapping = json.loads(mapping)

        # Load required fields for dry-run validation
        dt = await doctype_registry.get(self.doctype_name)
        required_fields = {f.fieldname for f in dt.fields if f.required and f.fieldtype not in _SKIP_FIELDTYPES}
        mapped_dt_fields = set(mapping.values())

        total = len(rows)
        processed = 0
        errors: list[dict[str, Any]] = []

        for idx, row_data in enumerate(rows):
            row_num = idx + 2  # 1-based, accounting for header row
            try:
                row_dict = dict(zip(headers, [str(v) if v is not None else "" for v in row_data], strict=False))
                doc_data: dict[str, Any] = {}
                for file_col, dt_field in mapping.items():
                    if dt_field and file_col in row_dict:
                        doc_data[dt_field] = row_dict[file_col]

                if self.dry_run:
                    # Validate required fields are present and non-empty
                    missing = [f for f in required_fields if f in mapped_dt_fields and not doc_data.get(f)]
                    if missing:
                        raise ValueError(f"Обов'язкові поля відсутні або порожні: {', '.join(missing)}")
                    # Validate update key exists when updating
                    if self.import_type == "Update Existing":
                        key = self.update_key
                        if not key:
                            raise ValueError("Ключ для оновлення не вказаний")
                        if not doc_data.get(key):
                            raise ValueError(f"Значення ключа '{key}' відсутнє в рядку")
                else:
                    if self.import_type == "Update Existing":
                        key = self.update_key
                        if not key:
                            raise ValueError("Ключ для оновлення не вказаний")
                        key_value = doc_data.get(key)
                        if not key_value:
                            raise ValueError(f"Значення ключа '{key}' відсутнє в рядку")
                        existing = await self.grunt.get_list(
                            self.doctype_name, filters={key: key_value}, limit=1
                        )
                        if existing:
                            await self.grunt.save_doc(self.doctype_name, existing[0]["id"], doc_data)
                        else:
                            raise ValueError(f"Документ з {key}={key_value} не знайдено")
                    else:
                        await self.grunt.new_doc(self.doctype_name, doc_data)

                processed += 1
            except Exception as exc:
                errors.append({"row": row_num, "error": str(exc)})

            if idx % 10 == 0:
                await self._update_db_progress(processed, len(errors), errors)

        self.status = (
            "Success" if not errors else ("Partial Success" if processed > 0 else "Failed")
        )
        self.total_rows = total
        self.processed_rows = processed
        self.error_count = len(errors)
        self.error_log = json.dumps(errors)
        await self.session.commit()

    async def _update_db_progress(self, processed: int, error_count: int, error_log: list[Any]) -> None:
        self.processed_rows = processed
        self.error_count = error_count
        self.error_log = json.dumps(error_log)
        await self.session.commit()

    async def _resolve_file_path(self) -> Path:
        """Resolve the attached file reference to an absolute Path."""
        path = Path(self.file)
        if path.exists():
            return path
        if self.file.startswith("/api/v1/files/"):
            file_id = self.file.rstrip("/").split("/")[-1]
            doc = await self.grunt.get_doc("File", file_id)
            if doc:
                return Path(doc["path"])
        raise FileNotFoundError(f"Import file not found: {self.file}")

    @staticmethod
    def _read_file(file_path: Path, limit: int | None = None) -> list[list[Any]]:
        """Read CSV or XLSX file via the io importer registry."""
        from grunt.core.io.importers.registry import get_importer_for_file  # noqa: PLC0415

        imp = get_importer_for_file(file_path.name)
        if imp is None:
            raise ValueError(f"Непідтримуваний формат файлу: {file_path.suffix}")
        return imp.read(file_path, limit=limit)

    # ──────────────────────────────────────────────────────────────────
    # Export helpers (called from API endpoints)
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    async def export_doctype(
        cls,
        grunt_app: Any,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        fmt: str = "csv",
        limit: int = 10_000,
    ) -> tuple[bytes, str]:
        """Export documents of *doctype* via the io exporter registry.

        Returns ``(file_bytes, filename)``.
        """
        from grunt.core.io.exporters.registry import get_exporter  # noqa: PLC0415

        exporter = get_exporter(fmt)
        if exporter is None:
            raise ValueError(f"Невідомий формат експорту: {fmt}")

        dt = await doctype_registry.get(doctype)
        exportable = [f for f in dt.fields if f.fieldtype not in _SKIP_FIELDTYPES]
        if fields:
            exportable = [f for f in exportable if f.fieldname in fields]

        rows = await grunt_app.get_list(
            doctype,
            filters=filters,
            fields=[f.fieldname for f in exportable],
            limit=limit,
        )

        content = await exporter.export(doctype, rows, exportable)
        return content, exporter.filename(doctype)

    @classmethod
    async def download_template(
        cls,
        doctype: str,
        *,
        fmt: str = "csv",
    ) -> tuple[bytes, str]:
        """Return an empty import template (headers only) for *doctype*."""
        from grunt.core.io.exporters.registry import get_exporter  # noqa: PLC0415

        exporter = get_exporter(fmt)
        if exporter is None:
            raise ValueError(f"Невідомий формат: {fmt}")

        dt = await doctype_registry.get(doctype)
        exportable = [f for f in dt.fields if f.fieldtype not in _SKIP_FIELDTYPES]
        content = await exporter.export(doctype, [], exportable)
        filename = f"{doctype.lower()}_template.{exporter.file_extension}"
        return content, filename
