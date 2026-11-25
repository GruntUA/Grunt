"""Controllers as constructors: ``Order(title=...)`` / ``await Order.create(...)``.

The generated annotations type them (``Document`` is a ``dataclass_transform``);
the ``= None`` / ``= []`` defaults are for the type checker only.
"""

import pytest
from fastapi import HTTPException

from grunt.document.base import Document
from grunt.utils.codegen import _render_type_block
from tests.support import make_user

ORDER = {
    "name": "CtorOrder",
    "label": "Ctor Order",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
    ],
}


class CtorOrder(Document):
    title: str
    status: str | None = None
    lines: list[dict] = []


def test_defaults_do_not_hide_data():
    assert "status" not in CtorOrder.__dict__
    assert "lines" not in CtorOrder.__dict__
    doc = CtorOrder(title="First", status="Open")
    assert doc.status == "Open"
    assert CtorOrder(title="x").status is None


def test_constructor_sets_doctype_and_data():
    doc = CtorOrder(title="First")
    assert doc.doctype == "CtorOrder"
    assert doc.data == {"title": "First"}
    assert doc.title == "First"


def test_old_positional_form_still_works():
    data = {"title": "x"}
    doc = Document("CtorOrder", data)
    assert doc.doctype == "CtorOrder"
    assert doc.data is data


def test_existing_row_unpacks_into_the_constructor():
    row = {"title": "x", "name": "CO-1", "doctype": "CtorOrder"}
    doc = CtorOrder(**row)
    assert type(doc) is CtorOrder
    assert doc.doctype == "CtorOrder"
    assert doc.data == {"title": "x", "name": "CO-1"}


def test_private_class_attributes_stay():
    class WithState(Document):
        _prev: dict | None = None

    assert WithState.__dict__["_prev"] is None


@pytest.fixture
async def orders(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ORDER, "__is_new": True})
    return ctx


async def test_insert_and_create(orders):
    doc = CtorOrder(title="First")
    await doc.insert()
    assert doc.name

    created = await CtorOrder.create(title="Second", status="Open")
    assert type(created) is CtorOrder
    assert created.name
    stored = await orders.get_doc("CtorOrder", created.name)
    assert stored.status == "Open"


async def test_create_checks_create_permission(orders, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, make_user("nobody@grunt.example.com", roles=[])):
        with pytest.raises(HTTPException) as exc:
            await CtorOrder.create(title="x")
    assert exc.value.status_code == 403


def test_generated_block_marks_optional_fields():
    block = _render_type_block(
        [
            {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
            {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
            {
                "fieldname": "code",
                "label": "Code",
                "fieldtype": "Data",
                "required": True,
                "default": "A",
            },
            {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "Line"},
        ]
    )
    assert "    title: str  # Title" in block
    assert "    status: str | None = None  # Status" in block
    assert "    code: str | None = None  # Code" in block
    assert "    lines: list[dict] = []  # Table: Line" in block


def test_registered_controller_is_used_with_or_without_doctype():
    from grunt.document.registry import document_registry

    class ExtendedOrder(CtorOrder):
        pass

    document_registry.register("CtorOrder", ExtendedOrder)
    try:
        assert type(CtorOrder(title="x")) is ExtendedOrder
        assert type(CtorOrder("CtorOrder", {"title": "x"})) is ExtendedOrder
        assert type(CtorOrder(doctype="CtorOrder", data={})) is ExtendedOrder
        assert type(Document("CtorOrder", {})) is Document
    finally:
        document_registry._forget("CtorOrder")


def test_required_child_table_has_no_default():
    block = _render_type_block(
        [{"fieldname": "lines", "fieldtype": "Table", "options": "Line", "required": True}]
    )
    assert "    lines: list[dict]  # Table: Line" in block


def test_scaffold_types_required_fields_like_sync_types():
    from grunt.metadata.field import DocField
    from grunt.metadata.scaffold import _build_scaffold_context

    ctx = _build_scaffold_context(
        "CtorOrder",
        [
            DocField(fieldname="title", fieldtype="Data", required=True),
            DocField(fieldname="note", fieldtype="Data"),
            DocField(fieldname="lines", fieldtype="Table", options="Line", required=True),
        ],
    )
    block = ctx["type_block"]
    assert "    title: str\n" in block
    assert "    note: str | None = None\n" in block
    assert "    lines: list[dict]  # Table: Line\n" in block  # required: no default
