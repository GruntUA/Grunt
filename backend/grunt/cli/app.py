import asyncio
from pathlib import Path

import click


@click.command("create-app")
@click.argument("name")
@click.option("--no-git", is_flag=True, default=False, help="Не ініціалізувати git репозиторій")
@click.option(
    "--dest",
    default=None,
    help="Директорія для створення додатку (за замовчуванням: bench_dir/apps/)",
)
def create_app(name: str, no_git: bool, dest: str | None):
    """Інтерактивно створити новий Grunt додаток.

    NAME — назва додатку (snake_case), наприклад: my_crm
    """
    from grunt.core.site.manager import site_manager  # noqa: PLC0415
    from grunt.utils.boilerplate import make_boilerplate  # noqa: PLC0415

    dest_path = Path(dest) if dest else site_manager.bench_dir / "apps"
    dest_path.mkdir(parents=True, exist_ok=True)
    make_boilerplate(dest_path, name, no_git=no_git)


@click.group("app")
def app_group():
    """Керування встановленими додатками."""
    pass


async def _do_install(name: str, site: str | None = None) -> None:
    """Встановлює додаток: реєструє в grunt.site, завантажує DocTypes, fixtures, after_install."""
    import json  # noqa: PLC0415

    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.db.base import Base  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.site.manager import current_site, site_manager  # noqa: PLC0415
    from grunt.core.startup import load_core_doctypes, seed_app_workspaces  # noqa: PLC0415

    _sites = site_manager.get_sites()
    target_site = site or (_sites[0] if _sites else None)
    if target_site is None:
        raise SystemExit("Помилка: сайт не знайдено.")

    app_dir = site_manager.bench_dir / "apps" / name
    app_json = app_dir / "app.json"
    if not app_dir.is_dir():
        raise SystemExit(f"Помилка: директорія '{app_dir}' не існує.")
    if not app_json.exists():
        raise SystemExit(f"Помилка: '{app_json}' не знайдено.")

    app_meta = json.loads(app_json.read_text(encoding="utf-8"))

    # Реєструємо в grunt.site
    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text(encoding="utf-8"))
    installed = site_config.get("installed_apps", [])
    if name not in installed:
        installed.append(name)
        site_config["installed_apps"] = installed
        site_file.write_text(
            json.dumps(site_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Завантажуємо DocTypes, fixtures, workspace, after_install
    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)

        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with maker() as session:
            await load_core_doctypes(session, eng)
            await doctype_registry.load_all(session)
            async with grunt.system_context(session, eng):
                await seed_app_workspaces(session, target_site)
            await session.commit()
    finally:
        current_site.reset(token)

    title = app_meta.get("title", name)
    print(f"✓ Додаток {title} встановлено на сайт {target_site}")
    print(f"  Додатки: {', '.join(site_config.get('installed_apps', []))}")


@app_group.command("install")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
def app_install(name: str, site: str | None):
    """Встановити додаток та одразу зареєструвати його workspace."""
    asyncio.run(_do_install(name, site))


@app_group.command("uninstall")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
def app_uninstall(name: str, site: str | None):
    """Видалити додаток із сайту (workspace та запис зберігаються)."""

    async def _run():
        import json  # noqa: PLC0415

        from grunt.core.site.manager import site_manager  # noqa: PLC0415

        _sites = site_manager.get_sites()
        target_site = site or (_sites[0] if _sites else None)
        if target_site is None:
            click.echo("Помилка: сайт не знайдено.", err=True)
            raise SystemExit(1)

        site_file = site_manager.sites_dir / target_site / "grunt.site"
        site_config = json.loads(site_file.read_text(encoding="utf-8"))
        installed = site_config.get("installed_apps", [])

        if name not in installed:
            click.echo(f"Помилка: додаток '{name}' не встановлено.", err=True)
            raise SystemExit(1)
        if name == "grunt":
            click.echo("Помилка: базовий додаток grunt не можна видалити.", err=True)
            raise SystemExit(1)

        installed.remove(name)
        site_config["installed_apps"] = installed
        site_file.write_text(
            json.dumps(site_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        click.echo(f"✓ Додаток '{name}' видалено з сайту {target_site}")
        click.echo(f"  Додатки: {', '.join(installed)}")

    asyncio.run(_run())


@app_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def app_list(site: str | None):
    """Показати встановлені додатки."""
    import json  # noqa: PLC0415

    from grunt.core.site.manager import site_manager  # noqa: PLC0415

    _sites = site_manager.get_sites()
    target_site: str | None = site or (_sites[0] if _sites else None)
    if target_site is None:
        click.echo("Помилка: сайт не знайдено.", err=True)
        raise SystemExit(1)

    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text(encoding="utf-8"))
    apps = site_config.get("installed_apps", [])
    click.echo(f"Сайт: {target_site}")
    for a in apps:
        click.echo(f"  • {a}")
