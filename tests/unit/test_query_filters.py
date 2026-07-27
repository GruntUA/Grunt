"""Unit tests for operator-aware filter building in ``grunt.document.query``.

These exercise ``_apply_filters`` against a real SQLAlchemy table so the
compiled SQL is checked directly — in particular that the list-level parser
supports the same operators as the ``grunt.db`` count path (regression: the
``nin`` operator was silently dropped, so ``get_list`` and ``count`` disagreed).
"""

from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table, select

from grunt.document.query import _apply_filters

_META = MetaData()
_TABLE = Table("t", _META, Column("doctype", String), Column("status", String))


def _sql(filters: dict) -> str:
    stmt = _apply_filters(select(_TABLE.c.doctype), _TABLE, filters)
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestApplyFilters:
    def test_eq(self):
        assert "t.doctype = 'Invoice'" in _sql({"doctype": "Invoice"})

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

    def test_unknown_column_ignored(self):
        # No clause should be added for a column that does not exist.
        assert "WHERE" not in _sql({"missing__nin": ["a"]})
