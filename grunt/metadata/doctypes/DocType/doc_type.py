"""Virtual DocType controller — DocType reads from grunt_meta_doctype."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

from sqlalchemy import func, select

from grunt.db.system_tables import GruntMetaDoctype
from grunt.metadata.compiler import get_table_name
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.metadata.virtual import VirtualDocType


def _row_to_doc(row: RowMapping) -> dict[str, Any]:
    """Convert grunt_meta_doctype row to DocType model data."""
    data: dict[str, Any] = dict(row.get("data") or {})
    data["name"] = row["name"]
    data["module"] = row["module"]
    # Show the resolved physical table name (override, or the computed default)
    # so the read-only "Назва таблиці" field isn't a dead empty box in the form.
    # Virtual DocTypes have no table of their own — leave it blank.
    if not data.get("is_virtual"):
        data["table_name"] = data.get("table_name") or get_table_name(row["module"], row["name"])
    created_at = row.get("created_at")
    modified_at = row.get("modified_at")
    data["created_at"] = created_at.isoformat() if created_at else None
    data["modified_at"] = modified_at.isoformat() if modified_at else None
    return data


def _drop_default_table_name(dt: DocType) -> None:
    """Don't persist ``table_name`` when it just equals the computed default —
    it's surfaced read-only in the form and would round-trip back as a
    spurious override that goes stale if the DocType is ever renamed."""
    if dt.table_name and dt.table_name == get_table_name(dt.module, dt.name):
        dt.table_name = None


class DocTypeController(VirtualDocType):
    """Serves DocType list/get from grunt_meta_doctype (single source of truth)."""

    def _session(self):
        import grunt

        return grunt.get_session()

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
            stmt = stmt.where(
                GruntMetaDoctype.c.name.ilike(f"%{search}%")
                | GruntMetaDoctype.c.data["label"].as_string().ilike(f"%{search}%")
            )

        for key, val in (filters or {}).items():
            if key == "module":
                stmt = stmt.where(GruntMetaDoctype.c.module == val)
            elif key == "name":
                stmt = stmt.where(GruntMetaDoctype.c.name.ilike(f"%{val}%"))
            elif key == "is_child":
                stmt = stmt.where(GruntMetaDoctype.c.data["is_child"].as_boolean() == bool(val))

        # Count
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        # Sort & Paginate
        col_name = sort_by if sort_by in GruntMetaDoctype.c else "name"
        col = GruntMetaDoctype.c[col_name]
        stmt = stmt.order_by(col.desc() if sort_order.lower() == "desc" else col.asc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        rows = (await session.execute(stmt)).mappings().all()

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
        result = await session.execute(
            select(GruntMetaDoctype).where(GruntMetaDoctype.c.name == doc_id)
        )
        row = result.mappings().one_or_none()
        return _row_to_doc(row) if row else {}

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create a new DocType."""
        import grunt
        from grunt.metadata.compiler import sync_table
        from grunt.metadata.scaffold import export_doctype_files

        dt = DocType(**data)
        _drop_default_table_name(dt)
        session = self._session()
        engine = grunt.get_engine()

        if await doctype_registry.get_or_none(dt.name) is not None:
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
        import grunt
        from grunt.metadata.compiler import sync_table
        from grunt.metadata.scaffold import export_doctype_files

        dt = DocType(**data)
        _drop_default_table_name(dt)
        session = self._session()
        engine = grunt.get_engine()

        await doctype_registry.update(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files
        export_doctype_files(dt, app_name=dt.app or None)

        return dt.model_dump()

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete a DocType."""
        session = self._session()
        result = await session.execute(
            select(GruntMetaDoctype.c.name).where(GruntMetaDoctype.c.name == doc_id)
        )
        name = result.scalar_one_or_none() or doc_id
        await doctype_registry.delete(name, session)
