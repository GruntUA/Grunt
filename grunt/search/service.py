"""Full-text search index service.

Maintains a ``grunt_search_index`` table (one row per indexed document) and
queries it with the database's native full-text engine:

* **SQLite** - a companion FTS5 table ``grunt_search_fts`` (unicode61
  tokenizer, 2/3-char prefix indexes, bm25 ranking). Its ``rowid`` is a
  stable 64-bit hash of ``idx_id``, so it survives ``VACUUM`` and needs no
  triggers. If FTS5 is unavailable, search falls back to ``LIKE``.
* **PostgreSQL** - GIN ``tsvector`` index, prefix ``tsquery``, ``ts_rank``.
* **MySQL** - native ``FULLTEXT`` in boolean mode.

All engines get the same query semantics (see :mod:`grunt.search.terms`):
every term must match, each term matches as a word *prefix*
(``петр`` → «Петренко»), results are ranked with title hits first.

The index is updated on every document save/delete through direct calls from
the document pipeline (no hook overhead, always consistent).
"""

import hashlib
import re
from itertools import islice
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    bindparam,
    delete,
    func,
    select,
    text,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from grunt import log
from grunt.document.meta import Meta
from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry
from grunt.search.terms import (
    fts5_query,
    match_columns,
    mysql_boolean_query,
    session_dialect,
    tsquery,
)
lazy from grunt.metadata.doctype import DocType

_INDEX_TABLE_NAME = "grunt_search_index"
_FTS_TABLE_NAME = "grunt_search_fts"
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

_PG_TSVECTOR_INDEX_SQL = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS grunt_search_idx_ts "
    "ON grunt_search_index "
    "USING GIN (to_tsvector('simple', coalesce(content_raw, '')))"
)
_PG_DOCTYPE_INDEX_SQL = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS grunt_search_idx_doctype "
    "ON grunt_search_index (doctype)"
)

# FTS5 has no SQLAlchemy construct - virtual-table DDL/DML is plain text.
# remove_diacritics 0: keep й/ї/є distinct from и/і/е for Ukrainian.
_FTS_CREATE_SQL = (
    f"CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS_TABLE_NAME} USING fts5("
    "idx_id UNINDEXED, title, content, "
    "tokenize = 'unicode61 remove_diacritics 0', prefix = '2 3')"
)
_FTS_INSERT_SQL = text(
    f"INSERT INTO {_FTS_TABLE_NAME} (rowid, idx_id, title, content) "
    "VALUES (:rowid, :idx_id, :title, :content)"
)
_FTS_DELETE_SQL = text(f"DELETE FROM {_FTS_TABLE_NAME} WHERE rowid IN :rowids").bindparams(
    bindparam("rowids", expanding=True)
)
# bm25 weights per column: idx_id (unindexed), title ×10, content ×1.
_FTS_SEARCH_SQL = f"""
    SELECT t.idx_id, t.doctype, t.doc_id, t.doc_name, t.title, t.module
    FROM {_FTS_TABLE_NAME} AS f
    JOIN {_INDEX_TABLE_NAME} AS t ON t.idx_id = f.idx_id
    WHERE {_FTS_TABLE_NAME} MATCH :match {{doctype_clause}}
    ORDER BY bm25({_FTS_TABLE_NAME}, 0.0, 10.0, 1.0)
    LIMIT :limit
"""


def is_indexable(dt: DocType) -> bool:
    """True if *dt*'s documents belong in the global search index."""
    return not (dt.is_child or dt.is_virtual or dt.is_log) and dt.in_global_search


