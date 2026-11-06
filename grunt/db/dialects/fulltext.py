"""Full-text index over one table - the backend's native engine behind one interface.

A :class:`FullTextSpec` names the indexed table and its columns: a unique
``key``, a ``title`` (hits there rank first), a secondary ``label`` (e.g. the
document id) and the ``content``. ``Dialect.fulltext(spec)`` returns the
engine for that backend:

* **SQLite** - a companion FTS5 table ``<name>_fts`` (unicode61 tokenizer,
  2/3-char prefix indexes, bm25 ranking). Its ``rowid`` is a stable 64-bit
  hash of the key, so it survives ``VACUUM`` and needs no triggers; the
  caller keeps it in step through :meth:`FullText.write` / :meth:`FullText.delete`.
  If FTS5 is unavailable on an engine, :meth:`FullText.match` returns ``None``.
* **PostgreSQL** - GIN ``tsvector`` index, prefix ``tsquery``, ``ts_rank``.
* **MySQL** - native ``FULLTEXT`` in boolean mode.

All engines get the same query semantics (see :mod:`grunt.search.terms`):
every term must match, each as a word *prefix*. ``match()`` returns ``None``
when the engine can't serve the query (nothing to tokenize, engine
unavailable) - the caller then falls back to a ``LIKE`` search.
"""

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    Select,
    Table,
    bindparam,
    column,
    func,
    literal_column,
    select,
    table,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from grunt import log
lazy from grunt.search.terms import fts5_query, mysql_boolean_query, tsquery


@dataclass(frozen=True)
class FullTextSpec:
    """Which table and columns a full-text index covers."""

    #: Base name for the engine's own objects (FTS table, indexes).
    name: str
    table: Table
    key: str
    title: str
    label: str
    content: str


class FullText(ABC):
    """Native full-text engine of one backend over a :class:`FullTextSpec`."""

    def __init__(self, spec: FullTextSpec) -> None:
        self.spec = spec

    @property
    def t(self) -> Table:
        return self.spec.table

    @abstractmethod
    async def ensure(self, engine: AsyncEngine) -> None:
        """Create the engine's indexes/tables if missing (idempotent)."""

    @abstractmethod
    def match(self, session: Any, base: Select, q: str) -> Select | None:
        """*base* (a select from the table) narrowed to *q* and ranked; ``None`` - fall back."""

    async def write(self, session: Any, rows: list[Mapping[str, Any]]) -> None:
        """Index *rows* (already upserted into the table) - for engines with a side table."""
        return None  # the index lives on the table itself

    async def delete(self, session: Any, keys: list[str]) -> None:
        """Drop *keys* from the index - for engines with a side table."""
        return None  # the index lives on the table itself

    async def clear(self, session: Any) -> None:
        """Empty the index - for engines with a side table."""
        return None  # the index lives on the table itself

    async def drop(self, engine: AsyncEngine) -> None:
        """Remove the engine's own objects (side tables) - indexes go with the table."""
        return None


# ── SQLite FTS5 ─────────────────────────────────────────────────────────────


