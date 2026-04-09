"""Full-text search index service.

Maintains a ``grunt_search_index`` table with a ``tsvector`` column for
PostgreSQL.  On SQLite (dev) falls back to simple ``ILIKE`` search against
the stored raw text.

Index is updated on every document save/delete through direct calls from
DocumentService (no hook overhead, always consistent).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()

_INDEX_TABLE_NAME = "grunt_search_index"
_INDEX_META = MetaData()

# Table definition (created via DDL, not Alembic — it's a framework table)
_search_index_table = Table(
    _INDEX_TABLE_NAME,
    _INDEX_META,
    Column("idx_id", String(512), primary_key=True),  # "{doctype}:{doc_id}"
    Column("doctype", String(255), nullable=False),
    Column("doc_id", String(255), nullable=False),
    Column("doc_name", Text),
    Column("title", Text),
    Column("module", String(255)),
    Column("content_raw", Text),  # space-joined text for fallback
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

# Add GIN index for PG tsvector — created separately to handle non-PG engines
_PG_TSVECTOR_INDEX_SQL = text(
    "CREATE INDEX IF NOT EXISTS grunt_search_idx_ts "
    "ON grunt_search_index "
    "USING GIN (to_tsvector('simple', coalesce(content_raw, '')))"
)
_PG_DOCTYPE_INDEX_SQL = text(
    "CREATE INDEX IF NOT EXISTS grunt_search_idx_doctype ON grunt_search_index (doctype)"
)

_SKIP_FIELDTYPES = frozenset(
    [
        "Section",
        "Column",
        "Tab",
        "Table",
        "MultiLink",
        "Image",
        "Attach",
        "Signature",
        "Geolocation",
        "JSON",
        "Code",
    ]
)
_TEXT_FIELDTYPES = frozenset(
    [
        "Text",
        "LongText",
        "RichText",
        "Data",
        "Int",
        "Float",
        "Check",
        "Select",
        "Link",
        "Color",
    ]
)


def _build_content(dt: DocType, doc: dict[str, Any]) -> str:
    """Return a whitespace-joined string of all searchable field values."""
    parts: list[str] = []

    # Always include name
    name = doc.get("name") or doc.get("id") or ""
    if name:
        parts.append(str(name))

    # Title field
    title_field = dt.title_field or "name"
    title = doc.get(title_field) or ""
    if title and str(title) not in parts:
        parts.append(str(title))

    # All other text-ish fields
    for field in dt.fields:
        if field.fieldtype in _SKIP_FIELDTYPES:
            continue
        val = doc.get(field.fieldname)
        if val is None or val is False or val == "":
            continue
        # Strip HTML tags from RichText
        text_val = re.sub(r"<[^>]+>", " ", str(val)).strip()
        if text_val and text_val not in parts:
            parts.append(text_val)

    return " ".join(parts)


def _is_postgres(engine: AsyncEngine) -> bool:
    return engine.dialect.name == "postgresql"


class SearchIndexService:
    async def ensure_table(self, engine: AsyncEngine) -> None:
        """Create grunt_search_index table + indexes if they don't exist."""
        async with engine.begin() as conn:
            await conn.run_sync(
                _INDEX_META.create_all,
                checkfirst=True,
            )
            if _is_postgres(engine):
                await conn.execute(_PG_TSVECTOR_INDEX_SQL)
                await conn.execute(_PG_DOCTYPE_INDEX_SQL)

    async def index_document(
        self,
        session: AsyncSession,
        doctype: str,
        dt: DocType,
        doc: dict[str, Any],
    ) -> None:
        """Upsert a document into the search index."""
        if dt.is_child or dt.is_virtual:
            return

        doc_id = str(doc.get("id") or "")
        if not doc_id:
            return

        idx_id = f"{doctype}:{doc_id}"
        title_field = dt.title_field or "name"
        title = str(doc.get(title_field) or doc.get("name") or "")
        doc_name = str(doc.get("name") or doc_id)
        content_raw = _build_content(dt, doc)

        try:
            row = {
                "idx_id": idx_id,
                "doctype": doctype,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "title": title,
                "module": dt.module or "",
                "content_raw": content_raw,
                "updated_at": func.now(),
            }

            dialect = session.bind.dialect.name if session.bind else "sqlite"
            stmt: Any
            if dialect == "postgresql":
                stmt = (
                    pg_insert(_search_index_table)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=["idx_id"],
                        set_={k: v for k, v in row.items() if k != "idx_id"},
                    )
                )
            else:
                # SQLite: delete + insert (no native upsert for composite)
                await session.execute(
                    delete(_search_index_table).where(_search_index_table.c.idx_id == idx_id)
                )
                stmt = _search_index_table.insert().values(**row)

            await session.execute(stmt)
        except Exception:  # noqa: BLE001
            logger.warning("search_index.index_failed", doctype=doctype, doc_id=doc_id)

    async def remove_document(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
    ) -> None:
        """Remove a document from the search index."""
        idx_id = f"{doctype}:{doc_id}"
        try:
            await session.execute(
                delete(_search_index_table).where(_search_index_table.c.idx_id == idx_id)
            )
        except Exception:  # noqa: BLE001
            logger.warning("search_index.remove_failed", doctype=doctype, doc_id=doc_id)

    async def search(
        self,
        session: AsyncSession,
        q: str,
        limit: int = 30,
        doctype: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the index. Uses tsvector on PostgreSQL, ILIKE on SQLite."""
        q = q.strip()
        if not q:
            return []

        t = _search_index_table
        base = select(
            t.c.idx_id,
            t.c.doctype,
            t.c.doc_id,
            t.c.doc_name,
            t.c.title,
            t.c.module,
        )
        if doctype:
            base = base.where(t.c.doctype == doctype)

        dialect = session.bind.dialect.name if session.bind else "sqlite"

        try:
            if dialect == "postgresql":
                # Use plainto_tsquery — handles multi-word naturally
                ts_query = func.plainto_tsquery("simple", q)
                ts_vector = func.to_tsvector("simple", func.coalesce(t.c.content_raw, ""))
                stmt = (
                    base.where(ts_vector.op("@@")(ts_query))
                    .order_by(func.ts_rank(ts_vector, ts_query).desc())
                    .limit(limit)
                )
            else:
                # SQLite fallback: simple ILIKE on raw content + name
                pattern = f"%{q}%"
                stmt = base.where(
                    or_(
                        t.c.content_raw.ilike(pattern),
                        t.c.doc_name.ilike(pattern),
                        t.c.title.ilike(pattern),
                    )
                ).limit(limit)

            rows = (await session.execute(stmt)).fetchall()
            return [dict(r._mapping) for r in rows]

        except Exception:  # noqa: BLE001
            logger.exception("search_index.search_failed", q=q)
            return []

    async def reindex_all(
        self,
        session: AsyncSession,
        engine: AsyncEngine,
    ) -> int:
        """Rebuild the entire search index from all DocType tables. Returns count."""
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        # Clear index
        await session.execute(delete(_search_index_table))

        count = 0
        all_doctypes = await doctype_registry.list_all()
        for dt in all_doctypes:
            if dt.is_child or dt.is_virtual:
                continue
            try:
                table = compile_doctype_to_table(dt)
                result = await session.execute(select(table))
                for row in result.fetchall():
                    doc = dict(row._mapping)
                    await self.index_document(session, dt.name, dt, doc)
                    count += 1
            except Exception:  # noqa: BLE001
                logger.warning("search_index.reindex_doctype_failed", doctype=dt.name)

        await session.flush()
        return count


search_index_service = SearchIndexService()
