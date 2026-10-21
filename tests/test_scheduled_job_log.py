"""ScheduledJobLog: every scheduler firing leaves a row - inline jobs are closed
by the scheduler, enqueued TaskIQ tasks by ScheduledJobLogMiddleware."""

from datetime import UTC, datetime, timedelta

import pytest
from taskiq import TaskiqMessage, TaskiqResult

from grunt.tasks import job_log, scheduler
from grunt.tasks.middleware import ScheduledJobLogMiddleware


@pytest.fixture(autouse=True)
def _test_db_sessions(monkeypatch):
    """job_log opens its own sessions through the site manager - point it at the test DB."""
    import conftest as _cf
    from grunt.db import session

    monkeypatch.setattr(session.site_manager, "get_active_site", lambda: "test", raising=False)
    monkeypatch.setattr(
        session.site_manager, "get_session_maker", lambda _s: _cf.TestSessionLocal, raising=False
    )
    monkeypatch.setattr(
        session.site_manager, "get_engine", lambda _s: _cf.test_engine, raising=False
    )


async def _rows(job_name: str) -> list[dict]:
    import grunt
    from grunt.db.session import async_session_factory

    async with async_session_factory() as session, grunt.system_context(session):
        return await grunt.db.get_all(
            "ScheduledJobLog",
            filters={"job_name": job_name},
            fields=["name", "status", "finished_at", "error_message"],
        )


def _message(log_id: str, **labels) -> TaskiqMessage:
    return TaskiqMessage(
        task_id="t1",
        task_name="some.task",
        labels={job_log.LOG_LABEL: log_id, **labels},
        args=[],
        kwargs={},
    )


@pytest.mark.asyncio
async def test_inline_job_success(setup_db):
    async def job():
        pass

    await scheduler._run_logged("test.ok", "* * * * *", job)

    [row] = await _rows("test.ok")
    assert row["status"] == "Success"
    assert row["finished_at"] is not None


@pytest.mark.asyncio
async def test_inline_job_takes_write_lock_up_front(setup_db, monkeypatch):
    """Scheduler runs in the web process (deferred BEGIN) - its firings write."""
    from grunt.db import write_intent

    monkeypatch.setattr(write_intent, "_process_default", False)
    seen = []

    async def job():
        seen.append(write_intent.begin_statement())

    await scheduler._run_logged("test.intent", "* * * * *", job)

    assert seen == ["BEGIN IMMEDIATE"]


@pytest.mark.asyncio
async def test_inline_job_failure(setup_db):
    async def job():
        raise RuntimeError("boom")

    await scheduler._run_logged("test.fail", "* * * * *", job)

    [row] = await _rows("test.fail")
    assert row["status"] == "Failed"
    assert row["error_message"] == "boom"


@pytest.mark.asyncio
async def test_enqueued_task_carries_log_id(setup_db):
    sent: dict = {}

    class Kicker:
        def with_labels(self, **labels):
            sent.update(labels)
            return self

        async def kiq(self, *args):
            sent["args"] = args

    class Task:
        def kicker(self):
            return Kicker()

    await scheduler._run_logged("test.kiq", "* * * * *", Task(), "daily")  # pyright: ignore[reportArgumentType]

    [row] = await _rows("test.kiq")
    assert row["status"] == "Running"  # the worker closes it
    assert sent == {job_log.LOG_LABEL: row["name"], "args": ("daily",)}


@pytest.mark.asyncio
async def test_middleware_closes_row(setup_db):
    middleware = ScheduledJobLogMiddleware()
    ok_id = await job_log.open_job_log("test.mw_ok", "* * * * *")
    fail_id = await job_log.open_job_log("test.mw_fail", "* * * * *")
    assert ok_id and fail_id

    await middleware.post_execute(
        _message(ok_id), TaskiqResult(is_err=False, return_value=None, execution_time=0.1)
    )
    await middleware.post_execute(
        _message(fail_id),
        TaskiqResult(is_err=True, return_value=None, execution_time=0.1, error=ValueError("bad")),
    )

    assert (await _rows("test.mw_ok"))[0]["status"] == "Success"
    [failed] = await _rows("test.mw_fail")
    assert failed["status"] == "Failed"
    assert failed["error_message"] == "bad"


@pytest.mark.asyncio
async def test_middleware_keeps_row_running_while_retrying(setup_db):
    log_id = await job_log.open_job_log("test.mw_retry", "* * * * *")
    assert log_id

    await ScheduledJobLogMiddleware().post_execute(
        _message(log_id, retry_on_error=True, max_retries=3),
        TaskiqResult(is_err=True, return_value=None, execution_time=0.1, error=ValueError("x")),
    )

    assert (await _rows("test.mw_retry"))[0]["status"] == "Running"


@pytest.mark.asyncio
async def test_stale_running_rows_are_failed(setup_db):
    stale = await job_log.open_job_log("test.stale", "* * * * *")
    fresh = await job_log.open_job_log("test.fresh", "* * * * *")
    assert stale and fresh
    await _backdate(stale, job_log.STALE_AFTER + timedelta(minutes=1))

    await job_log.fail_stale_job_logs()

    assert (await _rows("test.stale"))[0]["status"] == "Failed"
    assert (await _rows("test.fresh"))[0]["status"] == "Running"


async def _backdate(log_id: str, age: timedelta) -> None:
    import grunt
    from grunt.db.session import async_session_factory

    async with async_session_factory() as session, grunt.system_context(session):
        await grunt.db.set_value("ScheduledJobLog", log_id, {"started_at": datetime.now(UTC) - age})
