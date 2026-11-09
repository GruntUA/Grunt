"""ScheduledJobLog / ScheduledJobState: an hourly-or-rarer job leaves a log row
per run, a more frequent one only per failure; every run updates the job's
state. Inline jobs are recorded by the scheduler, enqueued TaskIQ tasks by
ScheduledJobLogMiddleware."""

from datetime import UTC, datetime, timedelta

import pytest
from taskiq import TaskiqMessage, TaskiqResult

from grunt.tasks import job_log, scheduler
from grunt.tasks.middleware import ScheduledJobLogMiddleware

HOURLY = "0 * * * *"
EVERY_MINUTE = "* * * * *"


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


async def _state(job_name: str) -> dict | None:
    import grunt
    from grunt.db.session import async_session_factory

    async with async_session_factory() as session, grunt.system_context(session):
        return await grunt.db.get_value(
            "ScheduledJobState",
            job_name,
            ["last_status", "last_finished_at", "run_count", "failure_count", "last_error"],
            as_dict=True,
        )


def _taskiq_task(kicker_class):
    """A TaskIQ task: _run_logged enqueues it through kicker(), never calls it."""

    async def task(*args):
        raise AssertionError("enqueued tasks are not called inline")

    task.kicker = kicker_class  # pyright: ignore[reportFunctionMemberAccess]
    return task


def _message(log_id: str | None, **labels) -> TaskiqMessage:
    return TaskiqMessage(
        task_id="t1",
        task_name="some.task",
        labels={job_log.LOG_LABEL: log_id, **labels} if log_id else labels,
        args=[],
        kwargs={},
    )


@pytest.mark.asyncio
async def test_inline_job_success(setup_db):
    async def job():
        pass

    await scheduler._run_logged("test.ok", HOURLY, job)

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

    await scheduler._run_logged("test.intent", HOURLY, job)

    assert seen == ["BEGIN IMMEDIATE"]


@pytest.mark.asyncio
async def test_inline_job_failure(setup_db):
    async def job():
        raise RuntimeError("boom")

    await scheduler._run_logged("test.fail", HOURLY, job)

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

    task = _taskiq_task(Kicker)

    await scheduler._run_logged("test.kiq", HOURLY, task, "daily")

    [row] = await _rows("test.kiq")
    assert row["status"] == "Running"  # the worker closes it
    started = sent.pop(job_log.STARTED_LABEL)
    assert started
    assert sent == {
        job_log.LOG_LABEL: row["name"],
        job_log.JOB_LABEL: "test.kiq",
        job_log.CRON_LABEL: HOURLY,
        "args": ("daily",),
    }


@pytest.mark.asyncio
async def test_middleware_closes_row(setup_db):
    middleware = ScheduledJobLogMiddleware()
    ok_id = await job_log.open_job_log("test.mw_ok", HOURLY)
    fail_id = await job_log.open_job_log("test.mw_fail", HOURLY)
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
    log_id = await job_log.open_job_log("test.mw_retry", HOURLY)
    assert log_id

    await ScheduledJobLogMiddleware().post_execute(
        _message(log_id, retry_on_error=True, max_retries=3),
        TaskiqResult(is_err=True, return_value=None, execution_time=0.1, error=ValueError("x")),
    )

    assert (await _rows("test.mw_retry"))[0]["status"] == "Running"


@pytest.mark.asyncio
async def test_stale_running_rows_are_failed(setup_db):
    stale = await job_log.open_job_log("test.stale", HOURLY)
    fresh = await job_log.open_job_log("test.fresh", HOURLY)
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


@pytest.mark.parametrize(
    ("cron", "logged"),
    [
        ("0 * * * *", True),
        ("15 3 * * *", True),
        ("0 8 * * 1", True),
        ("* * * * *", False),
        ("*/5 * * * *", False),
        ("0,30 * * * *", False),
        ("0-10 * * * *", False),
        ("", False),
    ],
)
def test_logs_every_run_only_hourly_or_rarer(cron, logged):
    assert job_log.logs_every_run(cron) is logged


def test_log_runs_overrides_the_default():
    assert job_log.logs_every_run("* * * * *", True) is True
    assert job_log.logs_every_run("0 3 * * *", False) is False