def fts_rowid(key: str) -> int:
    """Stable signed 64-bit rowid for an index entry (VACUUM-proof, unlike rowid)."""
    digest = hashlib.blake2b(key.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _fts_title(title: str | None, label: str | None) -> str:
    """Text for the FTS ``title`` column: title plus the label when they differ."""
    title = title or ""
    label = label or ""
    return title if not label or label == title else f"{title} {label}"


_CHUNK = 500


class SqliteFts5(FullText):
    def __init__(self, spec: FullTextSpec) -> None:
        super().__init__(spec)
        self.fts_name = f"{spec.name}_fts"
        #: Engine URLs where the FTS5 table could not be created.
        self._unavailable: set[str] = set()
        f, k = self.fts_name, spec.key
        # The FTS column carries the key under its own name, so a table made
        # by an earlier version (same layout) keeps working.
        self._insert = text(
            f"INSERT INTO {f} (rowid, {k}, title, content) VALUES (:rowid, :key, :title, :content)"
        )
        self._delete = text(f"DELETE FROM {f} WHERE rowid IN :rowids").bindparams(
            bindparam("rowids", expanding=True)
        )

    def _available(self, bind: Any) -> bool:
        bind = getattr(bind, "bind", None) or bind
        return str(getattr(bind, "url", "")) not in self._unavailable

    async def ensure(self, engine: AsyncEngine) -> None:
        """Create the FTS5 table and backfill it when it is out of step."""
        url = str(engine.url)
        try:
            async with engine.begin() as conn:
                # remove_diacritics 0: keep й/ї/є distinct from и/і/е for Ukrainian.
                await conn.execute(
                    text(
                        f"CREATE VIRTUAL TABLE IF NOT EXISTS {self.fts_name} USING fts5("
                        f"{self.spec.key} UNINDEXED, title, content, "
                        "tokenize = 'unicode61 remove_diacritics 0', prefix = '2 3')"
                    )
                )
                fts_count = (
                    await conn.execute(text(f"SELECT count(*) FROM {self.fts_name}"))
                ).scalar_one()
                base_count = (
                    await conn.execute(select(func.count()).select_from(self.t))
                ).scalar_one()
                if fts_count != base_count:
                    await self._rebuild(conn)
                    log.info("search_index.fts_rebuilt", rows=base_count, was=fts_count)
            self._unavailable.discard(url)
        except Exception as e:
            self._unavailable.add(url)
            log.warning("search_index.fts_unavailable", error=str(e))

    async def _rebuild(self, conn: Any) -> None:
        await conn.execute(text(f"DELETE FROM {self.fts_name}"))
        s, t = self.spec, self.t
        key = t.c[s.key]
        cols = select(key, t.c[s.title], t.c[s.label], t.c[s.content]).order_by(key)
        last: str | None = None
        while True:
            page = cols if last is None else cols.where(key > last)
            chunk = (await conn.execute(page.limit(_CHUNK))).mappings().all()
            if not chunk:
                break
            last = chunk[-1][s.key]
            await conn.execute(self._insert, [self._params(r) for r in chunk])

    def _params(self, row: Mapping[str, Any]) -> dict[str, Any]:
        s = self.spec
        return {
            "rowid": fts_rowid(row[s.key]),
            "key": row[s.key],
            "title": _fts_title(row.get(s.title), row.get(s.label)),
            "content": row.get(s.content) or "",
        }

    async def drop(self, engine: AsyncEngine) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {self.fts_name}"))

    async def write(self, session: Any, rows: list[Mapping[str, Any]]) -> None:
        if not rows or not self._available(session):
            return
        await self.delete(session, [r[self.spec.key] for r in rows])
        await session.execute(self._insert, [self._params(r) for r in rows])

    async def delete(self, session: Any, keys: list[str]) -> None:
        if keys and self._available(session):
            await session.execute(self._delete, {"rowids": [fts_rowid(k) for k in keys]})

    async def clear(self, session: Any) -> None:
        if self._available(session):
            await session.execute(text(f"DELETE FROM {self.fts_name}"))

    def match(self, session: Any, base: Select, q: str) -> Select | None:
        query = fts5_query(q)
        if query is None or not self._available(session):
            return None
        f = self.fts_name
        fts = table(f, column(self.spec.key))
        # bm25 weights per column: key (unindexed), title ×10, content ×1.
        return (
            base.join_from(self.t, fts, fts.c[self.spec.key] == self.t.c[self.spec.key])
            .where(text(f"{f} MATCH :fts_match").bindparams(fts_match=query))
            .order_by(text(f"bm25({f}, 0.0, 10.0, 1.0)"))
        )


# ── PostgreSQL tsvector ─────────────────────────────────────────────────────


class PostgresTsvector(FullText):
    """GIN ``tsvector`` index. Hyphens are turned into spaces before parsing:
    PostgreSQL's parser reads ``УН-2024-001`` as ``ун``, ``-2024``, ``-001``
    (signed numbers), so a search for ``2024`` would miss it. FTS5 splits on
    the hyphen anyway - both backends find the same documents."""

    #: Bumped whenever the indexed expression changes - the old index is dropped.
    _INDEX_VERSION = 2

    def _vector(self, col: str) -> Any:
        # Must match the GIN index expression exactly for the index to be used -
        # the constants as SQL literals, not bound parameters: asyncpg prepares
        # statements, and a generic plan can't match "$1" against the index.
        return func.to_tsvector(
            literal_column("'simple'::regconfig"),
            func.translate(
                func.coalesce(self.t.c[col], literal_column("''")),
                literal_column("'-'"),
                literal_column("' '"),
            ),
        )

    async def ensure(self, engine: AsyncEngine) -> None:
        name = self.spec.name
        # CONCURRENTLY cannot run inside a transaction block
        async with engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            for old in range(1, self._INDEX_VERSION):
                suffix = "" if old == 1 else str(old)
                await conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}_idx_ts{suffix}"))
            await conn.execute(
                text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name}_idx_ts{self._INDEX_VERSION} "
                    f"ON \"{self.t.name}\" USING GIN (to_tsvector('simple', "
                    f"translate(coalesce({self.spec.content}, ''), '-', ' ')))"
                )
            )

    def match(self, session: Any, base: Select, q: str) -> Select | None:
        pg_query = tsquery(q)
        if pg_query is None:
            return None
        # Prefix tsquery built from word characters only.
        ts_query = func.to_tsquery("simple", pg_query)
        content = self._vector(self.spec.content)
        title_hit = self._vector(self.spec.title).op("@@")(ts_query)
        return base.where(content.op("@@")(ts_query)).order_by(
            title_hit.desc(), func.ts_rank(content, ts_query).desc()
        )


# ── MySQL FULLTEXT ──────────────────────────────────────────────────────────


class MysqlFulltext(FullText):
    def _columns(self) -> Iterable[str]:
        s = self.spec
        return (s.content, s.title, s.label)

    async def ensure(self, engine: AsyncEngine) -> None:
        cols = ", ".join(self._columns())
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"ALTER TABLE {self.t.name} "
                    f"ADD FULLTEXT IF NOT EXISTS {self.spec.name}_idx_ft ({cols})"
                )
            )

    def match(self, session: Any, base: Select, q: str) -> Select | None:
        my_query = mysql_boolean_query(q)
        if my_query is None:
            return None
        # The query is a bound parameter, never interpolated into the SQL -
        # and it only carries word characters plus our own +, * and "
        # operators (see grunt.search.terms.mysql_boolean_query).
        match_expr = func.match(*(self.t.c[c] for c in self._columns())).op("AGAINST")(
            text("(:search_q IN BOOLEAN MODE)").bindparams(search_q=my_query)
        )
        return base.where(match_expr).order_by(match_expr.desc())
