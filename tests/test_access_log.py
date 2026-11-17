"""Access Log (PERMISSIONS_PLAN step 6c): exports, printouts and report
downloads are logged with who, what and how much; a refused attempt isn't."""

import pytest
from fastapi import HTTPException

from tests.support import make_user
from tests.test_permission_actions import LEDGER


@pytest.fixture
async def ledger(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LEDGER, "__is_new": True})
    names = [(await ctx.new_doc("ActLedger", {"title": t}))["name"] for t in ("Q3", "Q4")]
    await ctx.db._session().commit()
    return names


async def _entries(ctx) -> list[dict]:
    return await ctx.db.get_all(
        "AccessLog",
        fields=["action", "ref_doctype", "doc_id", "file_format", "rows", "filters", "owner"],
        order_by="created_at",
        order="asc",
        limit=50,
    )


@pytest.mark.asyncio
async def test_exports_prints_and_reports_are_logged(ctx, ledger, db_session, engine):
    import grunt
    from grunt.api.v1.data_import import export_quick
    from grunt.api.v1.document.export import export_csv, export_file, print
    from grunt.reports.doctypes.Report.report import export_xlsx

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

    clerk = make_user("clerk@example.com", roles=["Clerk"])
    async with grunt.context(db_session, engine, clerk):
        await export_file("ActLedger", fmt="csv", filters={"title": "Q3"})
        await export_csv("ActLedger", search="Q")
        await export_quick("ActLedger", fmt="csv")
        await print("ActLedger", ledger[0])
        await export_xlsx(name="Ledger titles")
    await db_session.commit()

    entries = await _entries(ctx)
    assert [(e["action"], e["ref_doctype"], e["file_format"]) for e in entries] == [
        ("Export", "ActLedger", "csv"),
        ("Export", "ActLedger", "csv"),
        ("Export", "ActLedger", "csv"),
        ("Print", "ActLedger", "html"),
        ("Report", "Report", "xlsx"),
    ]
    assert {e["owner"] for e in entries} == {"clerk@example.com"}
    assert entries[0]["rows"] == 1 and entries[0]["filters"] == {"filters": {"title": "Q3"}}
    assert entries[1]["filters"] == {"search": "Q"}
    assert entries[3]["doc_id"] == ledger[0]
    assert entries[4]["doc_id"] == "Ledger titles" and entries[4]["rows"] == 2


@pytest.mark.asyncio
async def test_refused_attempt_is_not_logged(ctx, ledger, db_session, engine):
    import grunt
    from grunt.api.v1.document.export import export_file

    viewer = make_user("viewer@example.com", roles=["Viewer"])
    async with grunt.context(db_session, engine, viewer):
        with pytest.raises(HTTPException):
            await export_file("ActLedger", fmt="csv")
    assert await _entries(ctx) == []
