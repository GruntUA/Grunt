from __future__ import annotations

from typing import TYPE_CHECKING, cast

import structlog

from grunt.app import grunt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


class DataImportService:
    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self._session = session
        self._engine = engine

    async def run_import(self, data_import_id: str, user: object) -> None:
        """Load the DataImport document and execute the import."""
        from grunt.core.doctypes.data_import.data_import import DataImport  # noqa: PLC0415

        async with grunt.context(self._session, self._engine, user):  # type: ignore[arg-type]
            doc = cast("DataImport", await grunt.get_doc("DataImport", data_import_id))
            await doc.run()
