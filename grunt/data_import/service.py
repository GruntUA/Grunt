from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import grunt
lazy from grunt.document.api import documents


class DataImportService:
    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self._session = session
        self._engine = engine

    async def run_import(self, data_import_id: str, user: str) -> None:
        """Load the DataImport document and execute the import as *user* (an email)."""
        async with grunt.context(self._session, self._engine, user):
            doc = await documents.get_doc_instance("DataImport", data_import_id)
            await doc.run()
