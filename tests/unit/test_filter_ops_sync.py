"""The filter-operator vocabulary is declared twice - ``DISPLAY_OPS`` in
grunt/query/parse.py and ``FILTER_OPS`` in frontend/src/core/filterOps.ts.
These tests keep the two in step and check report conditions use it."""

import re
from pathlib import Path

from grunt.query.parse import DISPLAY_OPS, FILTER_OPS, parse_filters, split_key
from grunt.reports.list_options import compile_conditions

FILTER_OPS_TS = Path(__file__).parents[2] / "frontend/src/core/filterOps.ts"


def _frontend_ops() -> dict[str, str]:
    """``'>=': { backend: 'gte', ... }`` lines of the FILTER_OPS table."""
    text = FILTER_OPS_TS.read_text(encoding="utf-8")
    table = text[text.index("export const FILTER_OPS = {") : text.index("} as const")]
    return dict(re.findall(r"'([^']+)':\s*\{\s*backend:\s*'([^']+)'", table))


def _frontend_suffixes() -> set[str]:
    text = FILTER_OPS_TS.read_text(encoding="utf-8")
    block = text[text.index("const BACKEND_SUFFIXES = [") :]
    return set(re.findall(r"'([^']+)'", block[: block.index("]")]))


def test_display_ops_match_frontend():
    assert _frontend_ops() == DISPLAY_OPS


def test_display_ops_are_known_backend_ops():
    # child_of is expanded to __in before parsing (expand_child_of_filters).
    assert set(DISPLAY_OPS.values()) - {"child_of"} <= set(FILTER_OPS)


def test_every_backend_op_parses():
    for op in FILTER_OPS:
        assert parse_filters({f"f__{op}": "2024"}) is not None


def test_frontend_key_splitting_knows_every_backend_op():
    assert _frontend_suffixes() == set(FILTER_OPS) | {"child_of"}


def test_compile_conditions_uses_display_ops():
    out = compile_conditions(
        [
            {"fieldname": "status", "op": "=", "value": "Open"},
            {"fieldname": "title", "op": "like", "value": "ab"},
            {"fieldname": "region", "op": "in", "value": "A, B"},
            {"fieldname": "note", "op": "is not set"},
            {"fieldname": "x", "op": "bogus", "value": 1},
        ]
    )
    assert out == [
        {"status__eq": "Open"},
        {"title__ilike": "ab"},
        {"region__in": ["A", "B"]},
        {"note__is": "not set"},
    ]
    assert [split_key(next(iter(c)))[1] for c in out] == ["eq", "ilike", "in", "is"]
