"""Full-text search index service.

Maintains a ``grunt_search_index`` table (one row per indexed document) and
queries it with the database's native full-text engine - SQLite FTS5,
PostgreSQL ``tsvector`` or MySQL ``FULLTEXT``, chosen by the dialect (see
:mod:`grunt.db.dialects.fulltext`). Where the engine can't serve a query
(FTS5 unavailable, nothing to tokenize) search falls back to ``LIKE``.

All engines get the same query semantics (see :mod:`grunt.search.terms`):
every term must match, each term matches as a word *prefix*
(``петр`` → «Петренко»), results are ranked with title hits first.

The index is updated on every document save/delete through direct calls from
the document pipeline (no hook overhead, always consistent).
"""

import re
from itertools import islice
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt import log
from grunt.db.dialects import Dialect, dialect_for
from grunt.db.dialects.fulltext import FullText, FullTextSpec
from grunt.document.meta import Meta
from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry
from grunt.search.terms import match_columns
lazy from grunt.metadata.doctype import DocType

_INDEX_TABLE_NAME = "grunt_search_index"
_INDEX_META = MetaData()
_CHUNK = 500

# Table definition (created via DDL, not Alembic - it's a framework table)
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
_doctype_index = Index("grunt_search_idx_doctype", _search_index_table.c.doctype)

_FULLTEXT = FullTextSpec(
    name="grunt_search",
    table=_search_index_table,
    key="idx_id",
    title="title",
    label="doc_name",
    content="content_raw",
)


def is_indexable(dt: DocType) -> bool:
    """True if *dt*'s documents belong in the global search index."""
    return not (dt.is_child or dt.is_virtual or dt.is_log) and dt.in_global_search


def _build_content(dt: DocType, doc: dict[str, Any]) -> str:
    """Return a whitespace-joined string of all searchable field values."""
    parts: list[str] = []

    # Always include name
    name = doc.get("name") or ""
    if name:
        parts.append(str(name))

    # Title field
    title_field = dt.title_field or "name"
    title = doc.get(title_field) or ""
    if title and str(title) not in parts:
        parts.append(str(title))

    # All other text-ish fields

    for field in Meta(dt).get_searchable_fields():
        val = doc.get(field.fieldname)
        if val is None or val is False or val == "":
            continue
        # Strip HTML tags from RichText
        text_val = re.sub(r"<[^>]+>", " ", str(val)).strip()
        if text_val and text_val not in parts:
            parts.append(text_val)

    return " ".join(parts)


