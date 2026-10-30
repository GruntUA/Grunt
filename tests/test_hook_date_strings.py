"""A controller hook that copies a date from the loaded document (an ISO string
there) into another Date/Datetime field gets it stored, on insert and on update.

The update used to hand the string straight to the column, and SQLite refused it:
``SQLite DateTime type only accepts Python datetime and date objects``.
"""

from datetime import UTC, date, datetime

import pytest

from grunt.document.base import Document

DOCTYPE = "HookDateNote"


class _Note(Document):
    async def before_save(self) -> None:
        d = self.data
        if d.get("source_at"):
            d["copied_at"] = d.get("copied_at") or d["source_at"]
        if d.get("source_on"):
            d["copied_on"] = d["source_on"]


@pytest.fixture
async def notes(ctx):
    from grunt.api.v1.meta import save_doctype
    from grunt.document.registry import document_registry

    await save_doctype(
        doctype_data={
            "name": DOCTYPE,
            "label": "Hook Date Note",
            "module": "core",
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
                {"fieldname": "source_at", "label": "Source at", "fieldtype": "Datetime"},
                {"fieldname": "copied_at", "label": "Copied at", "fieldtype": "Datetime"},
                {"fieldname": "source_on", "label": "Source on", "fieldtype": "Date"},
                {"fieldname": "copied_on", "label": "Copied on", "fieldtype": "Date"},
            ],
            "__is_new": True,
        }
    )
    document_registry.register(DOCTYPE, _Note)
    try:
        yield
    finally:
        document_registry._controllers.pop(DOCTYPE, None)


@pytest.mark.asyncio
async def test_hook_copied_iso_dates_are_stored(ctx, notes):
    doc = await ctx.new_doc(DOCTYPE, {"title": "a"})
    # Set behind the controller's back, so the next save loads it as a string.
    await ctx.db.set_value(
        DOCTYPE,
        doc["name"],
        {"source_at": datetime(2021, 10, 8, 10, 12, tzinfo=UTC), "source_on": date(2021, 10, 8)},
    )

    await ctx.save_doc(DOCTYPE, doc["name"], {"title": "b"})

    copied_at, copied_on = await ctx.db.get_value(DOCTYPE, doc["name"], ["copied_at", "copied_on"])
    assert datetime.fromisoformat(str(copied_at)) == datetime(2021, 10, 8, 10, 12, tzinfo=UTC)
    assert str(copied_on) == "2021-10-08"


@pytest.mark.asyncio
async def test_hook_iso_string_on_insert(ctx, notes):
    doc = await ctx.new_doc(
        DOCTYPE, {"title": "c", "copied_at": "2021-10-08T10:12:00+00:00", "source_on": "2021-10-08"}
    )
    copied_at, copied_on = await ctx.db.get_value(DOCTYPE, doc["name"], ["copied_at", "copied_on"])
    assert datetime.fromisoformat(str(copied_at)) == datetime(2021, 10, 8, 10, 12, tzinfo=UTC)
    assert str(copied_on) == "2021-10-08"
