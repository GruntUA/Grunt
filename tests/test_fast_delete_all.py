"""Fast delete (``BulkDeleteTask.run_fast_delete_all``) takes exactly the rows the
list shows for its filters and search, and cleans up only their search-index
entries - not the whole DocType's.
"""

from contextlib import asynccontextmanager

import pytest

pytestmark = pytest.mark.asyncio


FAST_DT = {
    "name": "FastDelItem",
    "label": "Fast Del Item",
    "module": "core",
    "title_field": "title",
    "search_fields": ["title"],
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
        {"fieldname": "kind", "label": "Kind", "fieldtype": "Data"},
    ],
}


class _Manager:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_to_user(self, _email: str, message: dict) -> None:
        self.sent.append(message)


async def test_fast_delete_respects_filters_and_search(ctx, db_session, engine, monkeypatch):
    from grunt.api.v1.meta import save_doctype
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.document import bulk_ops
    from grunt.search.service import _search_index_table

    await save_doctype(doctype_data={**FAST_DT, "__is_new": True})
    await db_session.commit()

    names = {}
    for title, kind in (("alpha one", "a"), ("alpha two", "a"), ("beta", "a"), ("alpha three", "b")):
        doc = await ctx.new_doc("FastDelItem", {"title": title, "kind": kind})
        names[title] = doc["name"]
        await db_session.execute(
            _search_index_table.insert().values(
                idx_id=f"fastdel-test:{doc['name']}", doctype="FastDelItem", doc_id=doc["name"], title=title,
            )
        )
    await db_session.commit()

    @asynccontextmanager
    async def _session():
        yield db_session

    monkeypatch.setattr(bulk_ops, "async_session_factory", _session)
    task = bulk_ops.BulkDeleteTask()
    task._manager = _Manager()

    await task.run_fast_delete_all(
        "FastDelItem",
        filters={"kind__eq": "a"},
        search="alpha",
        user=SYSTEM_USER,
        user_email=SYSTEM_USER.email,
        engine=engine,
    )

    remaining = {r["name"] for r in await ctx.get_list("FastDelItem", fields=["name"], limit=100)}
    assert remaining == {names["beta"], names["alpha three"]}

    indexed = {
        row.doc_id
        for row in await db_session.execute(
            _search_index_table.select().where(_search_index_table.c.doctype == "FastDelItem")
        )
    }
    assert indexed == {names["beta"], names["alpha three"]}

    done = task._manager.sent[-1]
    assert done["event"] == "bulk_delete_done"
    assert done["data"]["deleted"] == 2
