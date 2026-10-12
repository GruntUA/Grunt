"""Security PoC/regression: a formula / read_formula expression must not be
able to escape its restricted namespace via attribute traversal.

``_evaluate_formulas`` execs ``async def __f__(): return <formula>`` with an
empty ``__builtins__``. That alone does NOT stop ``().__class__.__mro__...``
reaching ``os`` - only refusing the attribute access does (``_formula_is_safe``).
A ``formula`` is System-Manager-authored, but read_formula runs on every read,
so an escape would be stored RCE triggered in any reader's request context.
"""

from __future__ import annotations

import pytest

from grunt.document.formula import _evaluate_formulas, _formula_is_safe


class _Field:
    def __init__(self, fieldname: str, formula: str) -> None:
        self.fieldname = fieldname
        self.formula = formula
        self.read_formula = formula
        self.fieldtype = "Data"
        self.is_virtual = True


class _DT:
    name = "FormulaProbe"

    def __init__(self, formula: str) -> None:
        self._field = _Field("out", formula)


@pytest.fixture(autouse=True)
def _patch_meta(monkeypatch):
    import grunt.document.formula as fmod

    class _Meta:
        def __init__(self, dt):
            self._dt = dt

        def get_formula_fields(self, attr):
            return [self._dt._field]

        def get_numeric_fieldnames(self):
            return set()

    monkeypatch.setattr(fmod, "Meta", _Meta)


ESCAPES = [
    "().__class__.__mro__[-1].__subclasses__()",
    "(1).__class__.__bases__",
    "'{0.__class__}'.format(now)",
    "now.__class__.__init__.__globals__",
]


@pytest.mark.parametrize("expr", ESCAPES)
def test_escape_expressions_are_rejected(expr):
    assert _formula_is_safe(expr) is False


LEGIT = [
    "(qty or 0) * (rate or 0)",
    "' '.join(str(p) for p in ['a', 'b'] if p)",
    "str(today)[:10]",
    "count('Employee', {'x': name})",
    "f'/x/{name}'",
]


@pytest.mark.parametrize("expr", LEGIT)
def test_legitimate_formulas_pass_the_gate(expr):
    assert _formula_is_safe(expr) is True


@pytest.mark.asyncio
async def test_escape_formula_does_not_execute(ctx):
    # Even driven through the evaluator, an escape attempt yields no value
    # (blocked, field left unchanged) rather than reaching os.
    dt = _DT("().__class__.__mro__[-1].__subclasses__()")
    row = {"name": "p1", "out": None}
    result = await _evaluate_formulas(dt, row, "read_formula")
    assert result["out"] is None
