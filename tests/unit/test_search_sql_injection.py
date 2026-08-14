"""Regression: SQL injection (CWE-89) in SearchIndexService.search()'s MySQL
FULLTEXT branch.

`text(f"('{q}' IN BOOLEAN MODE)")` string-interpolated the raw, user-typed
search query directly into a SQL literal. Verified live:

    q = "' OR 1=1 -- "
    text(f"('{q}' IN BOOLEAN MODE)")  →  ('' OR 1=1 -- ' IN BOOLEAN MODE)

— a syntactically valid SQL injection, reachable by any authenticated user
via the search endpoint on a MySQL-backed deployment (PostgreSQL/SQLite
already used SQLAlchemy's parameterized query builders correctly; only the
MySQL branch used raw text interpolation). Fixed with a bound parameter
(`text("(:search_q IN BOOLEAN MODE)").bindparams(search_q=q)`).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import mysql

from grunt.search.service import SearchIndexService, _search_index_table

_INJECTION_PAYLOAD = "' OR 1=1 -- "


@pytest.mark.asyncio
async def test_mysql_branch_uses_bound_parameter_not_string_interpolation(db_session):
    """Drive the real search() method down the MySQL branch and capture the
    statement it builds, before execution — proving the query object itself
    carries the malicious input as a parameter, not baked into SQL text.
    """
    svc = SearchIndexService()
    captured: dict[str, object] = {}

    async def _fake_execute(stmt):
        captured["stmt"] = stmt

        class _Result:
            def fetchall(self):
                return []

        return _Result()

    with (
        patch("grunt.search.service._dialect", return_value="mysql"),
        patch.object(db_session, "execute", side_effect=_fake_execute),
    ):
        result = await svc.search(db_session, _INJECTION_PAYLOAD)

    assert result == []
    stmt = captured["stmt"]

    # Unrendered SQL (no literal_binds): the payload must never appear as
    # raw text — it should only be reachable via a bound-parameter name.
    # This is what a vulnerable `text(f"('{q}' ...")` construction would
    # fail: the payload would already be baked into the SQL string itself.
    raw_sql = str(stmt)
    assert _INJECTION_PAYLOAD not in raw_sql

    # And SQLAlchemy's own literal-bind rendering (used only for this
    # assertion, never for real execution) properly escapes the embedded
    # quote by doubling it, so "OR 1=1" never becomes a bare SQL keyword
    # sequence outside the string literal it was submitted in.
    compiled_with_params_visible = str(
        stmt.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "''" in compiled_with_params_visible  # embedded quote doubled/escaped


def test_reference_vulnerable_pattern_is_actually_dangerous():
    """Sanity check the exploit premise itself: the pattern this fix removed
    (an f-string building a text() fragment) really does produce injectable
    SQL for this payload — otherwise the "fix" above wouldn't be proving
    anything.
    """
    vulnerable_fragment = text(f"('{_INJECTION_PAYLOAD}' IN BOOLEAN MODE)")
    assert str(vulnerable_fragment) == "('' OR 1=1 -- ' IN BOOLEAN MODE)"


def test_safe_construction_uses_placeholder_in_unrendered_sql():
    """The fixed construction's plain str() (no compilation) shows the
    bind-parameter placeholder, never the raw value — the value only
    reaches the database via the driver's parameter binding.
    """
    t = _search_index_table
    match_expr = func.match(t.c.content_raw, t.c.title, t.c.doc_name).op("AGAINST")(
        text("(:search_q IN BOOLEAN MODE)").bindparams(search_q=_INJECTION_PAYLOAD)
    )
    stmt = select(t.c.idx_id).where(match_expr)
    assert _INJECTION_PAYLOAD not in str(stmt)
    assert ":search_q" in str(stmt) or "search_q" in str(stmt)
