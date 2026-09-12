"""Regression: the controller type-block sync used to creep indentation.

`sync_controller_types` sliced the source at the marker's `#` (i.e. *after*
the line's leading whitespace) and then prepended `new_block`, which carries
its own indent — so every sync added another level, and once the ``# begin``
marker was no longer at exactly four spaces the "legacy" branch spliced that
stray indent onto the first method below the block. After enough saves the
controller no longer parsed (`IndentationError`).
"""

from __future__ import annotations

import ast
import textwrap

from grunt.utils.codegen import render_template, sync_controller_types

_CONTROLLER = textwrap.dedent(
    '''\
    from __future__ import annotations

    from grunt.document.base import Document


    class Widget(Document):

        # begin: auto-generated types
        # This code is auto-generated. Do not modify anything in this block.

        old_field: str | None

        # end: auto-generated types

        async def validate(self) -> None:
            """Custom code below the block — must never move."""
            pass

        async def before_save(self) -> None:
            pass
    '''
)


def _fields(n: int) -> list[dict]:
    return [{"fieldname": f"f{i}", "fieldtype": "Data", "label": f"Label {i}"} for i in range(n)]


def test_repeated_sync_does_not_creep_indentation(tmp_path):
    py = tmp_path / "Widget.py"
    py.write_text(_CONTROLLER, encoding="utf-8")

    for i in range(1, 6):
        sync_controller_types(py, "Widget", _fields(i))
        src = py.read_text(encoding="utf-8")
        ast.parse(src)  # must stay valid every iteration

    lines = src.splitlines()
    assert "    # begin: auto-generated types" in lines
    assert "    # end: auto-generated types" in lines
    assert "    async def validate(self) -> None:" in lines
    assert "    async def before_save(self) -> None:" in lines


def test_sync_normalises_an_already_crept_block(tmp_path):
    crept = _CONTROLLER.replace(
        "    # begin: auto-generated types", "            # begin: auto-generated types"
    )
    py = tmp_path / "Widget.py"
    py.write_text(crept, encoding="utf-8")

    sync_controller_types(py, "Widget", _fields(2))
    src = py.read_text(encoding="utf-8")

    ast.parse(src)
    assert "    # begin: auto-generated types" in src.splitlines()


def test_fresh_controller_render_is_valid_python_with_one_field_per_line(tmp_path):
    ctx = {
        "name": "Widget",
        "physical_fields": [
            {"fieldname": "a", "py_type": "str | None", "label": "Назва", "fieldtype": "Data"},
            {"fieldname": "b", "py_type": "int | None", "label": "Кількість", "fieldtype": "Int"},
        ],
        "table_fields": [{"fieldname": "rows", "options": "WidgetRow"}],
    }
    out = render_template("doctype/controller.py.jinja", ctx)
    ast.parse(out)
    assert "    a: str | None  # Назва\n" in out
    assert "    b: int | None  # Кількість\n" in out
    assert "    rows: list[dict]  # Table: WidgetRow\n" in out
