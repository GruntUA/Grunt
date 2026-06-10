"""Virtual DocType controller — DocType reads from grunt_meta_doctype."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select

from grunt.db.system_tables import GruntMetaDoctype
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.metadata.virtual import VirtualDocType


def _row_to_doc(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert grunt_meta_doctype row to DocType model data."""
    data: dict[str, Any] = dict(row.get("data") or {})
    data["name"] = row["name"]
    data["module"] = row["module"]
    created_at = row.get("created_at")
    modified_at = row.get("modified_at")
    data["created_at"] = created_at.isoformat() if created_at else None
    data["modified_at"] = modified_at.isoformat() if modified_at else None
    return data


def _expand_status_config(data: dict[str, Any]) -> None:
    """Expand status_config → status_field + status_indicators for the form."""
    sc = data.get("status_config")
    if sc and isinstance(sc, dict):
        data["status_field"] = sc.get("field", "")
        data["status_indicators"] = sc.get("indicators", [])
    else:
        data.setdefault("status_field", "")
        data.setdefault("status_indicators", [])


def _collapse_status_fields(data: dict[str, Any]) -> None:
    """Convert status_field + status_indicators → status_config before saving."""
    status_field = data.pop("status_field", None)
    status_indicators = data.pop("status_indicators", None)
    if status_field:
        data["status_config"] = {
            "field": status_field,
            "indicators": status_indicators or [],
        }
    elif status_field is not None:
        # Explicit empty string means clear the status config
        data["status_config"] = None


class DocTypeController(VirtualDocType):
    """Serves DocType list/get from grunt_meta_doctype (single source of truth)."""

    def _session(self):
        from grunt.app import grunt

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
        data = _row_to_doc(row) if row else {}
        _expand_status_config(data)
        return data

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create a new DocType."""
        _collapse_status_fields(data)
        from grunt.app import grunt
        from grunt.metadata.compiler import sync_table
        from grunt.metadata.scaffold import export_doctype_files

        dt = DocType(**data)
        session = self._session()
        engine = grunt._require_engine()

        if dt.name in doctype_registry._doctypes:
            raise ValueError(f"DocType '{dt.name}' already exists")

        await doctype_registry.register(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files if applicable
        export_doctype_files(dt, app_name=dt.app or None)

        result = dt.model_dump()
        _expand_status_config(result)
        return result

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Update an existing DocType."""
        _collapse_status_fields(data)
        from grunt.app import grunt
        from grunt.metadata.compiler import sync_table
        from grunt.metadata.scaffold import export_doctype_files

        dt = DocType(**data)
        session = self._session()
        engine = grunt._require_engine()

        await doctype_registry.update(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files
        export_doctype_files(dt, app_name=dt.app or None)

        result = dt.model_dump()
        _expand_status_config(result)
        return result

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete a DocType."""
        session = self._session()
        result = await session.execute(
            select(GruntMetaDoctype.c.name).where(GruntMetaDoctype.c.name == doc_id)
        )
        name = result.scalar_one_or_none() or doc_id
        await doctype_registry.delete(name, session)
