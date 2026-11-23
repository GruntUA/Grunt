"""Documents and rows read through grunt come back as ``AttrDict`` (``doc.status``)."""

import copy
import json
import pickle

import pytest

from grunt.utils.attr_dict import AttrDict, as_row, as_rows

ORDER = {
    "name": "AttrOrder",
    "label": "Attr Order",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
        {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "AttrOrderLine"},
    ],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
    ],
}

LINE = {
    "name": "AttrOrderLine",
    "label": "Attr Order Line",
    "module": "core",
    "is_child": True,
    "fields": [{"fieldname": "qty", "label": "Qty", "fieldtype": "Int"}],
}


# AttrDict itself


def test_attribute_access_reads_and_writes_keys():
    d = AttrDict({"a": 1})
    assert d.a == 1
    assert d.missing is None
    d.b = 2
    assert d["b"] == 2
    del d.b
    assert "b" not in d
    with pytest.raises(AttributeError):
        del d.b


def test_still_a_plain_dict_for_json_copy_and_pickle():
    d = AttrDict({"a": 1, "rows": [AttrDict({"q": 2})]})
    assert isinstance(d, dict)
    assert json.loads(json.dumps(d)) == {"a": 1, "rows": [{"q": 2}]}
    # Round-trips an object built right here - no untrusted data.
    for clone in (copy.copy(d), copy.deepcopy(d), pickle.loads(pickle.dumps(d)), d.copy()):
        assert type(clone) is AttrDict
        assert clone == d
    assert type(copy.deepcopy(d)["rows"][0]) is AttrDict


def test_dict_methods_win_over_same_named_keys():
    d = AttrDict({"items": [1]})
    assert callable(d.items)
    assert d["items"] == [1]


def test_as_row_keeps_an_attrdict_and_converts_child_rows():
    d = AttrDict({"lines": [{"qty": 1}, "x"]})
    assert as_row(d) is d
    assert d.lines[0].qty == 1
    assert d.lines[1] == "x"

    plain = {"a": 1}
    row = as_row(plain)
    assert type(row) is AttrDict and row.a == 1

    rows = [{"a": 1}, AttrDict({"a": 2})]
    assert as_rows(rows) is rows
    assert [r.a for r in rows] == [1, 2]


# Through the API


@pytest.fixture
async def orders(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LINE, "__is_new": True})
    await save_doctype(doctype_data={**ORDER, "__is_new": True})
    return ctx


async def test_document_api_returns_attrdicts(orders):
    grunt = orders
    doc = await grunt.new_doc("AttrOrder", {"title": "First", "lines": [{"qty": 3}]})
    assert type(doc) is AttrDict
    assert doc.title == "First"

    got = await grunt.get_doc("AttrOrder", doc.name)
    assert type(got) is AttrDict
    assert got.title == "First"
    assert got.lines[0].qty == 3

    saved = await grunt.save_doc("AttrOrder", doc.name, {"status": "Closed"})
    assert saved.status == "Closed"

    found = await grunt.find_doc("AttrOrder", doc.name)
    assert found is not None and found.status == "Closed"

    page = await grunt.get_list("AttrOrder", fields=["name", "title"])
    assert [r.title for r in page] == ["First"]


async def test_db_api_returns_attrdicts(orders):
    grunt = orders
    doc = await grunt.new_doc("AttrOrder", {"title": "Second"})

    rows = await grunt.db.get_all("AttrOrder", fields=["name", "title"])
    assert [r.title for r in rows] == ["Second"]
    assert all(type(r) is AttrDict for r in rows)
    assert await grunt.db.get_all("AttrOrder", pluck="title") == ["Second"]

    row = await grunt.db.get_doc("AttrOrder", doc.name)
    assert row is not None and row.title == "Second"

    values = await grunt.db.get_values("AttrOrder", doc.name, ["title"])
    assert values is not None and values.title == "Second"

    whole = await grunt.db.get_value("AttrOrder", doc.name, "*")
    assert whole is not None and whole.title == "Second"


def test_as_row_reaches_into_attrdict_children():
    row = as_row({"lines": [AttrDict({"parts": [{"qty": 1}]})]})
    assert row.lines[0].parts[0].qty == 1
