"""Child tables typed ``list[ChildCls]`` in the types block hold documents of the
child controller while code of the controller holds the document - each over
its row dict, so a field set on a child is set on the row. Below the controller
(validation, the store, the API, hooks of other apps) the rows stay dicts.
``assert_type`` below is checked by pyright in CI."""

import json
from typing import Any, assert_type

import pytest
from fastapi import HTTPException

import grunt
from grunt.api.v1.meta import save_doctype
from grunt.document.base import Document
from grunt.document.registry import document_registry
from grunt.errors import throw
from grunt.events import subscribe, unsubscribe
from grunt.utils.attr_dict import AttrDict

LINE = {
    "name": "TcLine",
    "label": "Tc Line",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "item", "label": "Item", "fieldtype": "Data"},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Int"},
    ],
}

NOTE = {
    "name": "TcNote",
    "label": "Tc Note",
    "module": "core",
    "is_child": True,
    "fields": [{"fieldname": "text", "label": "Text", "fieldtype": "Data"}],
}

ORDER = {
    "name": "TcOrder",
    "label": "Tc Order",
    "module": "core",
    "autoname": "field:code",
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": 1},
        {"fieldname": "total", "label": "Total", "fieldtype": "Int"},
        {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "TcLine"},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Table", "options": "TcNote"},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "write", "create", "delete"]}],
}


class TcLine(Document):
    item: str | None = None
    qty: int | None = None


class TcOrder(Document):
    code: str
    total: int | None = None
    lines: list[TcLine] = []
    notes: list[dict] = []  # not typed with a class: rows stay dicts

    async def validate(self) -> None:
        seen.append([type(r) for r in self.lines or []])
        if any((r.qty or 0) < 0 for r in self.lines or []):
            throw("A negative quantity")
        for row in self.lines or []:
            if row.item == "double":
                row.qty = (row.qty or 0) * 2
        if self.code == "extra":
            self.lines = [*(self.lines or []), TcLine(item="added", qty=5)]
        self.total = sum(r.qty or 0 for r in self.lines or [])


seen: list[list[type]] = []


@pytest.fixture
async def orders(ctx):
    await save_doctype(doctype_data={**LINE, "__is_new": True})
    await save_doctype(doctype_data={**NOTE, "__is_new": True})
    await save_doctype(doctype_data={**ORDER, "__is_new": True})
    registered = {"TcOrder": TcOrder, "TcLine": TcLine}
    previous = {name: document_registry._controllers.get(name) for name in registered}
    for name, cls in registered.items():
        document_registry.register(name, cls)
    seen.clear()
    try:
        yield ctx
    finally:
        for name, cls in previous.items():
            if cls is None:
                document_registry._controllers.pop(name, None)
                document_registry._bases.pop(name, None)
            else:
                document_registry.register(name, cls)


# Without a database


def test_constructor_rows_become_child_documents():
    order = TcOrder(code="a", lines=[{"item": "x", "qty": 1}], notes=[{"text": "n"}])  # pyright: ignore[reportArgumentType] - rows as dicts
    assert_type(order.lines, list[TcLine])
    line = order.lines[0]
    assert isinstance(line, TcLine)
    assert line.item == "x" and line.doctype == "TcLine"
    assert isinstance(order.notes[0], dict)  # list[dict] - left as it is


def test_a_child_is_its_row():
    row = {"item": "x", "qty": 1}
    order = TcOrder(code="a", lines=[row])  # pyright: ignore[reportArgumentType] - rows as dicts
    order.lines[0].qty = 3
    assert row["qty"] == 3


def test_assigned_rows_become_child_documents():
    order = TcOrder(code="a")
    order.lines = [{"item": "x"}, TcLine(item="y")]  # pyright: ignore[reportAttributeAccessIssue]
    assert [type(r) for r in order.lines] == [TcLine, TcLine]
    assert [r.item for r in order.lines] == ["x", "y"]


def test_as_dict_and_json_hold_rows():
    order = TcOrder(code="a", lines=[TcLine(item="x", qty=1)])
    order.lines.append(TcLine(item="y"))
    data = order.as_dict()
    assert data["lines"] == [{"item": "x", "qty": 1}, {"item": "y"}]
    assert all(type(r) is dict for r in data["lines"])
    assert json.loads(order.as_json())["lines"][1] == {"item": "y"}


def test_rows_of_a_document_built_from_rows():
    (order,) = TcOrder._from_rows([{"name": "a", "code": "a", "lines": [{"item": "x"}]}])
    assert isinstance(order.lines[0], TcLine)


