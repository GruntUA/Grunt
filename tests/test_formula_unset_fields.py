"""A stored formula sees a field the new document left out as None."""

from typing import Any

import pytest

from grunt.document import formula
from grunt.document.formula import compute_formulas
from grunt.metadata.doctype import DocType

DT: Any = DocType.model_validate(
    {
        "name": "FormulaUnset",
        "label": "Formula unset",
        "module": "Core",
        "fields": [
            {"fieldname": "due_date", "label": "Due", "fieldtype": "Date"},
            {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
            {
                "fieldname": "is_overdue",
                "label": "Overdue",
                "fieldtype": "Check",
                "formula": "bool(due_date) and status != 'Closed'",
            },
        ],
    }
)


@pytest.mark.asyncio
async def test_left_out_field_reads_as_none(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(formula.log, "warning", lambda event, **_kw: warnings.append(event))
    row = await compute_formulas(DT, {"status": "Open"})
    assert not row["is_overdue"]
    assert warnings == []


@pytest.mark.asyncio
async def test_given_field_is_used():
    row = await compute_formulas(DT, {"status": "Open", "due_date": "2026-01-01"})
    assert row["is_overdue"]
