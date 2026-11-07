"""The query AST: building, parsing filter dicts. Both backends giving the same
answers is ``tests/contract``'s job."""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects import sqlite

from grunt.query.compile_sql import to_sql
from grunt.query.evaluate import matches
from grunt.query.nodes import (
    FALSE,
    TRUE,
    And,
    Cmp,
    Empty,
    In,
    Like,
    MultiLink,
    Null,
    Or,
    Year,
    and_,
    conjuncts,
    or_,
)
from grunt.query.parse import parse_filters

A, B = Cmp("a", "eq", 1), Cmp("b", "eq", 2)


def test_and_or_flatten_and_absorb():
    assert and_() == TRUE and or_() == FALSE
    assert and_(A) == A and or_(A) == A
    assert and_(A, TRUE, and_(B, A)) == And((A, B, A))
    assert and_(A, FALSE) == FALSE and or_(A, TRUE) == TRUE
    assert or_(A, FALSE, or_(B)) == Or((A, B))
    assert conjuncts(TRUE) == () and conjuncts(A) == (A,) and conjuncts(And((A, B))) == (A, B)


@pytest.mark.parametrize(
    ("key", "value", "node"),
    [
        ("f", "x", Cmp("f", "eq", "x")),
        ("f__neq", 3, Cmp("f", "ne", 3)),
        ("f__gte", "5", Cmp("f", "gte", "5")),
        ("f__like", "a%b", Like("f", "%a%b%")),
        ("f__ilike", "a", Like("f", "%a%")),
        ("f__nlike", "a", Like("f", "%a%", negate=True)),
        ("f__in", "a, b,", In("f", ("a", "b"))),
        ("f__nin", ["a"], In("f", ("a",), negate=True)),
        ("f__isnull", "true", Null("f")),
        ("f__isnull", "0", Null("f", negate=True)),
        ("f__is", "not set", Empty("f")),
        ("f__is", "set", Empty("f", negate=True)),
        ("f__year", " 2024 ", Year("f", 2024)),
        ("f__year", "soon", FALSE),
        ("f__year", "99999", FALSE),
        ("f__lte_or_null", 3, Or((Cmp("f", "lte", 3), Null("f")))),
    ],
)
def test_parse_each_operator(key, value, node):
    assert parse_filters({key: value}) == node


def test_parse_name_string_and_empty():
    assert parse_filters("DOC-1") == Cmp("name", "eq", "DOC-1")
    assert parse_filters(None) == TRUE and parse_filters({}) == TRUE


def test_parse_skips_unknown_fields_when_fields_are_given():
    expr = parse_filters({"a": 1, "zz": 2, "dept__child_of": "X"}, fields={"a"})
    assert expr == Cmp("a", "eq", 1)


def test_parse_in_memory_rejects_unknown_operators():
    with pytest.raises(ValueError, match="child_of"):
        parse_filters({"dept__child_of": "X"})


def test_parse_multilink():
    ml = {"tags"}
    assert parse_filters({"tags": "a"}, multilinks=ml) == MultiLink("tags", ("a",))
    assert parse_filters({"tags__nin": "a,b"}, multilinks=ml) == MultiLink(
        "tags", ("a", "b"), negate=True
    )
    assert parse_filters({"tags__is": "set"}, multilinks=ml) == MultiLink("tags", None)
    assert parse_filters({"tags__isnull": 1}, multilinks=ml) == MultiLink("tags", None, negate=True)
    assert parse_filters({"tags__gt": "a"}, multilinks=ml) == TRUE  # unsupported: skipped


def test_sql_types_values_by_column():
    t = Table("t", MetaData(), Column("name", String), Column("qty", Integer))
    sql = to_sql(parse_filters({"qty__gt": "5", "qty__in": "1,2"}), t)
    compiled = sql.compile(dialect=sqlite.dialect())
    assert list(compiled.params.values()) == [5, [1, 2]]


def test_evaluate_missing_field_is_null():
    assert matches(Null("x"), {}) and not matches(Cmp("x", "ne", 1), {})
    with pytest.raises(NotImplementedError):
        matches(MultiLink("tags", None), {})