def test_a_child_named_by_string_is_looked_up_in_the_registry():
    class TcForward(Document):
        lines: list[TcNamed] = []  # noqa: F821  # pyright: ignore[reportUndefinedVariable] - as under TYPE_CHECKING

    doc = TcForward(lines=[{"item": "x"}])  # pyright: ignore[reportArgumentType]
    # No controller registered for "TcNamed": the base class, still a document.
    assert isinstance(doc.lines[0], Document)
    assert doc.lines[0].doctype == "TcNamed"


# Through the pipeline


@pytest.mark.asyncio
async def test_hooks_see_child_documents_and_their_changes_are_stored(orders):
    order = TcOrder(code="a", lines=[TcLine(item="double", qty=2), TcLine(item="x", qty=1)])
    result = await order.insert()

    assert seen == [[TcLine, TcLine]]
    stored = await TcOrder.get_doc("a")
    assert [(r.item, r.qty) for r in stored.lines] == [("double", 4), ("x", 1)]
    assert stored.total == 5
    # The row the pipeline returns is rows; the document, child documents again.
    assert all(isinstance(r, dict) for r in result["lines"])
    assert all(isinstance(r, TcLine) for r in order.lines)


@pytest.mark.asyncio
async def test_a_child_appended_in_a_hook_is_stored(orders):
    await TcOrder(code="extra", lines=[TcLine(item="x", qty=1)]).insert()
    stored = await TcOrder.get_doc("extra")
    assert [(r.item, r.qty) for r in stored.lines] == [("x", 1), ("added", 5)]


@pytest.mark.asyncio
async def test_read_by_class_change_a_child_and_save(orders):
    await TcOrder(code="a", lines=[TcLine(item="x", qty=1), TcLine(item="y", qty=2)]).insert()

    order = await TcOrder.get_doc("a")
    assert_type(order.lines, list[TcLine])
    order.lines[0].qty = 10
    order.lines.pop()
    order.lines.append(TcLine(item="z", qty=3))
    await order.save()

    stored = await TcOrder.get_doc("a")
    assert [(r.item, r.qty) for r in stored.lines] == [("x", 10), ("z", 3)]
    assert stored.total == 13


@pytest.mark.asyncio
async def test_reads_by_name_and_hooks_of_other_apps_get_rows(orders):
    received: list[Any] = []

    @subscribe("test_typed_children", events={"after_insert"})
    async def _listen(doctype: str, doc: dict[str, Any], **_: Any) -> None:
        if doctype == "TcOrder":
            received.append(doc["lines"])

    try:
        await TcOrder(code="a", lines=[TcLine(item="x", qty=1)]).insert()
    finally:
        unsubscribe("test_typed_children")

    doc = await grunt.get_doc("TcOrder", "a")
    assert isinstance(doc.lines[0], AttrDict)
    assert received and all(type(r) is not TcLine for r in received[0])


@pytest.mark.asyncio
async def test_new_doc_with_child_documents(orders):
    created = await grunt.new_doc("TcOrder", {"code": "a", "lines": [TcLine(item="x", qty=2)]})
    assert isinstance(created.lines[0], dict)
    stored = await TcOrder.get_doc("a")
    assert [(r.item, r.qty) for r in stored.lines] == [("x", 2)]


@pytest.mark.asyncio
async def test_save_doc_with_child_documents(orders):
    await TcOrder(code="a", lines=[TcLine(item="x", qty=1)]).insert()
    order = await TcOrder.get_doc("a")
    order.lines[0].qty = 7
    await grunt.save_doc("TcOrder", "a", {"lines": order.lines})
    stored = await TcOrder.get_doc("a")
    assert [(r.item, r.qty) for r in stored.lines] == [("x", 7)]


def test_string_annotations_type_children_too():
    from grunt.document.tests.typed_children_future import FutLine, FutOrder

    doc = FutOrder(lines=[{"qty": 1}], named=[{"qty": 2}], notes=[{"qty": 3}])  # pyright: ignore[reportArgumentType]
    assert isinstance(doc.lines[0], FutLine)
    assert isinstance(doc.named[0], Document) and doc.named[0].doctype == "FutNamed"
    assert type(doc.notes[0]) is dict


def test_update_wraps_child_rows():
    order = TcOrder(code="a")
    order.update({"lines": [{"item": "x"}]})
    assert isinstance(order.lines[0], TcLine)


@pytest.mark.asyncio
async def test_a_rejected_save_keeps_child_documents(orders):
    await TcOrder(code="a", lines=[TcLine(item="x", qty=1)]).insert()
    order = await TcOrder.get_doc("a")
    order.lines[0].qty = -1  # the validate hook refuses it
    with pytest.raises(HTTPException):
        await order.save()
    assert isinstance(order.lines[0], TcLine)
    order.lines[0].qty = 9
    await order.save()
    assert [(r.item, r.qty) for r in (await TcOrder.get_doc("a")).lines] == [("x", 9)]
