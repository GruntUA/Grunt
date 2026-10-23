"""«Стан системи»: a live, read-only virtual singleton of health checks."""

import pytest

from grunt.monitoring import health

URL = "/api/v1/docs/SystemHealthReport/SystemHealthReport"
STATUSES = {"OK", "Warning", "Error", "Info"}
METHOD = "/api/v1/method/grunt.monitoring.health"


@pytest.fixture(autouse=True)
def _offline_updates(monkeypatch):
    """The update checks ask git remotes, endoflife.date, PyPI and npm - not in tests."""
    from grunt.monitoring import updates

    async def unavailable(*args, **kwargs):
        raise updates.UnavailableError("offline")

    for name in ("fetch", "ls_remote", "framework_updates", "app_updates", "npm_outdated"):
        monkeypatch.setattr(updates, name, unavailable)
    monkeypatch.setattr(updates, "old_runtimes", lambda: ([], []))
    updates.clear_cache()
    yield
    updates.clear_cache()


@pytest.mark.asyncio
async def test_report_opens_on_a_skeleton(client, auth_headers, monkeypatch):
    async def never(*args, **kwargs):
        raise AssertionError("opening the report must not run the checks")

    monkeypatch.setattr(health, "_safe", never)
    r = await client.get(URL, headers={**auth_headers, "X-Grunt-Lang": "en"})
    assert r.status_code == 200, r.text
    doc = r.json()["data"]

    keys = [s["key"] for s in doc["sections"]]
    assert keys == [*health._CHECKS, *health._ITEMS]
    for key in health._CHECKS:
        assert f'<tbody data-health="{key}">' in doc["report"]
    assert "Checking…" in doc["top_errors"]
    assert "<table>" in doc["browser_report"]


@pytest.mark.asyncio
async def test_every_section_runs(client, auth_headers):
    """What the page does after opening: one request per section."""
    headers = {**auth_headers, "X-Grunt-Lang": "en"}
    for key in health._CHECKS:
        r = await client.post(f"{METHOD}.run_section", json={"key": key}, headers=headers)
        assert r.status_code == 200, (key, r.text)
        data = r.json()["data"]
        assert data["rows"] and all(c["status"] in STATUSES for c in data["rows"])
        crashed = [c for c in data["rows"] if c["value"] == "check failed"]
        assert not crashed, crashed
        assert data["html"].startswith(f'<tbody data-health="{key}">')

    r = await client.post(f"{METHOD}.run_section", json={"key": "largest_tables"}, headers=headers)
    rows = r.json()["data"]["rows"]
    assert rows and rows[0]["count"] >= 0

    r = await client.post(f"{METHOD}.run_section", json={"key": "nope"}, headers=headers)
    assert r.status_code == 404, r.text


def test_rendered_rows_are_escaped():
    html = health.render(
        "section",
        key="x",
        groups=health._groups([health.row("<b>cat</b>", "<script>", "Error", "<i>v</i>")]),
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;b&gt;cat&lt;/b&gt;" in html and "var(--destructive)" in html


@pytest.mark.asyncio
async def test_browser_rows_render(client, auth_headers):
    rows = [{"category": "Network", "check": "Server", "status": "OK", "value": "1 ms", "hint": ""}]
    r = await client.post(f"{METHOD}.render_checks", json={"rows": rows}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert "1 ms" in r.json()["data"] and 'data-health="browser"' in r.json()["data"]


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
    r = await client.get("/api/v1/docs/SqlProfilerQuery", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []
    r = await client.get("/api/v1/docs/SqlProfilerQuery/x", headers=auth_headers)
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
    r, _venvs = await health.check_app_dependencies()
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


def test_stray_app_venv_is_reported(tmp_path):
    from grunt.monitoring.health import WARNING, stray_venvs_row

    (tmp_path / "grunt" / ".venv").mkdir(parents=True)
    (tmp_path / "grunt" / ".venv" / "pyvenv.cfg").write_text("")
    assert stray_venvs_row(tmp_path)["status"] == "OK"

    (tmp_path / "hrm" / ".venv").mkdir(parents=True)
    (tmp_path / "hrm" / ".venv" / "pyvenv.cfg").write_text("")
    found = stray_venvs_row(tmp_path)
    assert found["status"] == WARNING
    assert "apps/hrm/.venv" in found["hint"]


@pytest.mark.asyncio
async def test_version_the_database_was_migrated_with(ctx):
    import grunt
    from grunt.startup.app_install import record_migrated_versions

    if await grunt.exists("GruntInstalledApp", {"name": "grunt"}) is None:
        await grunt.new_doc("GruntInstalledApp", {"name": "grunt", "title": "Grunt"})
    await grunt.save_doc("GruntInstalledApp", "grunt", {"version": "0.0.1"})

    [stale] = [r for r in await health.check_versions() if r["check"] == "grunt"]
    assert stale["status"] == "Warning" and "0.0.1" in stale["hint"]

    await record_migrated_versions()
    [fresh] = [r for r in await health.check_versions() if r["check"] == "grunt"]
    assert fresh["status"] == "Info" and fresh["value"] == grunt.__version__


def test_version_and_update_rows_merge():
    cat = "Framework and apps"
    local = [
        health.row(cat, "grunt", "Info", "1.2.0"),
        health.row(cat, "hrm", "Warning", "0.3.0", "Run `grunt migrate`."),
        health.row(cat, "Database migrations", "OK", "0017"),
    ]
    available = [
        health.row(cat, "grunt", "OK", "1.2.0"),
        health.row(cat, "hrm", "Warning", "0.3.0 → 0.4.0", "Run `grunt update`."),
        health.row(cat, "Python", "OK", "3.15.1"),
    ]
    grunt_row, hrm, migrations, python = health._merge_by_check(local, available)
    assert grunt_row["status"] == "OK"
    assert hrm["value"] == "0.3.0 → 0.4.0"
    assert hrm["hint"] == "Run `grunt migrate`. Run `grunt update`."
    assert migrations["check"] == "Database migrations" and python["check"] == "Python"


@pytest.mark.asyncio
async def test_largest_tables_counts_rows(ctx):
    await ctx.new_doc("ToDo", {"description": "count me"})
    counts = {r["label"]: r["count"] for r in await health.largest_tables()}
    assert counts, "every synced DocType table is counted"
    assert all(n >= 0 for n in counts.values())
    if "ToDo" in counts:
        assert counts["ToDo"] >= 1


@pytest.mark.asyncio
async def test_pdf_row_without_chromium(monkeypatch):
    from grunt.print.pdf import PdfEngineError

    async def missing():
        raise PdfEngineError("no chromium")

    monkeypatch.setattr(health, "check_engine", missing)
    [pdf] = await health.check_pdf()
    assert pdf["status"] == "Error" and "grunt update" in pdf["hint"]


@pytest.mark.asyncio
async def test_pdf_row_with_chromium(monkeypatch):
    async def installed():
        return "1.64.0"

    monkeypatch.setattr(health, "check_engine", installed)
    [pdf] = await health.check_pdf()
    assert pdf["status"] == "OK" and pdf["value"] == "Playwright 1.64.0"