class SearchIndexService:
    def __init__(self) -> None:
        self._fulltext_by_dialect: dict[Dialect, FullText] = {}

    def _fulltext(self, bind: Any) -> FullText:
        """The full-text engine for *bind*'s backend (one per dialect, kept)."""
        dialect = dialect_for(bind)
        if (ft := self._fulltext_by_dialect.get(dialect)) is None:
            ft = self._fulltext_by_dialect[dialect] = dialect.fulltext(_FULLTEXT)
        return ft

    async def ensure_table(self, engine: AsyncEngine) -> None:
        """Create grunt_search_index, its indexes and the full-text engine's objects."""
        async with engine.begin() as conn:
            await conn.run_sync(_INDEX_META.create_all, checkfirst=True)
            # create_all adds indexes only together with a new table
            await conn.run_sync(lambda c: _doctype_index.create(c, checkfirst=True))
        await self._fulltext(engine).ensure(engine)

    async def empty(self, conn: Any) -> None:
        """Delete every index entry, the full-text engine's included (tests)."""
        await conn.execute(delete(_search_index_table))
        await self._fulltext(conn).clear(conn)

    async def drop_table(self, engine: AsyncEngine) -> None:
        """Remove the index table and the full-text engine's objects (tests start clean)."""
        await self._fulltext(engine).drop(engine)
        async with engine.begin() as conn:
            await conn.run_sync(_INDEX_META.drop_all, checkfirst=True)

    async def index_document(
        self,
        session: AsyncSession,
        doctype: str,
        dt: DocType,
        doc: dict[str, Any],
    ) -> None:
        """Upsert a document into the search index."""
        if not is_indexable(dt):
            return

        doc_id = str(doc.get("name") or "")
        if not doc_id:
            return

        title_field = dt.title_field or "name"
        row = {
            "idx_id": f"{doctype}:{doc_id}",
            "doctype": doctype,
            "doc_id": doc_id,
            "doc_name": doc_id,
            "title": str(doc.get(title_field) or doc_id),
            "module": dt.module or "",
            "content_raw": _build_content(dt, doc),
            "updated_at": func.now(),
        }
        try:
            await session.execute(dialect_for(session).upsert(_search_index_table, row, ["idx_id"]))
            await self._fulltext(session).write(session, [row])
        except Exception as e:
            log.warning("search_index.index_failed", doctype=doctype, doc_id=doc_id, error=str(e))

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
            await self._fulltext(session).delete(session, [idx_id])
        except Exception:
            log.warning("search_index.remove_failed", doctype=doctype, doc_id=doc_id)

    async def remove_documents(
        self,
        session: AsyncSession,
        doctype: str,
        doc_ids: list[str],
        chunk_size: int = _CHUNK,
    ) -> None:
        """Remove multiple documents from the search index, chunked to avoid large IN lists."""
        if not doc_ids:
            return
        try:
            fulltext = self._fulltext(session)
            it = iter(doc_ids)
            while chunk := list(islice(it, chunk_size)):
                idx_ids = [f"{doctype}:{doc_id}" for doc_id in chunk]
                await session.execute(
                    delete(_search_index_table).where(_search_index_table.c.idx_id.in_(idx_ids))
                )
                await fulltext.delete(session, idx_ids)
        except Exception:
            log.warning("search_index.remove_bulk_failed", doctype=doctype, count=len(doc_ids))

    async def remove_doctype(self, session: AsyncSession, doctype: str) -> int:
        """Drop every index entry of *doctype*. Returns the number removed."""
        t = _search_index_table
        idx_ids = list(
            (await session.execute(select(t.c.idx_id).where(t.c.doctype == doctype))).scalars()
        )
        if not idx_ids:
            return 0
        await session.execute(delete(t).where(t.c.doctype == doctype))
        fulltext = self._fulltext(session)
        it = iter(idx_ids)
        while chunk := list(islice(it, _CHUNK)):
            await fulltext.delete(session, chunk)
        log.info("search_index.doctype_removed", doctype=doctype, count=len(idx_ids))
        return len(idx_ids)

    async def purge_excluded(self, session: AsyncSession, doctypes: list[DocType]) -> int:
        """Remove entries of DocTypes that are no longer indexable (or no longer
        exist) - e.g. after ``in_global_search`` was switched off or a DocType
        became ``is_log``. Returns the number of entries removed."""
        keep = {dt.name for dt in doctypes if is_indexable(dt)}
        t = _search_index_table
        indexed = (await session.execute(select(t.c.doctype).distinct())).scalars()
        removed = 0
        for name in [n for n in indexed if n not in keep]:
            removed += await self.remove_doctype(session, name)
        return removed

    async def search(
        self,
        session: AsyncSession,
        q: str,
        limit: int = 30,
        doctype: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the index, best matches first.

        Every term of *q* must match (as a word prefix on the full-text
        engines, as a substring on the ``LIKE`` fallback).
        """
        q = q.strip()
        if not q:
            return []
        try:
            return await self._search(session, q, limit, doctype)
        except Exception:
            log.exception("search_index.search_failed", q=q)
            return []

    async def _search(
        self, session: AsyncSession, q: str, limit: int, doctype: str | None
    ) -> list[dict[str, Any]]:
        t = _search_index_table
        base = select(t.c.idx_id, t.c.doctype, t.c.doc_id, t.c.doc_name, t.c.title, t.c.module)
        if doctype:
            base = base.where(t.c.doctype == doctype)

        stmt = self._fulltext(session).match(session, base, q)
        if stmt is None:
            # Fallback: every term as a substring of name / title / content.
            condition = match_columns(q, [t.c.content_raw, t.c.doc_name, t.c.title], session)
            if condition is None:
                return []
            stmt = base.where(condition)

        rows = (await session.execute(stmt.limit(limit))).fetchall()
        return [dict(r._mapping) for r in rows]

    async def reindex_all(
        self,
        session: AsyncSession,
        engine: AsyncEngine,
    ) -> int:
        """Rebuild the entire search index from all DocType tables. Returns count."""
        await session.execute(delete(_search_index_table))
        await self._fulltext(session).clear(session)

        count = 0
        all_doctypes = await doctype_registry.list_all()
        for dt in all_doctypes:
            if not is_indexable(dt):
                continue
            try:
                table = compile_doctype_to_table(dt)
                result = await session.execute(select(table))
                for row in result.fetchall():
                    doc = dict(row._mapping)
                    await self.index_document(session, dt.name, dt, doc)
                    count += 1
            except Exception:
                log.warning("search_index.reindex_doctype_failed", doctype=dt.name)

        await session.flush()
        return count


search_index_service = SearchIndexService()
