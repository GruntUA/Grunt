"""Unit tests for operator-aware filter building in ``grunt.db.filters``.

These exercise ``apply_filters`` against a real SQLAlchemy table so the
compiled SQL is checked directly — in particular that the list-level parser
supports the same operators as the ``grunt.db`` count path (regression: the
``nin`` operator was silently dropped, so ``get_list`` and ``count`` disagreed).

``document/query.py`` used to have its own near-identical ``_apply_filters``
wrapping the same ``build_clauses`` — now the document layer imports this one
directly (see grunt.document.collection/tree/bulk_ops), so there's a single
implementation, not two that could drift apart again.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, select

from grunt.db.filters import apply_filters, build_clauses

_META = MetaData()
_TABLE = Table(
    "t",
    _META,
    Column("doctype", String),
    Column("status", String),
    Column("due_date", String),
    Column("foo__bar", String),
    Column("qty", Integer),
)


def _sql(filters: dict) -> str:
    stmt = apply_filters(select(_TABLE.c.doctype), _TABLE, filters)
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

    def test_in_csv_trims_spaces_and_blanks(self):
        assert "IN ('A', 'B')" in _sql({"doctype__in": " A, B,"})

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

    def test_nlike_keeps_nulls(self):
        sql = _sql({"status__nlike": "x"})
        assert "t.status IS NULL" in sql and "lower(t.status) NOT LIKE lower('%x%')" in sql

    def test_is_not_set_text_covers_null_and_empty(self):
        sql = _sql({"status__is": "not set"})
        assert "t.status IS NULL OR t.status = ''" in sql

    def test_is_set_text_negates_empty(self):
        sql = _sql({"status__is": "set"})
        assert "NOT (t.status IS NULL OR t.status = '')" in sql

    def test_is_not_set_non_text_is_null_only(self):
        sql = _sql({"qty__is": "not set"})
        assert "t.qty IS NULL" in sql and "''" not in sql

    def test_field_with_double_underscore_not_misparsed(self):
        # A real column named foo__bar (no operator) must compare equal, not be
        # split into foo + op "bar".
        assert "t.foo__bar = 'v'" in _sql({"foo__bar": "v"})

    def test_unknown_column_ignored(self):
        # No clause should be added for a column that does not exist.
        assert "WHERE" not in _sql({"missing__nin": ["a"]})

    def test_apply_filters_matches_build_clauses(self):
        # apply_filters is a thin where()-applying wrapper around
        # build_clauses — same WHERE output either way.
        f = {"doctype__nin": ["A", "B"], "status": "Open"}
        via_apply_filters = _sql(f)
        clauses = build_clauses(_TABLE, f)
        stmt = select(_TABLE.c.doctype)
        for c in clauses:
            stmt = stmt.where(c)
        via_build_clauses = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert via_apply_filters == via_build_clauses


class TestVirtualDocTypeInFilter:
    """VirtualDocType.apply_filters mirrors build_clauses' in / nin operand parsing."""

    ROWS = [{"s": "A"}, {"s": "B"}, {"s": "C"}]

    def _apply(self, filters):
        from grunt.metadata.virtual import VirtualDocType

        return [r["s"] for r in VirtualDocType("T").apply_filters(self.ROWS, filters)]

    def test_in_list_and_csv(self):
        assert self._apply({"s__in": ["A", "B"]}) == ["A", "B"]
        assert self._apply({"s__in": "A, B"}) == ["A", "B"]

    def test_nin_list(self):
        assert self._apply({"s__nin": ["A"]}) == ["B", "C"]
