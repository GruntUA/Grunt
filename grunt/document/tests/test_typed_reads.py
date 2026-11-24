"""Reads by controller class: ``Cls.get_list()``, ``grunt.db.get_all(Cls)``...
return documents of that class - typed for the IDE (``assert_type`` below is
checked by pyright in CI) and honest at run time (a row of a list holds only the
fields asked for and can't be saved)."""

import json
from datetime import datetime
from typing import Any, assert_type

import jinja2
import pytest

import grunt
from grunt.api.v1.meta import save_doctype
from grunt.document.base import Document
from grunt.document.document_list import DocumentList
from grunt.document.registry import document_registry
from grunt.document.serde import to_json
from grunt.utils.attr_dict import AttrDict
from tests.support import acting_as, make_user

TASK = {
    "name": "TrTask",
    "label": "Tr Task",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": 1},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
        {"fieldname": "cost", "label": "Cost", "fieldtype": "Float"},
    ],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
        {"role": "Viewer", "actions": ["read"], "hidden_fields": ["cost"]},
    ],
}


class TrTask(Document):
    title: str
    status: str | None = None
    cost: float | None = None


@pytest.fixture
async def tasks(ctx):
    await save_doctype(doctype_data={**TASK, "__is_new": True})
    previous = document_registry._controllers.get("TrTask")
    document_registry.register("TrTask", TrTask)
    try:
        for i in range(3):
            await TrTask.create(title=f"T{i}", status="Open", cost=float(i))
        yield ctx
    finally:
        if previous is None:
            document_registry._controllers.pop("TrTask", None)
            document_registry._bases.pop("TrTask", None)
        else:
            document_registry.register("TrTask", previous)


# The DocType of a class


def test_doctype_of_a_class():
    class Invoice(Document):
        pass

    class CustomInvoice(Invoice):  # an app's subclass of a controller
        pass

    assert Invoice.__doctype__ == "Invoice"
    assert CustomInvoice.__doctype__ == "Invoice"

    from grunt.metadata.doctypes.DocType.doc_type import DocTypeController

    assert DocTypeController.__doctype__ == "DocType"


# Rows built without __init__


def test_rows_of_a_list_are_partial():
    rows = TrTask._from_rows([{"name": "A", "title": "x"}], doctype="TrTask", partial=True)
    row = rows[0]
    assert isinstance(row, TrTask)
    assert row.title == "x" and row.name == "A" and row.doctype == "TrTask"
    with pytest.raises(AttributeError, match="TrTask.status was not read"):
        _ = row.status


def test_system_fields_of_a_partial_row():
    row = TrTask._from_rows([{"name": "A", "title": "x"}], partial=True)[0]
    assert row.name == "A" and row.id == "A"
    with pytest.raises(AttributeError, match="TrTask.owner was not read"):
        _ = row.owner
    with pytest.raises(AttributeError):
        _ = row.idx
    whole = TrTask(title="x")
    assert whole.owner is None and whole.idx == 0


def test_a_whole_document_reads_a_missing_field_as_none():
    doc = TrTask(title="x")
    assert doc.status is None


def test_a_name_that_is_no_field_raises():
    doc = TrTask(title="x")
    with pytest.raises(AttributeError, match="TrTask has no field 'titel'"):
        _ = doc.titel


def test_the_doctype_decides_once_the_document_has_it():
    class Meta:
        @staticmethod
        def has_field(name: str) -> bool:
            return name == "custom_note"  # e.g. a field another app adds

    doc = TrTask(title="x")
    doc._dt = Meta()
    assert doc.custom_note is None
    with pytest.raises(AttributeError):
        _ = doc.status  # not in this (made-up) DocType


def test_a_controller_without_annotations_knows_no_fields():
    class Bare(Document):
        pass

    assert Bare().anything is None


def test_attrdict_missing_key_in_jinja():
    tpl = jinja2.Environment(autoescape=True).from_string(
        "{{ r.a }}|{{ r.b is defined }}|{{ r.b | default('-') }}"
    )
    assert tpl.render(r=AttrDict(a=1)) == "1|False|-"


def test_hidden_fields_read_as_none():
    row = TrTask._from_rows([{"name": "A"}], partial=True, hidden=frozenset({"cost"}))[0]
    assert row.cost is None


