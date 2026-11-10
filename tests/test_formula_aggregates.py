"""``count`` / ``sum_docs`` in formulas read every matching row, not a page of them."""

from typing import cast

import pytest

from grunt.document import formula
from grunt.document.formula import _evaluate_formulas
lazy from grunt.metadata.doctype import DocType

DOCTYPE = "FormulaLedger"


class _Field:
    def __init__(self, fieldname: str, expr: str) -> None:
        self.fieldname = fieldname
        self.formula = expr
        self.read_formula = expr
        self.fieldtype = "Data"
        self.is_virtual = True


class _DT:
    name = "FormulaProbe"

    def __init__(self, expr: str) -> None:
        self._field = _Field("out", expr)


@pytest.fixture
def probe(monkeypatch):
    class _Meta:
        def __init__(self, dt):
            self._dt = dt

        def get_formula_fields(self, attr):
            return [self._dt._field]

        def get_numeric_fieldnames(self):
            return set()

    monkeypatch.setattr(formula, "Meta", _Meta)


@pytest.fixture
async def ledger(ctx):
    from grunt.api.v1.meta import save_doctype, sync_doctype

    await save_doctype(
        doctype_data={
            "name": DOCTYPE,
            "label": "Formula ledger",
            "module": "Core",
            "fields": [{"fieldname": "amount", "label": "Amount", "fieldtype": "Int"}],
            "permissions": [{"role": "System Manager", "read": True, "write": True}],
        }
    )
    await sync_doctype(name=DOCTYPE)
    for i in range(25):  # more than a page of grunt.get_list (20)
        await ctx.new_doc(DOCTYPE, {"amount": i + 1})


async def test_sum_docs_adds_up_every_row(ctx, ledger, probe):
    dt = cast("DocType", _DT(f"sum_docs('{DOCTYPE}', 'amount')"))
    row = await _evaluate_formulas(dt, {"name": "p1", "out": None}, "read_formula")
    assert float(row["out"]) == sum(range(1, 26))


async def test_count_counts_every_row(ctx, ledger, probe):
    dt = cast("DocType", _DT(f"count('{DOCTYPE}')"))
    row = await _evaluate_formulas(dt, {"name": "p1", "out": None}, "read_formula")
    assert int(row["out"]) == 25
