"""Unit tests for grunt.search.terms - query splitting and engine renderers."""

from sqlalchemy import column
from sqlalchemy.dialects import sqlite

from grunt.search.terms import (
    MAX_TERMS,
    escape_like,
    fts5_query,
    like_term,
    match_columns,
    matches_text,
    mysql_boolean_query,
    split_terms,
    tsquery,
)


def test_split_terms_dedupes_case_insensitively_and_caps():
    assert split_terms("  Іван   іван Петренко ") == ["Іван", "Петренко"]
    assert split_terms(None) == []
    assert len(split_terms(" ".join(f"t{i}" for i in range(50)))) == MAX_TERMS


def test_escape_like_makes_wildcards_literal():
    assert escape_like("50%_a\\b") == "50\\%\\_a\\\\b"


def test_fts5_query_prefix_phrases_and_no_operators():
    assert fts5_query("петр іван") == '"петр"* "іван"*'
    assert fts5_query("UA-01") == '"UA 01"*'
    # Quotes, operators and FTS keywords are reduced to plain words.
    assert fts5_query('a" OR NEAR(x') == '"a"* "OR"* "NEAR x"*'
    assert fts5_query("-- %%") is None


def test_tsquery_prefix_and_phrase():
    assert tsquery("Петр Іван") == "петр:* & іван:*"
    assert tsquery("UA-01") == "(ua <-> 01:*)"
    assert tsquery("!!!") is None


def test_mysql_boolean_query():
    assert mysql_boolean_query("петр іван") == "+петр* +іван*"
    assert mysql_boolean_query("ЗАЯВ-2026") == '+"ЗАЯВ 2026"'
    assert mysql_boolean_query("'") is None


def test_like_term_uses_native_like_for_ascii_on_sqlite():
    col = column("title")
    ascii_sql = str(like_term(col, "abc", "sqlite").compile(dialect=sqlite.dialect()))
    cyr_sql = str(like_term(col, "абв", "sqlite").compile(dialect=sqlite.dialect()))
    assert "lower" not in ascii_sql and "LIKE" in ascii_sql
    assert "lower" in cyr_sql


def test_match_columns_ands_terms_and_ors_columns():
    sql = str(match_columns("a b", [column("x"), column("y")]))
    assert sql.count(" OR ") == 2 and " AND " in sql
    assert match_columns("   ", [column("x")]) is None


def test_matches_text_every_term_in_some_value():
    assert matches_text("іван ПЕТР", ["Петренко", "Іван"])
    assert not matches_text("іван сидор", ["Петренко", "Іван"])
    assert matches_text("", ["x"])