@pytest.mark.asyncio
async def test_frequent_job_success_leaves_no_row_but_updates_state(setup_db):
    async def job():
        pass

    await scheduler._run_logged("test.freq_ok", EVERY_MINUTE, job)
    await scheduler._run_logged("test.freq_ok", EVERY_MINUTE, job)

    assert await _rows("test.freq_ok") == []
    state = await _state("test.freq_ok")
    assert state is not None
    assert state["last_status"] == "Success"
    assert state["last_finished_at"] is not None
    assert state["run_count"] == 2
    assert state["failure_count"] == 0


@pytest.mark.asyncio
async def test_frequent_job_failure_leaves_failed_row(setup_db):
    async def job():
        raise RuntimeError("boom")

    await scheduler._run_logged("test.freq_fail", EVERY_MINUTE, job)

    [row] = await _rows("test.freq_fail")
    assert row["status"] == "Failed"
    assert row["error_message"] == "boom"
    assert row["finished_at"] is not None
    state = await _state("test.freq_fail")
    assert state is not None
    assert (state["last_status"], state["failure_count"], state["last_error"]) == (
        "Failed",
        1,
        "boom",
    )


@pytest.mark.asyncio
async def test_success_after_failure_keeps_last_error(setup_db):
    calls = []

    async def job():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first")

    await scheduler._run_logged("test.recover", EVERY_MINUTE, job)
    await scheduler._run_logged("test.recover", EVERY_MINUTE, job)

    state = await _state("test.recover")
    assert state is not None
    assert state["last_status"] == "Success"
    assert (state["run_count"], state["failure_count"]) == (2, 1)
    assert state["last_error"] == "first"


@pytest.mark.asyncio
async def test_log_runs_true_logs_a_frequent_job(setup_db):
    async def job():
        pass

    await scheduler._run_logged("test.forced", EVERY_MINUTE, job, log_runs=True)

    [row] = await _rows("test.forced")
    assert row["status"] == "Success"


@pytest.mark.asyncio
async def test_enqueued_frequent_task_opens_no_row(setup_db):
    sent: dict = {}

    class Kicker:
        def with_labels(self, **labels):
            sent.update(labels)
            return self

        async def kiq(self, *args):
            pass

    task = _taskiq_task(Kicker)

    await scheduler._run_logged("test.kiq_freq", EVERY_MINUTE, task)

    assert await _rows("test.kiq_freq") == []
    assert job_log.LOG_LABEL not in sent
    assert sent[job_log.JOB_LABEL] == "test.kiq_freq"


@pytest.mark.asyncio
async def test_middleware_records_frequent_task(setup_db):
    middleware = ScheduledJobLogMiddleware()
    labels = {
        job_log.JOB_LABEL: "test.mw_freq",
        job_log.CRON_LABEL: EVERY_MINUTE,
        job_log.STARTED_LABEL: datetime.now(UTC).isoformat(),
    }
    ok = TaskiqResult(is_err=False, return_value=None, execution_time=0.1)
    err = TaskiqResult(is_err=True, return_value=None, execution_time=0.1, error=ValueError("bad"))

    await middleware.post_execute(_message(None, **labels), ok)
    assert await _rows("test.mw_freq") == []

    await middleware.post_execute(_message(None, **labels), err)
    [row] = await _rows("test.mw_freq")
    assert (row["status"], row["error_message"]) == ("Failed", "bad")
    state = await _state("test.mw_freq")
    assert state is not None
    assert (state["run_count"], state["failure_count"]) == (2, 1)


@pytest.mark.asyncio
async def test_middleware_ignores_unscheduled_tasks(setup_db):
    await ScheduledJobLogMiddleware().post_execute(
        _message(None), TaskiqResult(is_err=False, return_value=None, execution_time=0.1)
    )


def test_hooks_pass_log_runs(monkeypatch):
    added: list = []

    def add(path, cron, *, log_runs=None):
        added.append((path, cron, log_runs))

    monkeypatch.setattr(scheduler, "_add_scheduled_job", add)

    scheduler.register_scheduler_events(
        {
            "all": ["a.every_minute"],
            "cron": [{"handler": "a.forced", "expression": "*/5 * * * *", "log_runs": True}],
        }
    )

    assert added == [("a.every_minute", "*/1 * * * *", None), ("a.forced", "*/5 * * * *", True)]
