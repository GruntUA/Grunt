"""Report access (roles, disabled), the SQL time limit, List totals and prepared reports."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.reports import prepared
from grunt.reports.access import runnable
from grunt.reports.doctypes.Report.report import prepare as prepare_report
from grunt.reports.doctypes.Report.report import run as run_report
from grunt.reports.engine import report_engine

ANALYST = "analyst@reports.test"
CLERK = "clerk@reports.test"
ROLE = "Report Analyst"

SLOW_SQL = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 1000000000) "
    "SELECT count(*) AS n FROM c"
)


@pytest_asyncio.fixture
async def users(ctx):
    await ctx.new_doc("Role", {"role_name": ROLE})
    for email, roles in ((ANALYST, [{"role_name": ROLE}]), (CLERK, [])):
        await ctx.new_doc(
            "User", {"email": email, "first_name": "T", "last_name": email, "roles": roles}
        )
    await ctx.db._session().commit()


async def _report(ctx, name: str, **values) -> dict:
    doc = await ctx.new_doc(
        "Report",
        {"report_name": name, "report_type": "Query", "query": "SELECT 1 AS one", **values},
    )
    await ctx.db._session().commit()
    return doc


async def _run_as(ctx, name: str, user: str, **kw) -> dict:
    return await report_engine.run(name, {}, user, ctx.db._session(), **kw)


@pytest.mark.asyncio
async def test_query_report_without_doctype_or_roles_is_system_managers_only(ctx, users):
    await _report(ctx, "Raw SQL")
    assert (await run_report(name="Raw SQL"))["data"] == [{"one": 1}]  # SYSTEM_USER
    for user in (ANALYST, CLERK):
        with pytest.raises(HTTPException) as e:
            await _run_as(ctx, "Raw SQL", user)
        assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_roles_open_a_report_to_their_holders_only(ctx, users):
    await _report(ctx, "For analysts", roles=[ROLE])
    assert (await _run_as(ctx, "For analysts", ANALYST))["data"] == [{"one": 1}]
    with pytest.raises(HTTPException):
        await _run_as(ctx, "For analysts", CLERK)


@pytest.mark.asyncio
async def test_roles_on_a_doctype_report_still_need_report_permission(ctx, users):
    # Report: only System Manager has `report` on it - a role doesn't bypass that.
    await _report(ctx, "On reports", report_type="List", ref_doctype="Report", roles=[ROLE])
    with pytest.raises(HTTPException):
        await _run_as(ctx, "On reports", ANALYST)


@pytest.mark.asyncio
async def test_disabled_report_does_not_run(ctx, users):
    await _report(ctx, "Switched off", disabled=True)
    with pytest.raises(HTTPException) as e:
        await run_report(name="Switched off")
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_runnable_filters_a_menu(ctx, users):
    rows = [
        {"report_name": "a", "roles": [ROLE]},
        {"report_name": "b", "roles": []},
        {"report_name": "c", "roles": [ROLE], "disabled": 1},
    ]
    assert [r["report_name"] for r in await runnable(rows, ANALYST)] == ["a"]
    assert [r["report_name"] for r in await runnable(rows, CLERK)] == []


@pytest.mark.asyncio
async def test_slow_query_is_stopped_at_the_timeout(ctx):
    if ctx.get_engine().dialect.name == "mysql":
        pytest.skip("MySQL stops the recursive CTE at cte_max_recursion_depth first")
    await _report(ctx, "Slow", query=SLOW_SQL, timeout=1)
    with pytest.raises(ApplicationError) as e:
        await run_report(name="Slow")
    assert e.value.code == "REPORT_TIMEOUT"
    # The session is still usable after the cancelled statement.
    assert (await _report(ctx, "After slow"))["report_name"] == "After slow"
    assert (await run_report(name="After slow"))["data"] == [{"one": 1}]


@pytest.mark.asyncio
async def test_list_report_marks_total_columns(ctx):
    await ctx.new_doc(
        "Report",
        {
            "report_name": "Totals",
            "report_type": "List",
            "ref_doctype": "Report",
            "columns": [
                {"fieldname": "report_type", "label": "Type"},
                {"fieldname": "name", "label": "Count", "aggregation": "count", "total": True},
            ],
        },
    )
    await ctx.db._session().commit()
    result = await run_report(name="Totals")
    assert [c.get("total", False) for c in result["columns"]] == [False, True]
    assert sum(r["name"] for r in result["data"]) >= 1


@pytest.mark.asyncio
async def test_prepared_report_runs_in_the_background(ctx, users, monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(prepared, "enqueue", lambda task, **kw: sent.append(kw))
    await _report(ctx, "Heavy", roles=[ROLE], prepared_report=True)
    session = ctx.db._session()

    # Nothing calculated yet: opening it doesn't run it.
    empty = await run_report(name="Heavy")
    assert empty["data"] == [] and empty["prepared"] == {"status": None}

    queued = await prepare_report(name="Heavy")
    assert queued["status"] == "Queued" and len(sent) == 1
    # Asking again while it is pending doesn't queue a second run.
    assert (await prepare_report(name="Heavy"))["name"] == queued["name"]
    await session.commit()

    await prepared.run_prepared(sent[0]["prepared_id"])
    done = await run_report(name="Heavy")
    assert done["data"] == [{"one": 1}]
    assert done["prepared"]["status"] == "Completed" and done["prepared"]["rows"] == 1

    # A new run replaces the old result (and its file).
    first_file = await ctx.db.get_value("PreparedReport", queued["name"], "result_file")
    await prepare_report(name="Heavy")
    await session.commit()
    await prepared.run_prepared(sent[-1]["prepared_id"])
    assert not await ctx.db.exists("PreparedReport", queued["name"])
    assert not await ctx.db.exists("File", first_file)

    # Results are per user - another viewer starts empty.
    report = await report_engine.load("Heavy", ANALYST, session)
    assert await prepared.latest(report["name"], ANALYST, {}) is None


@pytest.mark.asyncio
async def test_prepared_report_error_is_recorded(ctx, monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(prepared, "enqueue", lambda task, **kw: sent.append(kw))
    await _report(ctx, "Broken", query="SELECT * FROM no_such_table", prepared_report=True)
    await prepare_report(name="Broken")
    await ctx.db._session().commit()
    await prepared.run_prepared(sent[0]["prepared_id"])
    state = (await run_report(name="Broken"))["prepared"]
    assert state["status"] == "Error" and "no_such_table" in state["error"]


@pytest.mark.asyncio
async def test_a_lost_pending_run_is_replaced(ctx, monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(prepared, "enqueue", lambda task, **kw: sent.append(kw))
    await _report(ctx, "Lost", prepared_report=True)
    first = await prepare_report(name="Lost")
    await ctx.db._session().commit()
    # The worker died after taking it: Started two hours ago, never finished.
    await ctx.db.set_value(
        "PreparedReport",
        first["name"],
        {"status": "Started", "started_at": datetime.now(UTC) - timedelta(hours=2)},
    )
    second = await prepare_report(name="Lost")
    assert second["name"] != first["name"] and second["status"] == "Queued"
    assert await ctx.db.get_value("PreparedReport", first["name"], "status") == "Error"
    assert len(sent) == 2


def test_stale_rule():
    now = datetime.now(UTC)
    queued = {"status": "Queued", "created_at": now - timedelta(minutes=30)}
    assert not prepared._stale(queued, {})
    assert prepared._stale({**queued, "created_at": now - timedelta(hours=2)}, {})
    started = {"status": "Started", "started_at": (now - timedelta(hours=2)).replace(tzinfo=None)}
    assert prepared._stale(started, {})
    assert not prepared._stale(started, {"timeout": 3 * 3600})  # its own limit is longer
