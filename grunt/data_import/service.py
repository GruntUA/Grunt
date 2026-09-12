from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.app import grunt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class DataImportService:
    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self._session = session
        self._engine = engine

    async def run_import(self, data_import_id: str, user: object) -> None:
        """Load the DataImport document and execute the import."""
        async with grunt.context(self._session, self._engine, user):  # type: ignore[arg-type]
            doc = await grunt.get_doc_instance("DataImport", data_import_id)
            await doc.run()
