"""``SqlStore`` - a DocType's rows in its SQL table.

Compiles a :class:`~grunt.query.query.Query` into SQLAlchemy Core: the predicate
through :mod:`grunt.query.sql`, the order and keyset through the
:class:`~grunt.db.dialects.Dialect` (text case ignored, empty values last,
``name`` by code points breaking ties - ``tests/contract``).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.dialects import Dialect, dialect_for
from grunt.document.meta import Meta
from grunt.metadata.registry import doctype_registry
from grunt.query.aggregates import GROUP_FN_RE, parse_aggregation
from grunt.query.compile_sql import typed_value
from grunt.query.query import Query, Sort
from grunt.query.sql import where
from grunt.search.terms import like_term, match_terms
from grunt.store.base import (
    AGGREGATE,
    BULK,
    DELETE,
    HISTORY,
    INSERT,
    REFERENCES,
    SQL,
    UPDATE,
    Store,
)
lazy from grunt.document.aggregate import compute_aggregations
lazy from grunt.document.multi_link import MultiLinkService
lazy from grunt.document.payload import PROTECTED_FIELDS, update_values
lazy from grunt.document.relations import (
    _load_child_tables,
    _save_child_tables,
    attach_multi_link_values,
)
lazy from grunt.document.serde import serialize_datetimes, with_doctype
lazy from grunt.document.update_side_effects import delete_row_and_links
lazy from grunt.metadata.compiler import MULTI_LINK_TABLE

# "sum(amount)" / "count()" - see parse_aggregation.
_AGG_FUNCS = {"sum": func.sum, "avg": func.avg, "min": func.min, "max": func.max}
# Bound parameters per IN (...) when loading MultiLink values.
_CHUNK = 500


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


async def _linked_search_columns(
    field: Any, exclude: frozenset[str] = frozenset()
) -> tuple[Any, list[Any]] | None:
    """The table a Link field points at and its identifying columns (``name``,
    title, search fields), so a search matches what the user sees, not the id.
    ``None`` when the target can't be resolved - the raw column is matched then.
    *exclude* - ``link_field.target_field`` names not to look in (hidden from
    the user by the target DocType's rules)."""
    target = getattr(field, "options", None)
    linked_dt = await doctype_registry.get_meta(target) if target else None
    if linked_dt is None:
        return None
    linked_table = linked_dt.table
    cols = [linked_table.c.name]
    seen = {"name"}
    for fname in [linked_dt.title_field, *(linked_dt.search_fields or [])]:
        if not fname or fname in seen or f"{field.fieldname}.{fname}" in exclude:
            continue
        col = linked_table.c.get(fname)
        if col is not None:
            cols.append(col)
            seen.add(fname)
    return linked_table, cols


async def search_condition(
    table: Any, meta: Meta, text: str, dialect: Dialect, exclude: frozenset[str] = frozenset()
) -> Any | None:
    """The list search box as a condition, or ``None`` for no terms.

    Searched: ``name``, ``title_field`` and ``search_fields``. Every term must be
    found in some searched column (:mod:`grunt.search.terms`), so «Іван Петренко»
    finds first and last name kept in separate fields. A Link field is matched by
    the linked document's title/search fields - users type the name, not the id.
    *exclude* - fields not to look in (hidden from the user); for a Link field,
    ``link_field.target_field`` names its target's columns.
    """
    dt = meta.doc
    direct_cols: list[Any] = [table.c.name]
    link_targets: list[tuple[Any, Any, list[Any]]] = []
    seen = {"name"}
    for fname in [dt.title_field, *(dt.search_fields or [])]:
        if not fname or fname in seen or fname in exclude:
            continue
        seen.add(fname)
        col = table.c.get(fname)
        if col is None:
            continue
        field = meta.get_field(fname)
        if field is not None and field.has_trait("link"):
            resolved = await _linked_search_columns(field, exclude)
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


class SqlStore(Store):
    """The rows of *meta*'s DocType in its table, read and written in *session*:
    child tables, MultiLink values and aggregates with them."""

    capabilities = frozenset({INSERT, UPDATE, DELETE, AGGREGATE, REFERENCES, HISTORY, BULK, SQL})

    def __init__(self, meta: Any, session: AsyncSession) -> None:
        super().__init__(meta, session)
        self.table = meta.table
        self.dialect = dialect_for(session)
        self._multilinks: MultiLinkService | None = None

    @property
    def multilinks(self) -> MultiLinkService:
        if self._multilinks is None:
            self._multilinks = MultiLinkService(self.session)
        return self._multilinks

    @property
    def columns(self) -> frozenset[str] | None:
        return self.meta.columns

    async def _where(self, stmt: Select, query: Query) -> Select:
        stmt = await where(stmt, query.where, self.table, self.meta.name)
        if query.search:
            condition = await search_condition(
                self.table, self.meta, query.search, self.dialect, query.search_exclude
            )
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

    async def distinct(self, field: str) -> list[Any]:
        col = self.table.c.get(field)
        if col is None:
            return []
        rows = await self.session.execute(select(col).where(col.is_not(None)).distinct())
        return [v for v in rows.scalars().all() if v not in (None, "")]

    # One document

    async def get(self, name: str, *, expand: list[str] | None = None) -> dict[str, Any] | None:
        table = self.table
        # A singleton has only ever one row; *name* is irrelevant (callers pass
        # the DocType's name, or nothing at all).
        stmt = select(table).limit(1)
        if not self.meta.is_singleton:
            stmt = stmt.where(table.c.name == name)
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return None
        doc = serialize_datetimes(dict(row._mapping))

        dt = self.meta
        expand_set = {x for x in (expand or []) if x}
        load_all = expand is None or "*" in expand_set
        tables = dt.get_table_fieldnames()
        if load_all:
            await _load_child_tables(self.session, dt.doc, doc)
        elif selected := tables & expand_set:
            await _load_child_tables(self.session, dt.doc, doc, include_fields=selected)
        multilinks = {f.fieldname for f in dt.get_multilink_fields()}
        if multilinks and (load_all or multilinks & expand_set):
            await attach_multi_link_values(
                self.multilinks,
                dt.name,
                doc["name"],
                dt.doc,
                doc,
                fields=None if load_all else multilinks & expand_set,
            )
        return doc

    async def insert(
        self, doc: dict[str, Any], *, input: dict[str, Any], user: str
    ) -> dict[str, Any]:
        """INSERT *doc* with its child rows (from *doc*, so rows a hook filled in
        are stored too), aggregates and MultiLink values (from *input*)."""
        dt, table = self.meta, self.table
        name = doc["name"]
        await self.session.execute(
            table.insert().values(**{k: v for k, v in doc.items() if k in table.c})
        )
        # Flush so the parent row exists before the child rows reference it.
        await self.session.flush()
        now = doc.get("created_at") or datetime.now(UTC)
        await _save_child_tables(self.session, dt.doc, name, doc, user, now)
        await self._apply_aggregations(name, doc)
        await self._sync_multilinks(name, input, only_present=False)
        return doc

    async def update(
        self,
        name: str,
        doc: dict[str, Any],
        *,
        before: dict[str, Any],
        input: dict[str, Any],
        user: str,
    ) -> dict[str, Any]:
        """UPDATE the row to *doc* - every physical field that differs from
        *before* or was submitted (hook changes and computed values included) -
        then child tables, aggregates and the submitted MultiLink fields."""
        dt, table = self.meta, self.table
        real_name = before["name"]
        values = update_values(dt, input, self.columns, user)
        for field in dt.get_physical_fields():
            if field.fieldname in PROTECTED_FIELDS or field.fieldname not in table.c:
                continue
            # A hook may have put the stored value back (a masked secret sent
            # unchanged) - the document wins over the request payload then too.
            if field.fieldname in values or doc.get(field.fieldname) != before.get(field.fieldname):
                values[field.fieldname] = doc.get(field.fieldname)
        # The audit stamps of the document, not fresh ones.
        for key in ("modified_at", "modified_by"):
            if key in values:
                values[key] = doc[key]

        await self.session.execute(table.update().where(table.c.name == real_name).values(**values))
        await _save_child_tables(self.session, dt.doc, real_name, doc, user, datetime.now(UTC))
        await self._apply_aggregations(real_name, doc)
        await self._sync_multilinks(real_name, input, only_present=True)
        await self.session.flush()

        result = serialize_datetimes(dict(doc))
        await _load_child_tables(self.session, dt.doc, result)
        return await self.output(result)

    async def delete(self, name: str, *, before: dict[str, Any]) -> None:
        """DELETE the row, its child rows and its MultiLink relations."""
        await delete_row_and_links(
            session=self.session,
            ml=self.multilinks,
            dt=self.meta,
            table=self.table,
            doctype_name=self.doctype,
            real_id=before["name"],
        )

    async def output(self, doc: dict[str, Any]) -> dict[str, Any]:
        result = serialize_datetimes(dict(doc))
        await attach_multi_link_values(
            self.multilinks, self.doctype, result["name"], self.meta.doc, result
        )
        return with_doctype(self.doctype, result)

    async def _apply_aggregations(self, name: str, doc: dict[str, Any]) -> None:
        """Compute and store the aggregate fields derived from child tables."""
        values = await compute_aggregations(self.session, self.meta.doc, name)
        if not values:
            return
        table = self.table
        await self.session.execute(table.update().where(table.c.name == name).values(**values))
        doc.update(values)
        await self.session.flush()

    async def _sync_multilinks(
        self, name: str, data: dict[str, Any], *, only_present: bool
    ) -> None:
        """Store the MultiLink lists in *data* (``only_present`` - leave the
        fields *data* doesn't mention as they are)."""
        for field in self.meta.get_multilink_fields():
            if only_present and field.fieldname not in data:
                continue
            values = data.get(field.fieldname)
            if isinstance(values, list):
                await self.multilinks.set_values(
                    self.doctype, name, field.fieldname, field.options or "", values
                )

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


__all__ = ["SqlStore", "search_condition"]
