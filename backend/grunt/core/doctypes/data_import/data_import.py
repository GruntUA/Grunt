import csv
import json
from pathlib import Path
from typing import Any

import openpyxl
import structlog

from grunt.core.document.base import Document
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()


class DataImport(Document):
    """DocType controller for DataImport."""

    async def get_preview(self) -> dict[str, Any]:
        """Extract headers and first 5 rows for mapping."""
        file_path = Path(self.file)
        if not file_path.exists():
            # Handle the case where 'file' might be a relative path or URL
            # If it's a URL from /api/v1/files/, we need to resolve it to a path
            if self.file.startswith("/api/v1/files/"):
                file_id = self.file.split("/")[-1]
                try:
                    doc = await self.grunt.get_doc("File", file_id)
                    file_path = Path(doc.path)
                except Exception as err:
                    raise FileNotFoundError(f"File record not found for {file_id}") from err
            else:
                raise FileNotFoundError(f"Import file not found: {self.file}")

        data = self._read_file(file_path, limit=5)
        dt = await doctype_registry.get(self.doctype_name)

        headers = data[0] if data else []
        suggestions = {}
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
                {"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype}
                for f in dt.fields
                if f.fieldtype not in ("Section", "Column", "Tab", "Table", "MultiLink")
            ],
        }

    async def run(self):
        """Execute the import process."""
        self.status = "In Progress"
        await self.session.commit()

        file_path = Path(self.file)
        if self.file.startswith("/api/v1/files/"):
            file_id = self.file.split("/")[-1]
            try:
                doc = await self.grunt.get_doc("File", file_id)
                file_path = Path(doc.path)
            except Exception:
                pass

        all_rows = self._read_file(file_path)
        if not all_rows:
            self.status = "Failed"
            self.error_log = json.dumps([{"row": 0, "error": "File is empty"}])
            await self.session.commit()
            return

        headers = all_rows[0]
        rows = all_rows[1:]

        mapping = self.mapping
        if isinstance(mapping, str):
            mapping = json.loads(mapping)

        total = len(rows)
        processed = 0
        errors = []

        for idx, row_data in enumerate(rows):
            try:
                row_dict = dict(zip(headers, row_data, strict=False))
                doc_data = {}
                for file_col, dt_field in mapping.items():
                    if dt_field and file_col in row_dict:
                        doc_data[dt_field] = row_dict[file_col]

                if self.dry_run:
                    # For dry run, we just try to initialize it without saving
                    # but new_doc saves. We might need a validate-only helper.
                    # For now, let's skip validation in dry run or implement a check.
                    pass
                else:
                    if self.import_type == "Update Existing":
                        key = self.update_key
                        # Find existing
                        existing = await self.grunt.get_list(
                            self.doctype_name, filters={key: doc_data[key]}, limit=1
                        )
                        if existing:
                            await self.grunt.save_doc(
                                self.doctype_name, existing[0]["id"], doc_data
                            )
                        else:
                            raise ValueError(f"Document with {key}={doc_data[key]} not found")
                    else:
                        await self.grunt.new_doc(self.doctype_name, doc_data)

                processed += 1
            except Exception as e:
                errors.append({"row": idx + 2, "error": str(e)})

            if idx % 10 == 0:
                # Update progress
                await self._update_db_progress(processed, len(errors), errors)

        self.status = (
            "Success" if not errors else ("Partial Success" if processed > 0 else "Failed")
        )
        self.total_rows = total
        self.processed_rows = processed
        self.error_count = len(errors)
        self.error_log = json.dumps(errors)
        await self.session.commit()

    async def _update_db_progress(self, processed: int, error_count: int, error_log: list):
        self.processed_rows = processed
        self.error_count = error_count
        self.error_log = json.dumps(error_log)
        await self.session.commit()

    def _read_file(self, file_path: Path, limit: int | None = None) -> list[list[Any]]:
        if file_path.suffix.lower() == ".xlsx":
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            ws = wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if limit and i >= limit:
                    break
                rows.append(list(row))
            return rows
        else:
            with open(file_path, encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = []
                for i, row in enumerate(reader):
                    if limit and i >= limit:
                        break
                    rows.append(row)
                return rows
