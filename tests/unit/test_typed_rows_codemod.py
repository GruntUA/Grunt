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
    _Controller,
    _Controllers,
    _dependency_roots,
    _Fixer,
    _row_type_to,
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


def test_dependency_apps_are_searched_transitively(tmp_path: Path):
    def app(name: str, *deps: str) -> Path:
        root = tmp_path / name
        root.mkdir()
        listed = ", ".join(f'"{d}"' for d in deps)
        (root / "pyproject.toml").write_text(
            f"[project]\nname = '{name}'\n\n[tool.grunt]\ndepends_on = [{listed}]\n"
        )
        return root

    portal = app("portal", "cms", "grunt", "absent")
    cms = app("cms", "media")
    media = app("media", "portal")  # a loop back stays harmless
    app("hrm")
    assert _dependency_roots(portal) == [cms.resolve(), media.resolve()]


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


def test_row_type_to_replaces_the_row_inside_its_container():
    assert _row_type_to("dict[str, Any] | None", "Order") == "Order | None"
    assert _row_type_to("Sequence[dict[str, list[str]]]", "Order") == "Sequence[Order]"
    assert _row_type_to("list[AttrDict]", "Order") == "list[Order]"
    assert _row_type_to("str", "Order") is None


def test_fixer_retypes_the_parameter_a_row_is_passed_to():
    source = """\
from typing import Any


def label(row: dict[str, Any]) -> str:
    return row["status"]


class Report:
    def lines(self, rows: Sequence[AttrDict]) -> None: ...

    async def run(self, order) -> None:
        label(order)
        self.lines([order])
        print(order)
"""
    fixer = _fixer(source)
    arg = 'Argument of type "{}" cannot be assigned to parameter "{}" of type "x" in function "{}"'
    assert fixer.fix(
        _diag(source, "label(order)", "reportArgumentType", arg.format("Order", "row", "label"))
    )
    rows = arg.format("list[Order]", "rows", "lines")
    assert fixer.fix(_diag(source, "self.lines", "reportArgumentType", rows))
    assert not fixer.fix(  # not a function of this file
        _diag(source, "print(order)", "reportArgumentType", arg.format("Order", "x", "print"))
    )
    out = fixer.result()
    assert "def label(row: Order) -> str:" in out
    assert "def lines(self, rows: Sequence[Order])" in out


def test_fixer_imports_a_class_the_new_type_names():
    source = "import grunt\n\n\nasync def f() -> list[AttrDict]:\n    return await g()\n"
    classes = _Classes()
    classes.add(ORDER)
    msg = 'Type "list[Order]" is not assignable to return type "list[AttrDict]"'
    diag = _diag(source, "return", "reportReturnType", msg)
    cyclic = _Fixer(source, {"AttrDict"}, classes, _document_attrs(), importer=lambda n: None)
    assert not cyclic.fix(diag)
    fixer = _Fixer(
        source, {"AttrDict"}, classes, _document_attrs(), importer=lambda n: "shop.order"
    )
    assert fixer.fix(diag)
    out = fixer.result()
    assert "from shop.order import Order\n" in out and "-> list[Order]:" in out


def test_fixer_refuses_two_classes_for_one_parameter():
    source = (
        "def label(row: dict[str, Any]) -> str: ...\n\n\ndef f(o, i):\n    label(o)\n    label(i)\n"
    )
    classes = _Classes()
    classes.add(ORDER)
    classes.add(ORDER.replace("class Order", "class Invoice"))
    fixer = _Fixer(source, {"Order", "Invoice", "Any"}, classes, _document_attrs())
    arg = (
        'Argument of type "{}" cannot be assigned to parameter "row" of type "x"'
        ' in function "label"'
    )
    assert fixer.fix(_diag(source, "label(o)", "reportArgumentType", arg.format("Order")))
    assert fixer.fix(_diag(source, "label(o)", "reportArgumentType", arg.format("Order")))  # same
    assert not fixer.fix(_diag(source, "label(i)", "reportArgumentType", arg.format("Invoice")))
    assert "def label(row: Order) -> str:" in fixer.result()


def test_a_dependency_app_importing_this_one_back_is_a_cycle(tmp_path: Path):
    cms = tmp_path / "cms"
    (cms / "doctypes" / "Page").mkdir(parents=True)
    (cms / "__init__.py").write_text("")
    page = cms / "doctypes" / "Page" / "page.py"
    page.write_text("class Page: ...\n")
    ctrl = _Controller("Page", "cms.doctypes.Page.page", page, cms, {})
    reader = tmp_path / "portal" / "reader.py"
    assert not Rewriter._cycle(reader, "portal.reader", ctrl)
    assert Rewriter._cycle(tmp_path / "grunt" / "x.py", "grunt.x", ctrl)  # the core never
    hooks = tmp_path / "cms2"
    (hooks / "doctypes" / "Page").mkdir(parents=True)
    (hooks / "__init__.py").write_text("")
    back = hooks / "doctypes" / "Page" / "page.py"
    back.write_text("lazy from portal.reader import read\n\n\nclass Page: ...\n")
    ctrl2 = _Controller("Page", "cms2.doctypes.Page.page", back, hooks, {})
    assert Rewriter._cycle(reader, "portal.reader", ctrl2)


def test_two_files_of_one_run_do_not_import_each_other(app: Path):
    """The import graph on disk has neither import yet: the first one added in
    the run makes the second a cycle."""
    folder = app / "doctypes" / "Invoice"
    folder.mkdir()
    invoice = folder / "invoice.py"
    invoice.write_text(ORDER.replace("Order", "Invoice"))
    (folder / "Invoice.json").write_text(json.dumps({**ORDER_JSON, "name": "Invoice"}))
    order = app / "doctypes" / "Order" / "order.py"
    classes = _Classes()
    classes.add(ORDER)
    classes.add(ORDER.replace("Order", "Invoice"))
    rewriter = Rewriter(classes, _Controllers([app]))
    result = Result()

    def rewrite(path: Path, other: str) -> str | None:
        source = path.read_text() + (
            f"\n\nasync def peer(n: str):\n    return (await grunt.get_doc({other!r}, n)).status\n"
        )
        source = "import grunt\n" + source
        tree = ast.parse(source)
        sites = find_sites(path, tree, 0)
        types = {s.id: 'Module("grunt")' for s in sites}
        out, _, _ = rewriter.rewrite_file(path, source, tree, sites, types, result)
        return out

    first = rewrite(order, "Invoice")
    assert first is not None and "from shop.doctypes.Invoice.invoice import Invoice" in first
    assert rewrite(invoice, "Order") is None
    assert result.skipped["import cycle"] == 1
    assert result.cycles[0].endswith("Order")
