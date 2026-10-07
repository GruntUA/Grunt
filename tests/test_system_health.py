"""«Стан системи»: a live, read-only virtual singleton of health checks."""

from __future__ import annotations

import pytest

from grunt.monitoring import health

URL = "/api/v1/docs/SystemHealthReport/SystemHealthReport"
STATUSES = {"OK", "Warning", "Error", "Info"}


@pytest.mark.asyncio
async def test_report_runs_every_check(client, auth_headers):
    # English — the CHECKS categories are the (untranslated) English sources.
    r = await client.get(URL, headers={**auth_headers, "X-Grunt-Lang": "en"})
    assert r.status_code == 200, r.text
    doc = r.json()["data"]

    checks = doc["checks"]
    assert {c["category"] for c in checks} >= {c for c, _ in health.CHECKS}
    assert all(c["status"] in STATUSES for c in checks)
    crashed = [c for c in checks if c["value"] == "check failed"]
    assert not crashed, crashed

    assert doc["overall_status"] in {"OK", "Warning", "Error"}
    assert doc["ok_count"] + doc["warning_count"] + doc["error_count"] <= len(checks)
    assert doc["largest_tables"] and doc["largest_tables"][0]["count"] >= 0
    assert doc["browser_checks"] == []  # filled in by the page, in the browser


@pytest.mark.asyncio
async def test_report_is_read_only(client, auth_headers):
    r = await client.put(URL, json={"overall_status": "OK"}, headers=auth_headers)
    assert r.status_code in (403, 405), r.text


@pytest.mark.asyncio
async def test_broken_check_becomes_an_error_row(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(health, "_session", _NoSession)
    [bad] = await health._safe("Фонові задачі", boom)
    assert bad["status"] == "Error" and bad["hint"] == "redis down"


class _NoSession:
    """Stand-in session: begin_nested() is a no-op savepoint."""

    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_virtual_child_without_controller_lists_empty(client, auth_headers):
    """Opening the list of a controller-less virtual child DocType is an empty
    list, not a 500 (it used to raise NotImplementedError)."""
    r = await client.get("/api/v1/docs/SystemHealthCheck", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []
    r = await client.get("/api/v1/docs/SystemHealthCheck/x", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_doc_guard_on_virtual_doctype_does_not_touch_a_table(ctx):
    """doc_guard (websocket rooms, connections, history) used to SELECT from the
    virtual DocType's non-existent table."""
    from grunt.document.connections import get_connections

    assert await get_connections("SystemHealthReport", "SystemHealthReport") == {"groups": []}


@pytest.mark.asyncio
async def test_missing_app_dependency_is_reported(tmp_path, monkeypatch):
    from grunt.site.manager import site_manager

    app = tmp_path / "apps" / "demo"
    app.mkdir(parents=True)
    (app / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["surely-not-installed-pkg>=1", "pydantic"]\n'
    )
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    [r] = await health.check_app_dependencies()
    assert r["status"] == "Error"
    assert "demo: demo" in r["hint"] and "surely-not-installed-pkg" in r["hint"]
    assert "pydantic" not in r["hint"]


@pytest.mark.asyncio
async def test_unregistered_scheduler_job_is_reported(ctx):
    from grunt.tasks import scheduler

    # health holds a reference to this very dict - mutate it, don't replace it.
    saved = dict(scheduler.failed_jobs)
    scheduler.failed_jobs.clear()
    try:
        scheduler._add_scheduled_job("no_such_app.tasks.nope", "0 8 * * *")
        rows = await health.check_scheduler()
    finally:
        scheduler.failed_jobs.clear()
        scheduler.failed_jobs.update(saved)
    [bad] = [r for r in rows if r["check"] == "Незареєстровані задачі"]
    assert bad["status"] == "Error" and "no_such_app.tasks.nope" in bad["hint"]
