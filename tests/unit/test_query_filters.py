"""Unit tests for operator-aware filter building in ``grunt.document.query``.

These exercise ``_apply_filters`` against a real SQLAlchemy table so the
compiled SQL is checked directly — in particular that the list-level parser
supports the same operators as the ``grunt.db`` count path (regression: the
``nin`` operator was silently dropped, so ``get_list`` and ``count`` disagreed).
"""

from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table, select

from grunt.db.api import build_clauses
from grunt.document.query import _apply_filters

_META = MetaData()
_TABLE = Table(
    "t",
    _META,
    Column("doctype", String),
    Column("status", String),
    Column("due_date", String),
    Column("foo__bar", String),
)


def _sql(filters: dict) -> str:
    # Goes through document/query, which delegates to db.api.build_clauses —
    # exercising the single shared parser end to end.
    stmt = _apply_filters(select(_TABLE.c.doctype), _TABLE, filters)
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestApplyFilters:
    def test_eq(self):
        assert "t.doctype = 'Invoice'" in _sql({"doctype": "Invoice"})

    def test_explicit_eq_suffix(self):
        # `field__eq` must resolve to the column, not be treated as a column
        # literally named "field__eq" (which would silently drop the filter).
        assert "t.status = 'Active'" in _sql({"status__eq": "Active"})

    def test_in_list(self):
        sql = _sql({"doctype__in": ["A", "B"]})
        assert "IN ('A', 'B')" in sql and "NOT IN" not in sql

    def test_in_csv(self):
        assert "IN ('A', 'B')" in _sql({"doctype__in": "A,B"})

    def test_nin_list(self):
        sql = _sql({"doctype__nin": ["UserSession", "AppMenu"]})
        assert "NOT IN ('UserSession', 'AppMenu')" in sql

    def test_nin_csv(self):
        assert "NOT IN ('A', 'B')" in _sql({"doctype__nin": "A,B"})

    def test_ne(self):
        assert "t.doctype != 'X'" in _sql({"doctype__ne": "X"})

    def test_ne_and_neq_alias(self):
        assert "t.doctype != 'X'" in _sql({"doctype__neq": "X"})

    def test_ilike(self):
        assert "lower(t.status) LIKE lower('%x%')" in _sql({"status__ilike": "x"})

    def test_lte_or_null(self):
        sql = _sql({"due_date__lte_or_null": "2026-01-01"})
        assert "t.due_date <= '2026-01-01'" in sql and "t.due_date IS NULL" in sql

    def test_isnull_true_bool_and_string(self):
        assert "t.due_date IS NULL" in _sql({"due_date__isnull": True})
        assert "t.due_date IS NULL" in _sql({"due_date__isnull": "true"})

    def test_isnull_false_bool_and_string(self):
        assert "t.due_date IS NOT NULL" in _sql({"due_date__isnull": False})
        assert "t.due_date IS NOT NULL" in _sql({"due_date__isnull": "false"})

    def test_field_with_double_underscore_not_misparsed(self):
        # A real column named foo__bar (no operator) must compare equal, not be
        # split into foo + op "bar".
        assert "t.foo__bar = 'v'" in _sql({"foo__bar": "v"})

    def test_unknown_column_ignored(self):
        # No clause should be added for a column that does not exist.
        assert "WHERE" not in _sql({"missing__nin": ["a"]})

    def test_both_layers_share_one_parser(self):
        # db.api.build_clauses and document.query._apply_filters must produce
        # identical WHERE clauses — they are the same code now.
        f = {"doctype__nin": ["A", "B"], "status": "Open"}
        via_query = _sql(f)
        clauses = build_clauses(_TABLE, f)
        stmt = select(_TABLE.c.doctype)
        for c in clauses:
            stmt = stmt.where(c)
        via_db = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert via_query == via_db
