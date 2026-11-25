"""grunt.utils.typed_rows_codemod - deciding and rewriting (pyright not run: the
receiver types are given as pyright would reveal them)."""

import ast
import json
from pathlib import Path

import pytest

from grunt.utils.attr_codemod import _Classes, _document_attrs
from grunt.utils.typed_rows_codemod import (
    Result,
    Rewriter,
    _Controllers,
    _Fixer,
    find_sites,
)

ORDER = """\
from datetime import date

from grunt.document.base import Document


class Order(Document):
    status: str | None = None
    total: float | None = None
    placed_on: date | None = None

    def close(self) -> None:
        pass
"""

ORDER_JSON = {
    "name": "Order",
    "fields": [
        {"fieldname": "status", "fieldtype": "Select"},
        {"fieldname": "total", "fieldtype": "Float"},
        {"fieldname": "placed_on", "fieldtype": "Date"},
        {"fieldname": "label", "fieldtype": "Data", "read_formula": "status"},
    ],
}


@pytest.fixture
def app(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'shop'\n")
    pkg = tmp_path / "shop"
    folder = pkg / "doctypes" / "Order"
    folder.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (folder / "order.py").write_text(ORDER)
    (folder / "Order.json").write_text(json.dumps(ORDER_JSON))
    return pkg


def _rewrite(app: Path, source: str, recv: str = 'Module("grunt")', name: str = "service.py"):
    path = app / name
    path.write_text(source)
    tree = ast.parse(source)
    sites = find_sites(path, tree, 0)
    types = {s.id: ("GruntDB" if "db" in ast.unparse(s.recv) else recv) for s in sites}
    classes = _Classes()
    classes.add(ORDER)
    rewriter = Rewriter(classes, _Controllers([app]))
    result = Result()
    out, n, _ = rewriter.rewrite_file(path, source, tree, sites, types, result)
    return out, n, result


def test_get_doc_by_literal_reads_by_class_and_imports_it(app: Path):
    out, n, _ = _rewrite(
        app,
        """\
import grunt


async def close(name: str) -> str | None:
    doc = await grunt.get_doc("Order", name, ignore_permissions=True)
    doc["status"] = "Closed"
    if doc.get("total"):
        return doc["status"]
    return doc.status
""",
    )
    assert n == 1
    assert out is not None
    assert "from shop.doctypes.Order.order import Order\n" in out
    assert "doc = await Order.get_doc(name, ignore_permissions=True)" in out
    assert 'doc.status = "Closed"' in out
    assert 'doc.get("total")' in out  # Document.get stays
    assert "return doc.status" in out and '["status"]' not in out


def test_get_list_drops_include_total_and_asks_for_name(app: Path):
    out, n, _ = _rewrite(
        app,
        """\
import grunt


async def names() -> list[str]:
    rows = await grunt.get_list(
        "Order", filters={"status": "Open"}, fields=["status"], include_total=False
    )
    out = []
    for r in rows:
        out.append(r["name"] + r.status)
    return out
""",
    )
    assert n == 1 and out is not None
    assert 'Order.get_list(\n        filters={"status": "Open"}, fields=["status", "name"]' in out
    assert "r.name + r.status" in out


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        # get_list is the API's shape: never returned or passed on
        ('    return await grunt.get_list("Order")', "returned"),
        ('    rows = await grunt.get_list("Order")\n    send(rows)', "passed on: Call"),
        ('    return [dict(r) for r in await grunt.get_list("Order")]', "passed on: Call"),
        # ISO datetimes, read formulas only through the facade
        ('    return [r.placed_on for r in await grunt.get_list("Order")]', "get_list: date read"),
        ('    return [r.label for r in await grunt.get_list("Order")]', "get_list: read formula"),
        ('    return len(await grunt.get_list("Order", search="x"))', "get_list arguments"),
        # a key the controller has an attribute of
        ('    return (await grunt.get_doc("Order", "1")).close', "key taken by the controller"),
        ('    d = await grunt.get_doc("Order", "1")\n    return d.items()', "dict method"),
        # the value goes on through `or`
        ('    d = (await grunt.get_doc("Order", "1")) or {}\n    return d', "passed on: BoolOp"),
        ('    d = await grunt.get_doc("Order", "1")\n    d = None\n    return d', "rebound"),
        ('    return await grunt.get_doc("Ghost", "1")', "no controller"),
    ],
)
def test_left_as_is(app: Path, body: str, reason: str):
    out, n, result = _rewrite(app, f"import grunt\n\n\nasync def f():\n{body}\n")
    assert n == 0 and out is None
    assert result.skipped[reason] == 1, result.skipped


