from __future__ import annotations

import io
import pandas as pd
import structlog
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine

from grunt.core.auth.models import GruntUser
from grunt.core.document.service import DocumentService
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

class DataImportService:
    """Service for bulk data import from CSV/XLSX."""

    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self.session = session
        self.engine = engine
        self.doc_service = DocumentService(session, engine)

    async def run_import(self, data_import_id: str, user: GruntUser) -> None:
        """Execute the import process for a specific DataImport document."""
        # 1. Fetch DataImport settings
        try:
            doc = await self.doc_service.get_document("DataImport", data_import_id, user)
        except Exception as e:
            logger.error("data_import.not_found", id=data_import_id, error=str(e))
            return

        if doc["status"] != "Pending":
            logger.warning("data_import.already_processed", id=data_import_id, status=doc["status"])
            return

        # 2. Update status to In Progress
        await self.doc_service.update_document(
            "DataImport", data_import_id, {"status": "In Progress"}, user
        )
        await self.session.commit()

        reference_doctype = doc["reference_doctype"]
        import_type = doc.get("import_type", "Upsert")
        file_content = doc["import_file"] # Assuming raw content or path

        try:
            # 3. Parse File
            df = self._parse_file(file_content)
            total_rows = len(df)
            
            await self.doc_service.update_document(
                "DataImport", data_import_id, {"total_rows": total_rows, "processed_rows": 0}, user
            )
            await self.session.commit()

            # 4. Process Rows
            processed = 0
            errors = []

            for index, row in df.iterrows():
                row_dict = row.to_dict()
                # Clean up NaN
                row_dict = {k: v for k, v in row_dict.items() if pd.notna(v)}

                try:
                    if import_type == "Insert New Records":
                        await self.doc_service.create_document(reference_doctype, row_dict, user)
                    elif import_type == "Update Existing Records":
                        doc_id = row_dict.get("id") or row_dict.get("name")
                        if not doc_id:
                            raise ValueError("Missing 'id' or 'name' for update")
                        await self.doc_service.update_document(reference_doctype, doc_id, row_dict, user)
                    else: # Upsert
                        doc_id = row_dict.get("id") or row_dict.get("name")
                        if doc_id:
                            try:
                                await self.doc_service.update_document(reference_doctype, doc_id, row_dict, user)
                            except Exception:
                                await self.doc_service.create_document(reference_doctype, row_dict, user)
                        else:
                            await self.doc_service.create_document(reference_doctype, row_dict, user)
                    
                    processed += 1
                except Exception as e:
                    errors.append(f"Row {index + 1}: {str(e)}")

                # Update progress every 10 rows
                if processed % 10 == 0:
                    await self.doc_service.update_document(
                        "DataImport", data_import_id, {"processed_rows": processed}, user
                    )
                    await self.session.commit()

            # 5. Finalize
            final_status = "Completed" if not errors else "Failed"
            if processed > 0 and errors:
                final_status = "Completed" # Partial success? Or keep Failed? 
                # Frappe usually marks as Failed if any row fails, or has a separate Partial 
            
            await self.doc_service.update_document(
                "DataImport", 
                data_import_id, 
                {
                    "status": final_status, 
                    "processed_rows": processed,
                    "error_log": "\n".join(errors) if errors else None
                }, 
                user
            )
            await self.session.commit()
            logger.info("data_import.finished", id=data_import_id, status=final_status)

        except Exception as e:
            logger.error("data_import.failed", id=data_import_id, error=str(e))
            await self.doc_service.update_document(
                "DataImport", 
                data_import_id, 
                {"status": "Failed", "error_log": f"Critical Error: {str(e)}"}, 
                user
            )
            await self.session.commit()

    def _parse_file(self, content: str | bytes) -> pd.DataFrame:
        """Parse CSV or XLSX content into a pandas DataFrame."""
        if isinstance(content, str):
            # If it's a path
            if content.endswith(".csv"):
                return pd.read_csv(content)
            elif content.endswith(".xlsx"):
                return pd.read_excel(content)
            else:
                # Assume it's CSV content
                return pd.read_csv(io.StringIO(content))
        else:
            # Bytes
            return pd.read_csv(io.BytesIO(content))
