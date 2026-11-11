"""Permission rows grant ``actions`` - and export / print / report are their own
actions, not part of read: a role may see documents without taking them out.

(Import and share are covered in ``test_data_import_permissions`` and the share
tests.)
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from grunt.metadata.permission import DocPermission
from tests.support import make_user

LEDGER = {
    "name": "ActLedger",
    "label": "Act Ledger",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "Viewer", "actions": ["read"]},
        {"role": "Clerk", "actions": ["read", "export", "print", "report"]},
    ],
}


# The row model


def test_actions_keep_one_order():
    a = DocPermission(role="X", actions=["print", "read"])
    b = DocPermission(role="X", actions=["read", "print"])
    assert a.model_dump() == b.model_dump()


def test_old_flags_are_refused():
    """A row still in the old format would grant nothing - say so instead."""
    with pytest.raises(ValidationError, match="old flags"):
        DocPermission.model_validate({"role": "X", "read": True})


def test_unknown_action_is_refused():
    with pytest.raises(ValidationError):
        DocPermission(role="X", actions=["read", "wirte"])


# The endpoints


@pytest.fixture
async def ledger(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LEDGER, "__is_new": True})
    name = (await ctx.new_doc("ActLedger", {"title": "Q3"}))["name"]
    await ctx.db._session().commit()
    return name


async def _as(role, call, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, make_user(f"{role}@example.com", roles=[role])):
        return await call()


async def _denied(role, call, db_session, engine):
    with pytest.raises(HTTPException) as exc_info:
        await _as(role, call, db_session, engine)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_export_needs_export(ledger, db_session, engine):
    from grunt.api.v1.data_import import export_quick
    from grunt.api.v1.document.export import export_csv, export_file

    for call in (
        lambda: export_file("ActLedger", fmt="csv"),
        lambda: export_csv("ActLedger"),
        lambda: export_quick("ActLedger"),
    ):
        await _denied("Viewer", call, db_session, engine)
        assert await _as("Clerk", call, db_session, engine)


@pytest.mark.asyncio
async def test_data_export_needs_export_when_saved(ledger, db_session, engine):
    import grunt

    def save():
        return grunt.new_doc("DataExport", {"doctype_name": "ActLedger", "export_format": "CSV"})

    # DataExport itself is System Manager's; the target decides the rest.
    async with grunt.context(
        db_session, engine, make_user("sm@example.com", roles=["System Manager", "Viewer"])
    ):
        with pytest.raises(HTTPException) as exc_info:
            await save()
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_print_needs_print(ledger, db_session, engine):
    from grunt.api.v1.document.export import preview, print

    await _denied("Viewer", lambda: print("ActLedger", ledger), db_session, engine)
    response = await _as("Clerk", lambda: print("ActLedger", ledger), db_session, engine)
    assert response.status_code == 200

    template = "<p>{{ doc.title }}</p>"
    await _denied("Viewer", lambda: preview("ActLedger", template, ledger), db_session, engine)
    await _denied("Viewer", lambda: preview("ActLedger", template), db_session, engine)
    response = await _as(
        "Clerk", lambda: preview("ActLedger", template, ledger), db_session, engine
    )
    assert b"Q3" in response.body


@pytest.mark.asyncio
async def test_report_on_a_doctype_needs_report(ledger, ctx, db_session, engine):
    from grunt.reports.doctypes.Report.report import run as run_report

    await ctx.new_doc(
        "Report",
        {
            "report_name": "Ledger titles",
            "report_type": "List",
            "ref_doctype": "ActLedger",
            "columns": [{"fieldname": "title", "label": "Title"}],
        },
    )
    await ctx.db._session().commit()

    def call():
        return run_report(name="Ledger titles")

    await _denied("Viewer", call, db_session, engine)
    result = await _as("Clerk", call, db_session, engine)
    assert [r["title"] for r in result["data"]] == ["Q3"]