async def test_a_partial_row_cannot_be_saved():
    row = TrTask._from_rows([{"name": "A", "title": "x"}], partial=True)[0]
    with pytest.raises(ValueError, match="row of a list"):
        await row.save()
    with pytest.raises(ValueError, match="row of a list"):
        await row.insert()


# Through the API


@pytest.mark.usefixtures("tasks")
async def test_db_get_all_by_class():
    rows = await grunt.db.get_all(TrTask, fields=["name", "title"], order_by="title", order="asc")
    assert_type(rows, list[TrTask])
    assert [type(r) for r in rows] == [TrTask] * 3
    assert [r.title for r in rows] == ["T0", "T1", "T2"]
    with pytest.raises(AttributeError):
        _ = rows[0].status

    titles = await grunt.db.get_all(TrTask, pluck="title", order_by="title", order="asc")
    assert_type(titles, list[Any])
    assert titles == ["T0", "T1", "T2"]

    plain = await grunt.db.get_all("TrTask", fields=["name"])
    assert_type(plain, list[AttrDict])
    assert all(type(r) is AttrDict for r in plain)


@pytest.mark.usefixtures("tasks")
async def test_db_get_doc_and_get_value_by_class():
    name = (await grunt.db.get_all(TrTask, fields=["name"], limit=1))[0].name
    assert name is not None

    row = await grunt.db.get_doc(TrTask, name)
    assert_type(row, TrTask | None)
    assert isinstance(row, TrTask) and row.status == "Open"

    values = await grunt.db.get_value(TrTask, name, ["title"], as_dict=True)
    assert_type(values, TrTask | None)
    assert values is not None and values.title.startswith("T")
    with pytest.raises(AttributeError):
        _ = values.status

    assert await grunt.db.get_doc(TrTask, "missing") is None


@pytest.mark.usefixtures("tasks")
async def test_get_list_by_class():
    page = await TrTask.get_list(fields=["name", "title", "modified_at"], limit=2)
    assert_type(page, list[TrTask])
    assert len(page) == 2 and all(isinstance(r, TrTask) for r in page)
    assert isinstance(page[0].modified_at, datetime)  # stored values, not the API's strings
    with pytest.raises(ValueError, match="row of a list"):
        await page[0].save()

    found = await TrTask.find_doc("missing")
    assert_type(found, TrTask | None)
    assert found is None

    by_name = await grunt.get_list("TrTask", fields=["name"])
    assert_type(by_name, DocumentList[AttrDict])
    assert all(type(r) is AttrDict for r in by_name)


@pytest.mark.usefixtures("tasks")
async def test_get_list_by_class_masks_hidden_fields():
    viewer = make_user("viewer@x.com", roles=["Viewer"])
    with acting_as(viewer):
        rows = await TrTask.get_list(fields=["name", "title", "cost"])
    assert rows and all(r.cost is None for r in rows)
    assert all("cost" not in r.data for r in rows)


@pytest.mark.usefixtures("tasks")
async def test_get_doc_by_class_saves():
    name = (await grunt.db.get_all(TrTask, fields=["name"], limit=1))[0].name
    assert name is not None
    doc = await TrTask.get_doc(name)
    assert_type(doc, TrTask)
    doc.status = "Closed"
    await doc.save()
    assert (await grunt.db.get_value("TrTask", name, "status")) == "Closed"


@pytest.mark.usefixtures("tasks")
async def test_registered_subclass_is_used():
    class Extended(TrTask):
        def label(self) -> str:
            return f"[{self.title}]"

    document_registry.register("TrTask", Extended)
    rows = await grunt.db.get_all(TrTask, fields=["name", "title"], limit=1)
    assert type(rows[0]) is Extended


# JSON and templates


def test_json_of_a_document():
    doc = TrTask(title="x")
    assert json.loads(to_json({"doc": doc}))["doc"]["title"] == "x"
    with pytest.raises(TypeError, match="not JSON serializable"):
        to_json({"x": object()})


def test_jinja_sees_unread_fields_as_undefined():
    row = TrTask._from_rows([{"name": "A", "title": "x"}], partial=True)[0]
    tpl = jinja2.Environment(autoescape=True).from_string(
        "{{ r.title }}|{{ r.status is defined }}|{{ r.status | default('-') }}"
    )
    assert tpl.render(r=row) == "x|False|-"
