"""Virtual DocType controller — DocType reads from grunt_meta_doctype."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select

from grunt.core.db.system_tables import GruntMetaDoctype
from grunt.core.metadata.virtual import VirtualDocType


def _row_to_doc(row: GruntMetaDoctype) -> dict[str, Any]:
    data: dict[str, Any] = row.data or {}
    return {
        "id": row.id,
        "name": row.name,
        "label": data.get("label", row.name),
        "module": row.module,
        "is_child": data.get("is_child", False),
        "is_virtual": data.get("is_virtual", False),
        "is_singleton": data.get("is_singleton", False),
        "is_submittable": data.get("is_submittable", False),
        "track_changes": data.get("track_changes", False),
        "autoname": data.get("autoname"),
        "title_field": data.get("title_field"),
        "image_field": data.get("image_field"),
        "default_view": data.get("default_view"),
        "table_name": data.get("table_name"),
        "search_fields": data.get("search_fields"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "modified_at": row.modified_at.isoformat() if row.modified_at else None,
    }


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

        stmt_count = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(stmt_count)).scalar() or 0

        col = GruntMetaDoctype.name
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
