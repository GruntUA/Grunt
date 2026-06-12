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
    from grunt.db.base import metadata
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
            await conn.run_sync(metadata.create_all)
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


async def _do_uninstall(
    name: str,
    site: str | None = None,
    *,
    keep_data: bool = False,
    assume_yes: bool = False,
    vacuum: bool = False,
) -> None:
    """Видаляє додаток із сайту разом із його даними в БД.

    Очищає: таблиці даних DocType'ів додатку, їх записи в метаданих,
    workspace (AppMenu + sidebar items), лічильники NamingSeries та запис
    GruntInstalledApp. З ``keep_data=True`` лише знімає реєстрацію в
    grunt.site, не торкаючись БД.
    """
    import json

    from sqlalchemy import func, select

    from grunt.app import grunt
    from grunt.metadata.compiler import compile_doctype_to_table
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import current_site, site_manager
    from grunt.startup import load_core_doctypes

    _sites = site_manager.get_sites()
    target_site = site or (_sites[0] if _sites else None)
    if target_site is None:
        raise SystemExit("Помилка: сайт не знайдено.")
    if name == "grunt":
        raise SystemExit("Помилка: базовий додаток grunt не можна видалити.")

    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text(encoding="utf-8"))
    installed: list[str] = site_config.get("installed_apps", [])
    is_registered = name in installed

    def _unregister() -> None:
        if name in installed:
            installed.remove(name)
            site_config["installed_apps"] = installed
            site_file.write_text(
                json.dumps(site_config, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    if keep_data:
        if not is_registered:
            raise SystemExit(f"Помилка: додаток '{name}' не встановлено.")
        _unregister()
        click.echo(f"✓ Додаток '{name}' видалено з сайту {target_site} (дані збережено)")
        click.echo(f"  Додатки: {', '.join(installed)}")
        return

    # Модулі додатку — з app.json; якщо директорії вже немає, fallback на name
    app_modules = [name]
    app_json = site_manager.bench_dir / "apps" / name / "app.json"
    if app_json.exists():
        app_modules = json.loads(app_json.read_text(encoding="utf-8")).get("modules") or [name]

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)

        async with maker() as session:
            await load_core_doctypes(session, eng)
            await doctype_registry.load_all(session)

            app_doctypes = [
                dt for dt in await doctype_registry.list_all() if dt.module in app_modules
            ]

            async with grunt.system_context(session, eng):
                has_installed_row = await grunt.exists("GruntInstalledApp", {"name": name})
                has_workspace = await grunt.exists("AppMenu", {"name": name})

                if not (is_registered or app_doctypes or has_installed_row or has_workspace):
                    raise SystemExit(
                        f"Помилка: додаток '{name}' не встановлено і слідів у БД не знайдено."
                    )

                # План видалення: DocType → (Table, кількість рядків | None якщо таблиці немає)
                plan: list[tuple[str, object, int | None]] = []
                for dt in app_doctypes:
                    table = compile_doctype_to_table(dt)
                    try:
                        cnt = (
                            await session.execute(select(func.count()).select_from(table))
                        ).scalar() or 0
                    except Exception:
                        cnt = None
                    plan.append((dt.name, table, cnt))

                click.echo(f"Сайт: {target_site}. Буде видалено:")
                for dt_name, table, cnt in plan:
                    rows = "таблиці немає" if cnt is None else f"{cnt} рядків"
                    click.echo(f"  • DocType {dt_name} ({getattr(table, 'name', '?')}: {rows})")
                if has_workspace:
                    click.echo(f"  • Workspace '{name}' із пунктами меню")
                if has_installed_row:
                    click.echo(f"  • Запис GruntInstalledApp '{name}'")

                if not assume_yes and not click.confirm(
                    "Продовжити? Дані буде втрачено безповоротно"
                ):
                    raise SystemExit("Скасовано.")

                # before_uninstall hook додатку (apps/<name>/install.py)
                install_py = site_manager.bench_dir / "apps" / name / "install.py"
                if install_py.exists():
                    import importlib.util

                    spec = importlib.util.spec_from_file_location(f"{name}.install", install_py)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "before_uninstall"):
                            await mod.before_uninstall(session, target_site)

                # Лічильники NamingSeries: префікси, що походять з autoname доктайпів
                ns_table = compile_doctype_to_table(await doctype_registry.get("NamingSeries"))
                for dt in app_doctypes:
                    autoname = (dt.autoname or "").strip()
                    if not autoname or autoname.startswith("field:"):
                        continue
                    head = autoname.removeprefix("format:").split(".", 1)[0]
                    if head:
                        await session.execute(
                            ns_table.delete().where(ns_table.c.prefix.like(f"{head}%"))
                        )

                if has_workspace:
                    await grunt.db.delete("WorkspaceSidebarItem", {"parent_name": name})
                    await grunt.delete_doc("AppMenu", name)
                if has_installed_row:
                    await grunt.delete_doc("GruntInstalledApp", name)

                for dt in app_doctypes:
                    await doctype_registry.delete(dt.name, session)

            await session.commit()

        # DDL після коміту, окремим з'єднанням — інакше SQLite тримає lock
        async with eng.begin() as conn:
            for _dt_name, table, cnt in plan:
                if cnt is not None:
                    await conn.run_sync(
                        lambda sync_conn, t=table: t.drop(sync_conn, checkfirst=True)
                    )

        if vacuum and eng.dialect.name == "sqlite":
            # VACUUM не має SQLAlchemy-еквівалента і вимагає autocommit
            async with eng.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.exec_driver_sql("VACUUM")
    finally:
        current_site.reset(token)

    _unregister()
    click.echo(f"✓ Додаток '{name}' видалено з сайту {target_site}, дані очищено")
    click.echo(f"  Додатки: {', '.join(installed)}")


@app_group.command("uninstall")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
@click.option(
    "--keep-data",
    is_flag=True,
    default=False,
    help="Лише зняти реєстрацію додатку, дані в БД залишити",
)
@click.option("--yes", "-y", "assume_yes", is_flag=True, default=False, help="Без підтвердження")
@click.option(
    "--vacuum",
    is_flag=True,
    default=False,
    help="Стиснути файл БД після очищення (лише SQLite)",
)
def app_uninstall(name: str, site: str | None, keep_data: bool, assume_yes: bool, vacuum: bool):
    """Видалити додаток із сайту та очистити його дані в БД."""
    asyncio.run(
        _do_uninstall(name, site, keep_data=keep_data, assume_yes=assume_yes, vacuum=vacuum)
    )


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
