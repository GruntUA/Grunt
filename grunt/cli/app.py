import asyncio
from pathlib import Path

import click


@click.group("app")
def app_group():
    """Керування встановленими додатками."""
    pass


@app_group.command("create")
@click.argument("name")
@click.option("--no-git", is_flag=True, default=False, help="Не ініціалізувати git репозиторій")
@click.option(
    "--dest",
    default=None,
    help="Директорія для створення додатку (за замовчуванням: bench_dir/apps/)",
)
def create_app(name: str, no_git: bool, dest: str | None):
    """Створити новий Grunt додаток (scaffold).

    NAME — назва додатку (snake_case), наприклад: my_crm
    """
    from grunt.site.manager import site_manager
    from grunt.utils.boilerplate import make_boilerplate

    dest_path = Path(dest) if dest else site_manager.bench_dir / "apps"
    dest_path.mkdir(parents=True, exist_ok=True)
    make_boilerplate(dest_path, name, no_git=no_git)


async def _do_install(name: str, site: str | None = None) -> None:
    """Встановлює додаток: реєструє в grunt.site, завантажує DocTypes, fixtures, after_install."""
    import json

    from grunt.app import grunt
    from grunt.db.base import Base
    from grunt.metadata.compiler import SA_METADATA
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import current_site, site_manager
    from grunt.startup import load_core_doctypes, seed_app_workspaces

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
            await conn.run_sync(SA_METADATA.create_all)

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
        import json

        from grunt.site.manager import site_manager

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
    import json

    from grunt.site.manager import site_manager

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


@app_group.command("doctor")
@click.argument("name", required=False)
def app_doctor(name: str | None):
    """Перевірити додатки на помилки структури та виправити їх.

    Якщо NAME не вказано — перевіряє всі додатки.
    """
    import subprocess

    from grunt.site.manager import site_manager

    apps_dir = site_manager.bench_dir / "apps"
    target_apps = (
        [name]
        if name
        else [d.name for d in apps_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    )

    for app_name in target_apps:
        app_path = apps_dir / app_name
        click.echo(f"🩺 Перевірка додатку: {click.style(app_name, fg='cyan')}")

        # 1. Перевірка Git
        git_dir = app_path / ".git"
        if not git_dir.is_dir():
            click.echo(f"  [!] Git не ініціалізовано. {click.style('Виправлення...', fg='yellow')}")
            try:
                subprocess.run(["git", "init"], cwd=str(app_path), check=True, capture_output=True)

                # Додаємо базовий .gitignore
                gitignore = app_path / ".gitignore"
                if not gitignore.exists():
                    content = "__pycache__/\n*.py[cod]\n.env\n.venv/\nnode_modules/\ndist/\n"
                    gitignore.write_text(content, encoding="utf-8")

                click.echo(f"  {click.style('✓', fg='green')} Git репозиторій створено.")
            except Exception as e:
                click.echo(f"  {click.style('✗', fg='red')} Помилка при ініціалізації Git: {e}")

        # 2. Перевірка app.json
        app_json = app_path / "app.json"
        if not app_json.exists():
            click.echo(f"  [!] app.json відсутній. {click.style('Створення...', fg='yellow')}")
            import json

            basic_meta = {
                "name": app_name,
                "title": app_name.replace("_", " ").title(),
                "description": f"Додаток {app_name}",
                "version": "0.1.0",
            }
            app_json.write_text(
                json.dumps(basic_meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            click.echo(f"  {click.style('✓', fg='green')} app.json створено.")

        # 3. Перевірка пакету (__init__.py)
        pkg_dir = app_path / app_name
        if pkg_dir.is_dir():
            init_py = pkg_dir / "__init__.py"
            if not init_py.exists():
                click.echo(
                    f"  [!] {app_name}/__init__.py відсутній. "
                    f"{click.style('Створення...', fg='yellow')}"
                )
                init_py.touch()
                click.echo(f"  {click.style('✓', fg='green')} __init__.py створено.")

    click.echo(f"\n{click.style('Доктор завершив роботу!', bold=True)}")
