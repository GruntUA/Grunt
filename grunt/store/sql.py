"""``SqlStore`` - a DocType's rows in its SQL table.

Compiles a :class:`~grunt.query.query.Query` into SQLAlchemy Core: the predicate
through :mod:`grunt.query.sql`, the order and keyset through the
:class:`~grunt.db.dialects.Dialect` (text case ignored, empty values last,
``name`` by code points breaking ties - ``tests/contract``).
"""

import re
from typing import Any

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt.db.buckets import DATE_BUCKETS
from grunt.db.dialects import Dialect, dialect_for
from grunt.document.meta import Meta
from grunt.query.compile_sql import typed_value
from grunt.query.query import Query, Sort
from grunt.query.sql import where
from grunt.search.terms import like_term, match_terms
lazy from grunt.metadata.compiler import MULTI_LINK_TABLE

# "sum(amount)" / "count()" - see parse_aggregation.
_AGG_EXPR_RE = re.compile(r"^([a-z_]+)(?:\((.*)\))?$")
# "month(created_at)" / "date(due)" - a group_by entry with a period bucket.
GROUP_FN_RE = re.compile(rf"^(date|{'|'.join(DATE_BUCKETS)})\((.+)\)$", re.IGNORECASE)
_AGG_FUNCS = {"sum": func.sum, "avg": func.avg, "min": func.min, "max": func.max}
# Bound parameters per IN (...) when loading MultiLink values.
_CHUNK = 500


def parse_aggregation(expr: str) -> tuple[str, str | None]:
    """An ``aggregates`` entry (``sum(amount)``, ``count()``) as (function, field).

    The field is ``None`` for ``count()`` / ``count``. ``ValueError`` for anything
    else than ``fn(field)`` / ``fn``.
    """
    m = _AGG_EXPR_RE.match(expr.strip().lower())
    if not m:
        raise ValueError(f"Invalid aggregation expression: {expr}")
    fn_name, field = m.groups()
    return fn_name, (field.strip() if field else None)


def group_field(entry: str) -> str:
    """The field a ``group_by`` entry reads (``month(posting_date)`` -> ``posting_date``)."""
    m = GROUP_FN_RE.match(entry.strip())
    return m.group(2).strip() if m else entry.strip()


def _aggregate_column(table: Any, fn_name: str, field: str | None) -> Any:
    if fn_name == "count":
        return func.count()
    if not field or field == "*":
        raise ValueError(f"Function {fn_name} requires a field name.")
    fn = _AGG_FUNCS.get(fn_name)
    if fn is None:
        raise ValueError(f"Unsupported aggregation function: {fn_name}")
    return fn(table.c[field])


def _group_column(table: Any, entry: str, dialect: Dialect) -> tuple[Any, Any]:
    """(select expression, GROUP BY expression) for one ``group_by`` entry: a
    column, ``date(field)`` (calendar day) or a period bucket ``day/month/
    quarter/year(field)`` labelled ``2026-09-23`` / ``2026-09`` / ``2026-Q3`` / ``2026``."""
    entry = entry.strip()
    m = GROUP_FN_RE.match(entry)
    if m:
        fn, field = m.group(1).lower(), m.group(2).strip()
        col = table.c[field]
        expr = dialect.calendar_date(col) if fn == "date" else dialect.date_bucket(col, fn)
        return expr.label(entry), expr
    col = table.c[entry]
    return col.label(entry), col


async def _linked_search_columns(field: Any) -> tuple[Any, list[Any]] | None:
    """The table a Link field points at and its identifying columns (``name``,
    title, search fields), so a search matches what the user sees, not the id.
    ``None`` when the target can't be resolved - the raw column is matched then."""
    target = getattr(field, "options", None)
    linked_dt = await grunt.get_meta(target) if target else None
    if linked_dt is None:
        return None
    linked_table = linked_dt.table
    cols = [linked_table.c.name]
    seen = {"name"}
    for fname in [linked_dt.title_field, *(linked_dt.search_fields or [])]:
        if not fname or fname in seen:
            continue
        col = linked_table.c.get(fname)
        if col is not None:
            cols.append(col)
            seen.add(fname)
    return linked_table, cols


async def search_condition(table: Any, meta: Meta, text: str, dialect: Dialect) -> Any | None:
    """The list search box as a condition, or ``None`` for no terms.

    Searched: ``name``, ``title_field`` and ``search_fields``. Every term must be
    found in some searched column (:mod:`grunt.search.terms`), so «Іван Петренко»
    finds first and last name kept in separate fields. A Link field is matched by
    the linked document's title/search fields - users type the name, not the id.
    """
    dt = meta.doc
    direct_cols: list[Any] = [table.c.name]
    link_targets: list[tuple[Any, Any, list[Any]]] = []
    seen = {"name"}
    for fname in [dt.title_field, *(dt.search_fields or [])]:
        if not fname or fname in seen:
            continue
        seen.add(fname)
        col = table.c.get(fname)
        if col is None:
            continue
        field = meta.get_field(fname)
        if field is not None and field.has_trait("link"):
            resolved = await _linked_search_columns(field)
            if resolved is not None:
                link_targets.append((col, *resolved))
                continue
        direct_cols.append(col)

    def term_condition(term: str) -> Any:
        conditions = [like_term(c, term, dialect) for c in direct_cols]
        for col, linked_table, linked_cols in link_targets:
            linked_match = or_(*(like_term(c, term, dialect) for c in linked_cols))
            conditions.append(col.in_(select(linked_table.c.name).where(linked_match)))
        return or_(*conditions)

    return match_terms(text, term_condition)


