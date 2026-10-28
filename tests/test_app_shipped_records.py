"""Records an app ships into core DocTypes (Pages, ...) go with it; its
extensions' dashboards show up in its switcher."""

import json

import pytest

from grunt.testkit import write_app_manifest


@pytest.fixture
def bench(tmp_path, monkeypatch):
    from grunt.site.manager import site_manager

    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    apps = tmp_path / "apps"
    write_app_manifest(apps / "base", {"name": "base"})
    addon = apps / "addon"
    write_app_manifest(addon, {"name": "addon"}, extends=["base"])
    (addon / "addon" / "fixtures").mkdir(parents=True)
    (addon / "addon" / "fixtures" / "01_page.json").write_text(
        json.dumps({"doctype": "Page", "records": [{"name": "addon-fixture-page"}]})
    )
    return apps


async def _page(ctx, name, app=None, widgets=1):
    rows = [{"widget_type": "metric", "title": f"w{i}"} for i in range(widgets)]
    await ctx.new_doc("Page", {"name": name, "label": name, "app": app, "widgets": rows})


@pytest.mark.asyncio
async def test_uninstall_removes_shipped_pages_with_widgets(ctx, bench, monkeypatch):
    from grunt.cli.app import _delete_shipped_records, _shipped_records
    from grunt.config import settings

    await _page(ctx, "addon-standard", app="addon", widgets=2)
    await _page(ctx, "addon-fixture-page")  # no app: known from the fixture file
    await _page(ctx, "base-home", app="base")

    shipped = await _shipped_records("addon", bench / "addon", skip=set())
    assert sorted(shipped) == [("Page", "addon-fixture-page"), ("Page", "addon-standard")]

    removed: list = []
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr("grunt.standard_records.remove_record", lambda *a, **k: removed.append(a))
    await _delete_shipped_records(shipped)

    names = [p["name"] for p in await ctx.get_list("Page", fields=["name"], limit=100)]
    assert "base-home" in names
    assert not {"addon-standard", "addon-fixture-page"} & set(names)
    widgets = await ctx.get_list(
        "PageWidget", filters={"parent_name": "addon-standard"}, fields=["name"]
    )
    assert widgets == []
    assert removed == []  # the app's files on disk stay


@pytest.mark.asyncio
async def test_switcher_lists_extension_dashboards(ctx, bench, monkeypatch):
    from grunt.api.v1 import workspace
    from grunt.site.manager import site_manager

    monkeypatch.setattr(site_manager, "get_installed_apps", lambda site: ["base", "addon"])
    workspace._extenders_of.cache_clear()
    pages = [
        {"name": "base-home", "app": "base"},
        {"name": "addon-page", "app": "addon", "label": "Addon"},
        {"name": "other", "app": "other"},
    ]

    picked = workspace._dashboards({"app": "base", "home_page": "base-home"}, pages)

    assert [p["name"] for p in picked] == ["base-home", "addon-page"]
    workspace._extenders_of.cache_clear()
