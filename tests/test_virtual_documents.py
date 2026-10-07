"""Virtual DocTypes through the public facade: list, count, read, create,
update and delete go to the controller, and the document events fire around
them just as for a table-backed DocType."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_filters, apply_search, apply_sort, build_response
from grunt.events import subscribe, unsubscribe

DOCTYPE = "VirtualNote"


class _Notes(BaseDocument):
    store: dict[str, dict[str, Any]] = {}

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        rows = [dict(r) for r in cls.store.values()]
        if filters:
            rows = apply_filters(rows, filters)
        if search:
            rows = apply_search(rows, search, ["title"])
        rows = apply_sort(rows, sort_by if sort_by != "modified_at" else "name", sort_order)
        return build_response(rows, page, per_page)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        if self.name not in self.store:
            raise HTTPException(404, "not found")
        self.data = dict(self.store[str(self.name)])

    async def db_insert(self) -> None:
        row = {"name": self.name, "title": self.title, "rank": self.rank or 0}
        self.store[row["name"]] = row
        self.data = dict(row)

    async def db_update(self) -> None:
        self.store[str(self.name)].update({"title": self.title, "rank": self.rank})
        self.data = dict(self.store[str(self.name)])

    async def db_delete(self) -> None:
        self.store.pop(str(self.name), None)


@pytest.fixture
async def notes(ctx):
    from grunt.api.v1.meta import save_doctype
    from grunt.document.registry import document_registry

    await save_doctype(
        doctype_data={
            "name": DOCTYPE,
            "label": "Virtual Note",
            "module": "core",
            "is_virtual": True,
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
                {"fieldname": "rank", "label": "Rank", "fieldtype": "Int"},
            ],
            "__is_new": True,
        }
    )
    _Notes.store = {
        "a": {"name": "a", "title": "Alpha", "rank": 1},
        "b": {"name": "b", "title": "Beta", "rank": 2},
        "c": {"name": "c", "title": "Gamma", "rank": 3},
    }
    document_registry.register(DOCTYPE, _Notes)
    try:
        yield _Notes.store
    finally:
        document_registry._controllers.pop(DOCTYPE, None)


@pytest.fixture
def events():
    seen: list[tuple[str, str | None]] = []

    @subscribe("test_virtual_events")
    async def _record(event: str, doctype: str, doc: Any = None, **kwargs: Any) -> None:
        if doctype == DOCTYPE:
            name = doc.get("name") or doc.get("id") if isinstance(doc, dict) else None
            seen.append((event, name))

    try:
        yield seen
    finally:
        unsubscribe("test_virtual_events")


@pytest.mark.asyncio
async def test_list_filters_searches_sorts_and_pages(ctx, notes):
    page = await ctx.get_list(DOCTYPE, order_by="rank", order="asc", limit=2)
    assert [r["name"] for r in page] == ["a", "b"]
    assert page.meta["total"] == 3

    assert [r["name"] for r in await ctx.get_list(DOCTYPE, filters={"rank__gte": 2})] == [
        "c",
        "b",
    ]
    assert [r["name"] for r in await ctx.get_list(DOCTYPE, search="gam")] == ["c"]


@pytest.mark.asyncio
async def test_count_comes_from_the_controller(ctx, notes):
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.document.collection import count_documents

    assert await count_documents(ctx.get_session(), DOCTYPE, SYSTEM_USER) == 3
    assert await ctx.count(DOCTYPE, respect_permissions=True) == 3


@pytest.mark.asyncio
async def test_get_doc_reads_the_controller(ctx, notes):
    assert (await ctx.get_doc(DOCTYPE, "b"))["title"] == "Beta"
    assert await ctx.find_doc(DOCTYPE, "missing") is None


@pytest.mark.asyncio
async def test_create_update_delete_go_to_the_controller(ctx, notes, events):
    created = await ctx.new_doc(DOCTYPE, {"name": "d", "title": "Delta"})
    assert created["title"] == "Delta"
    assert notes["d"]["title"] == "Delta"

    updated = await ctx.save_doc(DOCTYPE, "d", {"title": "Delta 2"})
    assert updated["title"] == "Delta 2"
    assert notes["d"]["title"] == "Delta 2"

    await ctx.delete_doc(DOCTYPE, "d")
    assert "d" not in notes

    assert events == [
        ("before_save", "d"),
        ("after_insert", "d"),
        ("after_save", "d"),
        ("before_save", "d"),
        ("after_update", "d"),
        ("after_save", "d"),
        ("before_delete", "d"),
        ("after_delete", "d"),
    ]


@pytest.mark.asyncio
async def test_document_instance_methods_work_for_virtual(ctx, notes):
    doc = await BaseDocument.load(DOCTYPE, "a")
    assert isinstance(doc, _Notes)
    assert doc.title == "Alpha"

    doc.title = "Alpha 2"
    await doc.save()
    assert notes["a"]["title"] == "Alpha 2"

    await doc.delete()
    assert "a" not in notes


@pytest.mark.asyncio
async def test_rename_is_refused(ctx, notes):
    with pytest.raises(HTTPException) as exc:
        await ctx.rename_doc(DOCTYPE, "a", "z")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_delete_goes_to_the_controller(ctx, notes):
    await ctx.bulk_delete_docs(DOCTYPE, ["a", "b"])
    assert set(notes) == {"c"}


@pytest.mark.asyncio
async def test_backup_refuses_create_and_update(ctx):
    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("Backup", {"name": "x"})
    assert exc.value.status_code == 405


@pytest.mark.asyncio
async def test_doctype_document_round_trip(ctx, db_session):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            "name": "RoundTripItem",
            "label": "Round Trip",
            "module": "core",
            "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
            "__is_new": True,
        }
    )
    doc = await ctx.get_doc("DocType", "RoundTripItem")
    doc["label"] = "Round Trip 2"
    saved = await ctx.save_doc("DocType", "RoundTripItem", doc)
    assert saved["label"] == "Round Trip 2"
    assert (await ctx.get_doc("DocType", "RoundTripItem"))["label"] == "Round Trip 2"

    names = [r["name"] for r in await ctx.get_list("DocType", search="Round Trip 2")]
    assert names == ["RoundTripItem"]

    await ctx.delete_doc("DocType", "RoundTripItem")
    assert await ctx.find_doc("DocType", "RoundTripItem") is None


@pytest.mark.asyncio
async def test_unsupported_write_explains_itself(ctx):
    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("Backup", {"name": "x"})
    assert "Create now" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_row_level_match_filters_list_count_and_get(ctx, db_session, engine):
    import grunt
    from grunt.api.v1.meta import save_doctype
    from grunt.document.registry import document_registry
    from tests.support import make_user

    await save_doctype(
        doctype_data={
            "name": "VirtualOwnedNote",
            "label": "Virtual Owned Note",
            "module": "core",
            "is_virtual": True,
            "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
            "permissions": [{"role": "Employee", "read": True, "match": "owner == user"}],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()
    _Notes.store = {
        "a": {"name": "a", "title": "Alice's", "owner": "alice@example.com"},
        "b": {"name": "b", "title": "Bob's", "owner": "bob@example.com"},
    }
    document_registry.register("VirtualOwnedNote", _Notes)
    try:
        alice = make_user("alice@example.com", roles=["Employee"])
        async with grunt.context(db_session, engine, alice):
            rows = await grunt.get_list("VirtualOwnedNote")
            assert [r["name"] for r in rows] == ["a"]
            assert rows.meta["total"] == 1
            assert await grunt.count("VirtualOwnedNote", respect_permissions=True) == 1
            assert (await grunt.get_doc("VirtualOwnedNote", "a"))["title"] == "Alice's"
            with pytest.raises(HTTPException) as exc:
                await grunt.get_doc("VirtualOwnedNote", "b")
            assert exc.value.status_code == 403
    finally:
        document_registry._controllers.pop("VirtualOwnedNote", None)
