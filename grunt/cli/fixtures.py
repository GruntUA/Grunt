import asyncio
import importlib

import click

from grunt.cli.utils import _site_session


@click.group("fixtures")
def fixtures_group():
    """Фікстури додатків: експорт записів з БД у файли додатка."""
    pass


@fixtures_group.command("export")
@click.argument("app")
@click.option("--site", default=None, help="Назва сайту")
def fixtures_export(app: str, site: str | None):
    """Експортувати записи, оголошені в `fixtures` у hooks.py додатка, у <module>/fixtures/.

    Файли пишуться з `"sync": true` — при migrate вони оновлюють наявні записи.
    """

    async def _run():
        from grunt.app import grunt
        from grunt.apps.loader import _ensure_on_syspath, _hooks_import_path
        from grunt.fixtures import export_fixtures, parse_fixture_specs
        from grunt.site.manager import site_manager

        app_dir = site_manager.bench_dir / "apps" / app
        if not app_dir.is_dir():
            click.echo(f"Помилка: додаток '{app}' не знайдено ({app_dir}).", err=True)
            raise SystemExit(1)
        _ensure_on_syspath(app_dir)

        targets = []
        for hooks_file in sorted(app_dir.glob("*/hooks.py")):
            mod = importlib.import_module(_hooks_import_path(app, hooks_file.parent.name))
            entries = getattr(mod, "fixtures", None)
            if entries:
                targets.append((hooks_file.parent / "fixtures", parse_fixture_specs(entries)))

        if not targets:
            click.echo(f"У hooks.py додатка '{app}' не оголошено `fixtures` — нічого експортувати.")
            return

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            for fixtures_dir, specs in targets:
                for path, count in await export_fixtures(specs, fixtures_dir):
                    click.echo(f"  {path.relative_to(app_dir)} — {count} записів")

    asyncio.run(_run())
