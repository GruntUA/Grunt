"""``site_manager.on_engine``: layers above hook into site engines without the
manager knowing them (IMPORT_CYCLES_PLAN.md, step 3)."""

from sqlalchemy import event

from grunt.monitoring import perf
from grunt.site.manager import SiteManager, site_manager


def _manager(tmp_path, monkeypatch) -> SiteManager:
    manager = SiteManager()
    monkeypatch.setattr(manager, "sites_dir", tmp_path)
    return manager


async def test_a_setup_runs_on_engines_made_before_and_after_it(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    seen: list[object] = []
    before = manager.get_engine("one")

    manager.on_engine(seen.append)
    after = manager.get_engine("two")

    assert seen == [before, after]
    for engine in (before, after):
        await engine.dispose()


async def test_the_sql_counter_registers_itself_on_site_engines(tmp_path, monkeypatch):
    assert perf.attach_sql_counter in site_manager._engine_setups

    manager = _manager(tmp_path, monkeypatch)
    manager.on_engine(perf.attach_sql_counter)
    engine = manager.get_engine("three")

    assert event.contains(engine.sync_engine, "before_cursor_execute", perf._before_cursor)
    await engine.dispose()