def test_truth_tests_and_bool_ops_in_a_test_are_fine(app: Path):
    out, n, _ = _rewrite(
        app,
        """\
import grunt


async def f(n):
    d = await grunt.find_doc("Order", n)
    if d is None or not d.status:
        return None
    return d.total
""",
    )
    assert n == 1 and out is not None and "await Order.find_doc(n)" in out


def test_db_reads_take_the_class_and_constants_resolve(app: Path):
    out, n, result = _rewrite(
        app,
        """\
import grunt

ORDER = "Order"


async def f(n):
    total = 0
    for r in await grunt.db.get_all(ORDER, fields=["total"]):
        total += r["total"]
    row = await grunt.db.get_value(ORDER, n, ["status"], as_dict=True)
    names = await grunt.db.get_all(ORDER, pluck="name")
    st = await grunt.db.get_value(ORDER, n, "status")
    return total, row.status if row else None, names, st
""",
    )
    assert n == 2 and out is not None
    assert 'await grunt.db.get_all(Order, fields=["total"])' in out
    assert "total += r.total" in out
    assert 'await grunt.db.get_value(Order, n, ["status"], as_dict=True)' in out
    assert result.skipped["pluck"] == 1 and result.skipped["get_value without as_dict"] == 1


def test_another_receiver_stays(app: Path):
    source = 'async def f(ctx):\n    return (await ctx.get_doc("Order", "1")).status\n'
    out, n, result = _rewrite(app, source, recv="ServerScriptContext")
    assert out is None and result.skipped["receiver ServerScriptContext"] == 1


def test_import_cycle_is_reported_not_rewritten(app: Path):
    order = app / "doctypes" / "Order" / "order.py"
    order.write_text(ORDER + "\nfrom shop import service  # noqa\n")
    out, n, result = _rewrite(
        app, 'import grunt\n\n\nasync def f():\n    return (await grunt.get_doc("Order")).status\n'
    )
    assert out is None and result.skipped["import cycle"] == 1
    assert result.cycles and result.cycles[0].endswith("Order")


def _diag(source: str, needle: str, rule: str, message: str) -> dict:
    line = next(i for i, ln in enumerate(source.splitlines()) if needle in ln)
    col = source.splitlines()[line].index(needle)
    return {
        "rule": rule,
        "message": message,
        "range": {"start": {"line": line, "character": col}},
    }


def _fixer(source: str) -> _Fixer:
    classes = _Classes()
    classes.add(ORDER)
    return _Fixer(source, {"Order", "AttrDict", "Any"}, classes, _document_attrs())


def test_fixer_retypes_a_declared_row_type():
    source = """\
from grunt.utils.attr_dict import AttrDict


async def f() -> list[AttrDict]:
    rows: list[AttrDict] = await grunt.db.get_all(Order)
    return rows
"""
    fixer = _fixer(source)
    assert fixer.fix(
        _diag(
            source,
            "await grunt",
            "reportAssignmentType",
            'Type "list[Order]" is not assignable to declared type "list[AttrDict]"',
        )
    )
    assert fixer.fix(
        _diag(
            source,
            "return rows",
            "reportReturnType",
            'Type "list[Order]" is not assignable to return type "list[AttrDict]"',
        )
    )
    out = fixer.result()
    assert "-> list[Order]:" in out and "rows: list[Order] =" in out
    assert "AttrDict" not in out  # the import went with the last use


def test_fixer_keeps_none_and_refuses_a_row_mixed_with_a_dict():
    source = "async def f():\n    row: AttrDict | None = None\n    row = await g()\n"
    fixer = _fixer(source)
    assert fixer.fix(
        _diag(
            source,
            "await g",
            "reportAssignmentType",
            'Type "Order" is not assignable to declared type "AttrDict | None"',
        )
    )
    assert "row: Order | None = None" in fixer.result()
    mixed = _fixer(source)
    assert not mixed.fix(
        _diag(
            source,
            "await g",
            "reportAssignmentType",
            'Type "Order | dict[str, Any]" is not assignable to declared type "AttrDict | None"',
        )
    )


def test_fixer_turns_item_access_on_a_controller_into_attributes():
    source = (
        'def f(lines: list[Order]):\n    return [x["total"] for x in lines], lines[0]["close"]\n'  # noqa: E501
    )
    fixer = _fixer(source)
    msg = '"__getitem__" method not defined on type "Order"'
    assert fixer.fix(_diag(source, 'x["total"]', "reportIndexIssue", msg))
    assert not fixer.fix(_diag(source, 'lines[0]["close"]', "reportIndexIssue", msg))
    assert "[x.total for x in lines]" in fixer.result()
