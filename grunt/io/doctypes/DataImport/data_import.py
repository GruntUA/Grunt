import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import grunt
from grunt import _, log
from grunt.document.base import Document
from grunt.io.exporters.registry import get_exporter
from grunt.io.importers.registry import get_importer_for_file


class DataImport(Document):
    """DocType controller for DataImport."""

    async def get_import_preview(self) -> dict[str, Any]:
        """Extract headers and first 5 data rows for column mapping."""
        file_path, file_name = await self._resolve_file_path()
        data = self._read_file(file_path, file_name, limit=6)  # header + 5 rows
        dt = await self.grunt.get_meta(self.doctype_name)
        if dt is None:
            from grunt.errors import not_found

            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": self.doctype_name})

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
                {
                    "fieldname": f.fieldname,
                    "label": f.label,
                    "fieldtype": f.fieldtype,
                    "required": f.required,
                }
                for f in dt.get_physical_fields()
            ],
        }

    async def run(self) -> None:
        """Execute the import process (or dry-run validation)."""
        self.status = "In Progress"
        await self.session.commit()

        try:
            file_path, file_name = await self._resolve_file_path()
        except FileNotFoundError as exc:
            self.status = "Failed"
            self.error_log = json.dumps([{"row": 0, "error": str(exc)}])
            await self.session.commit()
            return

        all_rows = self._read_file(file_path, file_name)
        if not all_rows:
            self.status = "Failed"
            self.error_log = json.dumps([{"row": 0, "error": "File is empty"}])
            await self.session.commit()
            return

        headers = [str(h) if h is not None else "" for h in all_rows[0]]
        rows = all_rows[1:]

        mapping: dict[str, str] = self.mapping or {}
        if isinstance(mapping, str):
            mapping = json.loads(mapping) if mapping else {}

        # Load required fields for dry-run validation
        dt = await self.grunt.get_meta(self.doctype_name)
        if dt is None:
            self.status = "Failed"
            self.error_log = json.dumps(
                [
                    {
                        "row": 0,
                        "error": _("DocType “%(doctype)s” not found")
                        % {"doctype": self.doctype_name},
                    }
                ]
            )
            await self.session.commit()
            return
        required_fields = {f.fieldname for f in dt.get_required_fields()}
        mapped_dt_fields = set(mapping.values())

        total = len(rows)
        processed = 0
        errors: list[dict[str, Any]] = []

        self.total_rows = total
        await self.session.commit()

        for idx, row_data in enumerate(rows):
            row_num = idx + 2  # 1-based, accounting for header row
            try:
                row_dict = dict(
                    zip(headers, [str(v) if v is not None else "" for v in row_data], strict=False)
                )
                doc_data: dict[str, Any] = {}
                for file_col, dt_field in mapping.items():
                    if dt_field and file_col in row_dict:
                        doc_data[dt_field] = row_dict[file_col]

                if self.dry_run:
                    # Validate required fields are present and non-empty
                    if not self.skip_required_validation:
                        missing = [
                            f
                            for f in required_fields
                            if f in mapped_dt_fields and not doc_data.get(f)
                        ]
                        if missing:
                            raise ValueError(
                                _("Required fields are missing or empty: %(fields)s")
                                % {"fields": ", ".join(missing)}
                            )
                    # Validate update key exists when updating
                    if self.import_type == "Update Existing":
                        key = self.update_key
                        if not key:
                            raise ValueError(_("The update key is not specified"))
                        if not doc_data.get(key):
                            raise ValueError(
                                _("The key value “%(key)s” is missing in the row") % {"key": key}
                            )
                else:
                    if self.import_type == "Update Existing":
                        key = self.update_key
                        if not key:
                            raise ValueError(_("The update key is not specified"))
                        key_value = doc_data.get(key)
                        if not key_value:
                            raise ValueError(
                                _("The key value “%(key)s” is missing in the row") % {"key": key}
                            )
                        existing = await self.grunt.get_list(
                            self.doctype_name, filters={key: key_value}, limit=1
                        )
                        skip_req = bool(self.skip_required_validation)
                        if existing:
                            await self.grunt.save_doc(
                                self.doctype_name,
                                existing[0]["name"],
                                doc_data,
                                ignore_required=skip_req,
                            )
                        else:
                            raise ValueError(
                                _("Document with %(key)s=%(value)s not found")
                                % {"key": key, "value": key_value}
                            )
                    else:
                        await self.grunt.new_doc(
                            self.doctype_name,
                            doc_data,
                            ignore_required=bool(self.skip_required_validation),
                        )

                processed += 1
            except Exception as exc:
                errors.append({"row": row_num, "error": str(exc)})

            if idx % 10 == 0:
                self.error_count = len(errors)
                self.error_log = json.dumps(errors)
                await self.publish_progress(processed, total)

        self.status = (
            "Success" if not errors else ("Partial Success" if processed > 0 else "Failed")
        )
        self.total_rows = total
        self.processed_rows = processed
        self.error_count = len(errors)
        self.error_log = json.dumps(errors)
        await self.session.commit()

        try:
            from grunt.api.v1.ws import manager

            await manager.broadcast_doc(
                "DataImport",
                str(self.id),
                "doc_change",
                {
                    "source": "import",
                    "status": self.status,
                    "processed_rows": self.processed_rows,
                    "total_rows": self.total_rows,
                    "error_count": self.error_count,
                    "error_log": self.error_log,
                },
            )
        except Exception:
            log.exception("suppressed_error")

    async def _resolve_file_path(self) -> tuple[Path, str]:
        """Resolve the attached file reference to its blob's path and file name.

        Only resolves through a real `File` document + the storage
        backend - `self.file` is a plain string field an authenticated
        user (anyone with create rights on DataImport) fully controls.
        Treating it as a raw filesystem path (as this used to, via
        `Path(self.file).exists()`) is a path-traversal / arbitrary local
        file read: `{"file": "/etc/passwd"}` (or any other server-local
        path readable by the app process) would be "imported" and its
        contents surfaced back through get_import_preview()'s headers/rows.
        """
        file_id = parse_qs(urlparse(self.file).query).get("file_id", [None])[0]
        if file_id:
            doc = await self.grunt.find_doc("File", file_id)
            if doc and doc.get("content_hash"):
                from grunt.storage import get_storage_backend

                path = get_storage_backend().path(doc["content_hash"])
                if path.exists():
                    # Blobs carry no extension - the importer goes by the name.
                    return path, doc["file_name"]

        raise FileNotFoundError(f"Import file not found: {self.file}")

    @staticmethod
    def _read_file(file_path: Path, file_name: str, limit: int | None = None) -> list[list[Any]]:
        """Read CSV or XLSX file via the io importer registry."""
        imp = get_importer_for_file(file_name)
        if imp is None:
            raise ValueError(
                _("Unsupported file format: %(format)s") % {"format": Path(file_name).suffix}
            )
        return imp.read(file_path, limit=limit)

    # Export helpers (called from API endpoints)

    @classmethod
    async def export_doctype(
        cls,
        grunt: Any,
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
        exporter = get_exporter(fmt)
        if exporter is None:
            raise ValueError(_("Unknown export format: %(format)s") % {"format": fmt})

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise ValueError(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        exportable = dt.get_physical_fields()
        if fields:
            exportable = [f for f in exportable if f.fieldname in fields]

        rows = await grunt.get_list(
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
        exporter = get_exporter(fmt)
        if exporter is None:
            raise ValueError(_("Unknown format: %(format)s") % {"format": fmt})

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise ValueError(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        exportable = dt.get_physical_fields()
        content = await exporter.export(doctype, [], exportable)
        filename = f"{doctype.lower()}_template.{exporter.file_extension}"
        return content, filename
