"""A document is a JSON object that names its own DocType.

``grunt.get_doc`` / ``new_doc`` / ``save_doc`` return ``{"doctype": ..., ...}``
with every child row naming its DocType too, and that JSON is enough to build
the document again: ``grunt.get_doc(data)`` gives an unsaved controller.
"""

from __future__ import annotations

import json

import pytest

_PARENT = {
    "name": "JsDoc",
    "label": "Js Doc",
    "module": "core",
    "autoname": "field:code",
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "rows", "label": "Rows", "fieldtype": "Table", "options": "JsDocRow"},
    ],
}

_CHILD = {
    "name": "JsDocRow",
    "label": "Js Doc Row",
    "module": "core",
    "is_child": True,
    "fields": [{"fieldname": "label", "label": "Label", "fieldtype": "Data"}],
}


@pytest.fixture
async def js_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_CHILD, "__is_new": True})
    await save_doctype(doctype_data={**_PARENT, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_documents_name_their_doctype(ctx, js_doctype):
    created = await ctx.new_doc("JsDoc", {"code": "a", "rows": [{"label": "x"}]})
    assert next(iter(created)) == "doctype"
    assert created["doctype"] == "JsDoc"

    doc = await ctx.get_doc("JsDoc", "a")
    assert next(iter(doc)) == "doctype"
    assert doc["doctype"] == "JsDoc"
    assert [r["doctype"] for r in doc["rows"]] == ["JsDocRow"]

    saved = await ctx.save_doc("JsDoc", "a", {"title": "T"})
    assert saved["doctype"] == "JsDoc"
    assert [r["doctype"] for r in saved["rows"]] == ["JsDocRow"]


@pytest.mark.asyncio
async def test_get_doc_from_json_builds_an_unsaved_controller(ctx, js_doctype):
    from grunt.document.base import BaseDocument

    doc = await ctx.get_doc({"doctype": "JsDoc", "code": "b", "rows": [{"label": "y"}]})
    assert isinstance(doc, BaseDocument)
    assert doc.doctype == "JsDoc"
    assert await ctx.find_doc("JsDoc", "b") is None

    await doc.insert()
    stored = await ctx.get_doc("JsDoc", "b")
    assert [r["label"] for r in stored["rows"]] == ["y"]


@pytest.mark.asyncio
async def test_document_json_round_trips(ctx, js_doctype):
    await ctx.new_doc("JsDoc", {"code": "c", "title": "Original", "rows": [{"label": "z"}]})
    controller = await ctx.get_doc_instance("JsDoc", "c")

    data = json.loads(controller.as_json())
    assert data["doctype"] == "JsDoc"
    assert data["rows"][0]["doctype"] == "JsDocRow"

    data.update(name="c2", code="c2")
    await (await ctx.get_doc(data)).insert()
    copy = await ctx.get_doc("JsDoc", "c2")
    assert copy["title"] == "Original"
    assert [r["label"] for r in copy["rows"]] == ["z"]


@pytest.mark.asyncio
async def test_get_doc_from_json_needs_a_doctype(ctx):
    with pytest.raises(ValueError):
        await ctx.get_doc({"name": "x"})


def test_doctype_is_a_reserved_fieldname():
    from grunt.metadata.doctype import DocType

    with pytest.raises(ValueError, match="reserved"):
        DocType.model_validate(
            {
                "name": "Bad",
                "label": "Bad",
                "module": "core",
                "fields": [{"fieldname": "doctype", "label": "DocType", "fieldtype": "Data"}],
            }
        )