def _fts_rowid(idx_id: str) -> int:
    """Stable signed 64-bit rowid for an index entry (VACUUM-proof, unlike rowid)."""
    digest = hashlib.blake2b(idx_id.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


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


def _dialect(engine_or_session: Any) -> str:
    """Return the dialect name for an engine or session."""
    return session_dialect(engine_or_session) or "sqlite"


def _fts_title(title: str | None, doc_name: str | None) -> str:
    """Text for the FTS ``title`` column: title plus the id when they differ."""
    title = title or ""
    doc_name = doc_name or ""
    return title if not doc_name or doc_name == title else f"{title} {doc_name}"


class SearchIndexService:
    #: Engines (by URL) where the FTS5 table could not be created.
    _fts_unavailable: set[str]

    def __init__(self) -> None:
        self._fts_unavailable = set()

    def _use_fts(self, session_or_engine: Any) -> bool:
        if _dialect(session_or_engine) != "sqlite":
            return False
        bind = getattr(session_or_engine, "bind", None) or session_or_engine
        return str(getattr(bind, "url", "")) not in self._fts_unavailable

    async def ensure_table(self, engine: AsyncEngine) -> None:
        """Create grunt_search_index table + indexes if they don't exist."""
        dialect = _dialect(engine)
        async with engine.begin() as conn:
            await conn.run_sync(_INDEX_META.create_all, checkfirst=True)
            if dialect == "mysql":
                await conn.execute(
                    text(
                        "ALTER TABLE grunt_search_index "
                        "ADD FULLTEXT IF NOT EXISTS idx_ft_content (content_raw, title, doc_name)"
                    )
                )

        if dialect == "postgresql":
            # CONCURRENTLY cannot run inside a transaction block
            async with engine.connect() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(text(_PG_TSVECTOR_INDEX_SQL))
                await conn.execute(text(_PG_DOCTYPE_INDEX_SQL))

        if dialect == "sqlite":
            await self._ensure_fts(engine)

    async def _ensure_fts(self, engine: AsyncEngine) -> None:
        """Create the FTS5 table and backfill it when it is out of step."""
        url = str(engine.url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(_FTS_CREATE_SQL))
                fts_count = (
                    await conn.execute(text(f"SELECT count(*) FROM {_FTS_TABLE_NAME}"))
                ).scalar_one()
                base_count = (
                    await conn.execute(select(func.count()).select_from(_search_index_table))
                ).scalar_one()
                if fts_count != base_count:
                    await self._rebuild_fts(conn)
                    log.info("search_index.fts_rebuilt", rows=base_count, was=fts_count)
            self._fts_unavailable.discard(url)
        except Exception as e:
            self._fts_unavailable.add(url)
            log.warning("search_index.fts_unavailable", error=str(e))

    async def _rebuild_fts(self, conn: AsyncConnection | AsyncSession) -> None:
        """Refill the FTS5 table from grunt_search_index."""
        await conn.execute(text(f"DELETE FROM {_FTS_TABLE_NAME}"))
        t = _search_index_table
        cols = select(t.c.idx_id, t.c.title, t.c.doc_name, t.c.content_raw).order_by(t.c.idx_id)
        last: str | None = None
        while True:
            page = cols if last is None else cols.where(t.c.idx_id > last)
            chunk = (await conn.execute(page.limit(_CHUNK))).fetchall()
            if not chunk:
                break
            last = chunk[-1].idx_id
            await conn.execute(
                _FTS_INSERT_SQL,
                [
                    {
                        "rowid": _fts_rowid(r.idx_id),
                        "idx_id": r.idx_id,
                        "title": _fts_title(r.title, r.doc_name),
                        "content": r.content_raw or "",
                    }
                    for r in chunk
                ],
            )

    async def _fts_delete(self, session: AsyncSession, idx_ids: list[str]) -> None:
        if idx_ids and self._use_fts(session):
            await session.execute(_FTS_DELETE_SQL, {"rowids": [_fts_rowid(i) for i in idx_ids]})

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

        idx_id = f"{doctype}:{doc_id}"
        title_field = dt.title_field or "name"
        title = str(doc.get(title_field) or doc.get("name") or "")
        doc_name = str(doc.get("name") or "")
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

            dialect = _dialect(session)
            update_cols = {k: v for k, v in row.items() if k != "idx_id"}
            stmt: Any
            if dialect == "postgresql":
                stmt = (
                    pg_insert(_search_index_table)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=["idx_id"],
                        set_=update_cols,
                    )
                )
            elif dialect == "mysql":
                stmt = (
                    mysql_insert(_search_index_table)
                    .values(**row)
                    .on_duplicate_key_update(**update_cols)
                )
            else:
                # SQLite: delete + insert (no native upsert in old versions)
                await session.execute(
                    delete(_search_index_table).where(_search_index_table.c.idx_id == idx_id)
                )
                stmt = _search_index_table.insert().values(**row)

            await session.execute(stmt)

            if self._use_fts(session):
                await self._fts_delete(session, [idx_id])
                await session.execute(
                    _FTS_INSERT_SQL,
                    {
                        "rowid": _fts_rowid(idx_id),
                        "idx_id": idx_id,
                        "title": _fts_title(title, doc_name),
                        "content": content_raw,
                    },
                )
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
            await self._fts_delete(session, [idx_id])
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
            it = iter(doc_ids)
            while chunk := list(islice(it, chunk_size)):
                idx_ids = [f"{doctype}:{doc_id}" for doc_id in chunk]
                await session.execute(
                    delete(_search_index_table).where(_search_index_table.c.idx_id.in_(idx_ids))
                )
                await self._fts_delete(session, idx_ids)
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
        it = iter(idx_ids)
        while chunk := list(islice(it, _CHUNK)):
            await self._fts_delete(session, chunk)
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

        dialect = _dialect(session)
        try:
            if dialect == "sqlite" and self._use_fts(session):
                return await self._search_fts(session, q, limit, doctype)
            return await self._search_sql(session, dialect, q, limit, doctype)
        except Exception:
            log.exception("search_index.search_failed", q=q)
            return []

    async def _search_fts(
        self, session: AsyncSession, q: str, limit: int, doctype: str | None
    ) -> list[dict[str, Any]]:
        match = fts5_query(q)
        if match is None:
            # Only punctuation typed - nothing FTS can tokenize; plain LIKE.
            return await self._search_sql(session, "sqlite", q, limit, doctype)
        params: dict[str, Any] = {"match": match, "limit": limit}
        clause = ""
        if doctype:
            clause = "AND t.doctype = :doctype"
            params["doctype"] = doctype
        stmt = text(_FTS_SEARCH_SQL.format(doctype_clause=clause))
        rows = (await session.execute(stmt, params)).fetchall()
        return [dict(r._mapping) for r in rows]

    async def _search_sql(
        self, session: AsyncSession, dialect: str, q: str, limit: int, doctype: str | None
    ) -> list[dict[str, Any]]:
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

        stmt: Any
        if dialect == "postgresql" and (pg_query := tsquery(q)):
            # Prefix tsquery built from word characters only; the vector
            # expression matches the GIN index definition exactly.
            ts_query = func.to_tsquery("simple", pg_query)
            ts_vector = func.to_tsvector("simple", func.coalesce(t.c.content_raw, ""))
            title_hit = func.to_tsvector("simple", func.coalesce(t.c.title, "")).op("@@")(ts_query)
            stmt = (
                base.where(ts_vector.op("@@")(ts_query))
                .order_by(title_hit.desc(), func.ts_rank(ts_vector, ts_query).desc())
                .limit(limit)
            )
        elif dialect == "mysql" and (my_query := mysql_boolean_query(q)):
            # MySQL FULLTEXT MATCH ... AGAINST. The query is a bound
            # parameter (:search_q), never string-interpolated into the SQL
            # text - and it only carries word characters plus our own +, *
            # and " operators (see grunt.search.terms.mysql_boolean_query).
            match_expr = func.match(t.c.content_raw, t.c.title, t.c.doc_name).op("AGAINST")(
                text("(:search_q IN BOOLEAN MODE)").bindparams(search_q=my_query)
            )
            stmt = base.where(match_expr).order_by(match_expr.desc()).limit(limit)
        else:
            # Fallback: every term as a substring of name / title / content.
            condition = match_columns(q, [t.c.content_raw, t.c.doc_name, t.c.title], dialect)
            if condition is None:
                return []
            stmt = base.where(condition).limit(limit)

        rows = (await session.execute(stmt)).fetchall()
        return [dict(r._mapping) for r in rows]

    async def reindex_all(
        self,
        session: AsyncSession,
        engine: AsyncEngine,
    ) -> int:
        """Rebuild the entire search index from all DocType tables. Returns count."""
        # Clear index
        await session.execute(delete(_search_index_table))
        if self._use_fts(session):
            await session.execute(text(f"DELETE FROM {_FTS_TABLE_NAME}"))

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