class SqlStore:
    """The rows of *meta*'s DocType in its table, read in *session*."""

    def __init__(self, meta: Any, session: AsyncSession) -> None:
        self.meta = meta
        self.session = session
        self.table = meta.table
        self.dialect = dialect_for(session)

    async def _where(self, stmt: Select, query: Query) -> Select:
        stmt = await where(stmt, query.where, self.table, self.meta.name)
        if query.search:
            condition = await search_condition(self.table, self.meta, query.search, self.dialect)
            if condition is not None:
                stmt = stmt.where(condition)
        return stmt

    def _sort_column(self, sort: Sort) -> Any | None:
        """The column to sort by - ``modified_at`` (then ``created_at``) for an
        unknown field."""
        c = self.table.c
        for name in (sort.field, "modified_at", "created_at"):
            col = c.get(name)
            if col is not None:
                return col
        return None

    def _keyset(self, sort_col: Any, descending: bool, after: tuple[Any, str]) -> Any:
        """Rows after (value, name) in the order of :meth:`fetch`."""
        value, after_name = after
        dialect = self.dialect
        name = dialect.exact(self.table.c.name)
        beyond_name = name < after_name if descending else name > after_name
        if value is None:  # within the empties - they come last, ordered by name
            return and_(sort_col.is_(None), beyond_name)
        key = dialect.sort_key(sort_col)
        bound = dialect.sort_key(literal(typed_value(sort_col, value), type_=sort_col.type))
        beyond = key < bound if descending else key > bound
        return or_(beyond, and_(key == bound, beyond_name), sort_col.is_(None))

    async def fetch(self, query: Query) -> list[dict[str, Any]]:
        table = self.table
        fields = query.fields
        multilinks = (
            [f.fieldname for f in self.meta.get_multilink_fields() if f.fieldname in fields]
            if fields
            else []
        )
        if fields:
            cols = [table.c[f] for f in fields if f in table.c]
            if multilinks and "name" not in fields:
                cols.append(table.c.name)  # key for the MultiLink values, dropped below
            stmt = select(*cols) if cols else select(table)
        else:
            stmt = select(table)

        stmt = await self._where(stmt, query)

        sort_col = self._sort_column(query.sort) if query.sort else None
        if query.sort and sort_col is not None:
            descending = query.sort.descending
            stmt = stmt.order_by(
                *self.dialect.sort(sort_col, descending=descending),
                *self.dialect.order_by(self.dialect.exact(table.c.name), descending=descending),
            )
            if query.after is not None:
                stmt = stmt.where(self._keyset(sort_col, descending, query.after))
        if query.limit is not None:
            stmt = stmt.limit(query.limit)
        if query.offset and query.after is None:
            stmt = stmt.offset(query.offset)

        rows = [dict(r._mapping) for r in await self.session.execute(stmt)]
        if multilinks:
            await self._attach_multilinks(rows, multilinks, keep_name="name" in (fields or ()))
        return rows

    async def _attach_multilinks(
        self, rows: list[dict[str, Any]], fieldnames: list[str], *, keep_name: bool
    ) -> None:
        """Set ``row[field]`` to its linked names (in ``idx`` order) for each MultiLink field."""
        values: dict[tuple[str, str], list[str]] = {}
        names = [r["name"] for r in rows]
        ml = MULTI_LINK_TABLE
        for start in range(0, len(names), _CHUNK):
            result = await self.session.execute(
                select(ml.c.parent_name, ml.c.parent_field, ml.c.link_name)
                .where(
                    ml.c.parent_doctype == self.meta.name,
                    ml.c.parent_field.in_(fieldnames),
                    ml.c.parent_name.in_(names[start : start + _CHUNK]),
                )
                .order_by(ml.c.parent_name, ml.c.parent_field, ml.c.idx)
            )
            for parent, field, link in result.fetchall():
                values.setdefault((parent, field), []).append(link)
        for row in rows:
            name = row["name"] if keep_name else row.pop("name")
            for field in fieldnames:
                row[field] = values.get((name, field), [])

    async def count(self, query: Query) -> int:
        stmt = await self._where(select(func.count()).select_from(self.table), query)
        return (await self.session.execute(stmt)).scalar() or 0

    async def aggregate(self, query: Query) -> list[dict[str, Any]]:
        table = self.table
        select_exprs: list[Any] = []
        group_exprs: list[Any] = []
        # label -> expression, so the sort resolves to a real construct - the
        # caller's string never reaches SQL as text.
        labeled: dict[str, Any] = {}

        for entry in query.group_by:
            select_expr, group_expr = _group_column(table, entry, self.dialect)
            select_exprs.append(select_expr)
            group_exprs.append(group_expr)
            labeled[entry.strip()] = select_expr
        for label, spec in query.aggregates:
            col = _aggregate_column(table, *parse_aggregation(spec)).label(label)
            select_exprs.append(col)
            labeled[label] = col
        if not select_exprs:
            select_exprs = [func.count().label("count")]

        # Explicit FROM: a bare select(func.count()) has none and returns one row.
        stmt = await self._where(select(*select_exprs).select_from(table), query)
        if group_exprs:
            stmt = stmt.group_by(*group_exprs)
        if query.sort:
            key = query.sort.field.strip()
            expr = labeled.get(key)
            if expr is None:
                expr = table.c.get(key)
                if expr is None:
                    raise ValueError(f"Invalid order_by: {query.sort.field!r}")
            stmt = stmt.order_by(*self.dialect.sort(expr, descending=query.sort.descending))
        if query.limit is not None:
            stmt = stmt.limit(query.limit)
        return [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]


__all__ = ["GROUP_FN_RE", "SqlStore", "group_field", "parse_aggregation", "search_condition"]
