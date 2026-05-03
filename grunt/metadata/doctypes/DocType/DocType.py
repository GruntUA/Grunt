"""Virtual DocType controller — DocType reads from grunt_meta_doctype."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select

from grunt.db.system_tables import GruntMetaDoctype
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.metadata.virtual import VirtualDocType


def _row_to_doc(row: GruntMetaDoctype) -> dict[str, Any]:
    """Convert GruntMetaDoctype row to DocType model data."""
    # Data is the primary source, row columns (name, module) are for indexing/querying
    data: dict[str, Any] = row.data or {}
    data["id"] = row.id
    data["name"] = row.name
    data["module"] = row.module
    data["created_at"] = row.created_at.isoformat() if row.created_at else None
    data["modified_at"] = row.modified_at.isoformat() if row.modified_at else None
    return data


class DocTypeController(VirtualDocType):
    """Serves DocType list/get from grunt_meta_doctype (single source of truth)."""

    def _session(self):
        from grunt.app import grunt  # noqa: PLC0415

        return grunt._require_session()

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "asc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        session = self._session()
        stmt = select(GruntMetaDoctype)

        if search:
            stmt = stmt.where(GruntMetaDoctype.name.ilike(f"%{search}%"))

        for key, val in (filters or {}).items():
            if key == "module":
                stmt = stmt.where(GruntMetaDoctype.module == val)
            elif key == "name":
                stmt = stmt.where(GruntMetaDoctype.name.ilike(f"%{val}%"))
            elif key == "is_child":
                # JSON filtering
                stmt = stmt.where(GruntMetaDoctype.data["is_child"].as_boolean() == bool(val))

        # Count
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        # Sort & Paginate
        # Default to 'name' as GruntMetaDoctype doesn't have all DocType fields as top-level columns
        col = getattr(GruntMetaDoctype, sort_by if hasattr(GruntMetaDoctype, sort_by) else "name")
        stmt = stmt.order_by(col.desc() if sort_order.lower() == "desc" else col.asc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        rows = (await session.execute(stmt)).scalars().all()

        return {
            "data": [_row_to_doc(r) for r in rows],
            "meta": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
            },
        }

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        session = self._session()
        row = await session.get(GruntMetaDoctype, doc_id)
        if not row:
            result = await session.execute(
                select(GruntMetaDoctype).where(GruntMetaDoctype.name == doc_id)
            )
            row = result.scalar_one_or_none()
        return _row_to_doc(row) if row else {}

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create a new DocType."""
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.metadata.compiler import sync_table  # noqa: PLC0415
        from grunt.metadata.scaffold import export_doctype_files  # noqa: PLC0415

        dt = DocType(**data)
        session = self._session()
        engine = grunt._require_engine()

        if dt.name in doctype_registry._doctypes:
            from grunt.metadata.virtual import VirtualDocType  # noqa: PLC0415

            raise ValueError(f"DocType '{dt.name}' already exists")

        await doctype_registry.register(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files if applicable
        export_doctype_files(dt, app_name=dt.app or None)

        return dt.model_dump()

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Update an existing DocType."""
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.metadata.compiler import sync_table  # noqa: PLC0415
        from grunt.metadata.scaffold import export_doctype_files  # noqa: PLC0415

        dt = DocType(**data)
        session = self._session()
        engine = grunt._require_engine()

        await doctype_registry.update(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files
        export_doctype_files(dt, app_name=dt.app or None)

        return dt.model_dump()

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete a DocType."""
        # Find name first if doc_id is UUID
        session = self._session()
        row = await session.get(GruntMetaDoctype, doc_id)
        name = row.name if row else doc_id

        await doctype_registry.delete(name, session)
