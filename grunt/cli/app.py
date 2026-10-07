import asyncio
from pathlib import Path

import click


@click.group("app")
def app_group():
    """Manage installed apps."""
    pass


@app_group.command("create")
@click.argument("name")
@click.option("--no-git", is_flag=True, default=False, help="Do not initialize a git repository")
@click.option(
    "--dest",
    default=None,
    help="Directory to create the app in (default: bench_dir/apps/)",
)
def create_app(name: str, no_git: bool, dest: str | None):
    """Create a new Grunt app (scaffold).

    NAME is the app name (snake_case), e.g. my_crm
    """
    from grunt.site.manager import site_manager
    from grunt.utils.boilerplate import make_boilerplate

    dest_path = Path(dest) if dest else site_manager.bench_dir / "apps"
    dest_path.mkdir(parents=True, exist_ok=True)
    make_boilerplate(dest_path, name, no_git=no_git)


async def _do_install(name: str, site: str | None = None) -> None:
    """Встановлює додаток: реєструє в grunt.site, завантажує DocTypes, fixtures, after_install."""
    import json

    import grunt
    from grunt.metadata.compiler import SA_METADATA
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import current_site, site_manager
    from grunt.startup import load_core_doctypes, sync_installed_apps

    _sites = site_manager.get_sites()
    target_site = site or (_sites[0] if _sites else None)
    if target_site is None:
        raise SystemExit("Error: site not found.")

    app_dir = site_manager.bench_dir / "apps" / name
    app_json = app_dir / "app.json"
    if not app_dir.is_dir():
        raise SystemExit(f"Error: directory '{app_dir}' does not exist.")
    if not app_json.exists():
        raise SystemExit(f"Error: '{app_json}' not found.")

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
            await conn.run_sync(SA_METADATA.create_all)

        async with maker() as session:
            # New app: seed its core DocTypes into the DocType table so the
            # server can lazy-load them without ever touching the JSON files
            # again (sync_db=True - same as `grunt db migrate`).
            await load_core_doctypes(session, sync_db=True)
            await doctype_registry.load_all(session)
            async with grunt.system_context(session, eng):
                await sync_installed_apps(session, target_site)
            await session.commit()
    finally:
        current_site.reset(token)

    title = app_meta.get("title", name)
    print(f"✓ App {title} installed on site {target_site}")
    print(f"  Apps: {', '.join(site_config.get('installed_apps', []))}")


def _apps_dir() -> Path:
    from grunt.site.manager import site_manager

    return site_manager.bench_dir / "apps"


@app_group.command("deps")
@click.argument("names", nargs=-1)
def app_deps(names: tuple[str, ...]):
    """Install the Python dependencies of bench apps (apps/<app>/pyproject.toml).

    Without arguments, all apps. Runs after the framework's `uv sync`.
    """
    from grunt.apps.deps import install_app_packages

    installed = install_app_packages(_apps_dir(), list(names) or None)
    click.echo(f"App dependencies: {', '.join(installed) or 'no apps with pyproject.toml'}")


@app_group.command("install")
@click.argument("name")
@click.option("--site", default=None, help="Site name")
def app_install(name: str, site: str | None):
    """Install an app and register its workspace right away."""
    from grunt.apps.deps import install_app_packages

    install_app_packages(_apps_dir(), [name])  # its Python dependencies first
    asyncio.run(_do_install(name, site))


async def _plan_app_uninstall(session, app_doctypes: list) -> list:
    """Compile each app DocType's table and count its rows.

    Returns ``[(doctype_name, table, row_count | None)]`` - count is None
    when the table doesn't exist (or can't be counted), used later to skip
    the DROP TABLE step for it.
    """
    from sqlalchemy import func, select

    from grunt.metadata.compiler import compile_doctype_to_table

    plan = []
    for dt in app_doctypes:
        table = compile_doctype_to_table(dt)
        try:
            cnt = (await session.execute(select(func.count()).select_from(table))).scalar() or 0
        except Exception:
            cnt = None
        plan.append((dt.name, table, cnt))
    return plan


def _print_uninstall_plan(
    target_site: str,
    plan: list,
    *,
    name: str,
    has_workspace: bool,
    has_installed_row: bool,
) -> None:
    click.echo(f"Site: {target_site}. Will be removed:")
    for dt_name, table, cnt in plan:
        rows = "no table" if cnt is None else f"{cnt} rows"
        click.echo(f"  • DocType {dt_name} ({getattr(table, 'name', '?')}: {rows})")
    if has_workspace:
        click.echo(f"  • Workspace '{name}' with its menu items")
    if has_installed_row:
        click.echo(f"  • GruntInstalledApp record '{name}'")


async def _run_before_uninstall_hook(session, target_site: str, name: str) -> None:
    """Call apps/<name>/install.py:before_uninstall(session, site), if defined."""
    from grunt.site.manager import site_manager
    from grunt.utils.app_helpers import load_app_hook_module

    install_mod = load_app_hook_module(site_manager.bench_dir / "apps" / name, name)
    if install_mod is not None and hasattr(install_mod, "before_uninstall"):
        await install_mod.before_uninstall(session, target_site)


async def _delete_naming_series_counters(session, app_doctypes: list) -> None:
    """Clear NamingSeries prefix counters derived from this app's autoname doctypes."""
    import grunt

    ns_dt = await grunt.get_meta("NamingSeries")
    if ns_dt is None:
        raise SystemExit("Error: DocType 'NamingSeries' not found.")
    ns_table = ns_dt.table
    for dt in app_doctypes:
        autoname = (dt.autoname or "").strip()
        if not autoname or autoname.startswith("field:"):
            continue
        head = autoname.removeprefix("format:").split(".", 1)[0]
        if head:
            await session.execute(ns_table.delete().where(ns_table.c.prefix.like(f"{head}%")))


async def _delete_workspace_and_registration(
    *, name: str, has_workspace: bool, has_installed_row: bool
) -> None:
    import grunt

    if has_workspace:
        await grunt.db.delete("WorkspaceSidebarItem", {"parent_name": name})
        await grunt.delete_doc("AppMenu", name)
    if has_installed_row:
        await grunt.delete_doc("GruntInstalledApp", name)


async def _drop_app_tables(eng, plan: list) -> None:
    """DROP TABLE for each planned table, on a separate connection/transaction.

    Run after the main session commits - doing DDL on the same SQLite
    connection while it still holds the delete transaction's lock fails.
    """
    async with eng.begin() as conn:
        for _dt_name, table, cnt in plan:
            if cnt is not None:
                await conn.run_sync(lambda sync_conn, t=table: t.drop(sync_conn, checkfirst=True))


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

    import grunt
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import current_site, site_manager

    _sites = site_manager.get_sites()
    target_site = site or (_sites[0] if _sites else None)
    if target_site is None:
        raise SystemExit("Error: site not found.")
    if name == "grunt":
        raise SystemExit("Error: the base grunt app cannot be removed.")

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
            raise SystemExit(f"Error: app '{name}' is not installed.")
        _unregister()
        click.echo(f"✓ App '{name}' removed from site {target_site} (data kept)")
        click.echo(f"  Apps: {', '.join(installed)}")
        return

    # Модулі додатку - з app.json; якщо директорії вже немає, fallback на name
    app_modules = [name]
    app_json = site_manager.bench_dir / "apps" / name / "app.json"
    if app_json.exists():
        app_modules = json.loads(app_json.read_text(encoding="utf-8")).get("modules") or [name]

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        plan: list = []

        async with maker() as session:
            # Uninstalling: the app's DocTypes already exist in
            # the DocType table from when it was installed - hydrate from
            # there, no need to re-parse its JSON files.
            await doctype_registry.load_all(session)

            app_doctypes = [
                dt for dt in await doctype_registry.list_all() if dt.module in app_modules
            ]

            async with grunt.system_context(session, eng):
                has_installed_row = bool(await grunt.exists("GruntInstalledApp", {"name": name}))
                has_workspace = bool(await grunt.exists("AppMenu", {"name": name}))

                if not (is_registered or app_doctypes or has_installed_row or has_workspace):
                    raise SystemExit(
                        f"Error: app '{name}' is not installed and has no traces in the database."
                    )

                plan = await _plan_app_uninstall(session, app_doctypes)
                _print_uninstall_plan(
                    target_site,
                    plan,
                    name=name,
                    has_workspace=has_workspace,
                    has_installed_row=has_installed_row,
                )

                if not assume_yes and not click.confirm(
                    "Continue? The data will be lost permanently"
                ):
                    raise SystemExit("Cancelled.")

                await _run_before_uninstall_hook(session, target_site, name)
                await _delete_naming_series_counters(session, app_doctypes)
                await _delete_workspace_and_registration(
                    name=name,
                    has_workspace=has_workspace,
                    has_installed_row=has_installed_row,
                )

                for dt in app_doctypes:
                    await doctype_registry.delete(dt.name, session)

            await session.commit()

        # DDL після коміту, окремим з'єднанням - інакше SQLite тримає lock
        await _drop_app_tables(eng, plan)

        if vacuum and eng.dialect.name == "sqlite":
            # VACUUM не має SQLAlchemy-еквівалента і вимагає autocommit
            async with eng.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.exec_driver_sql("VACUUM")
    finally:
        current_site.reset(token)

    _unregister()
    click.echo(f"✓ App '{name}' removed from site {target_site}, data cleared")
    click.echo(f"  Apps: {', '.join(installed)}")


@app_group.command("uninstall")
@click.argument("name")
@click.option("--site", default=None, help="Site name")
@click.option(
    "--keep-data",
    is_flag=True,
    default=False,
    help="Only unregister the app, keep its data in the database",
)
@click.option("--yes", "-y", "assume_yes", is_flag=True, default=False, help="No confirmation")
@click.option(
    "--vacuum",
    is_flag=True,
    default=False,
    help="Compact the database file after cleanup (SQLite only)",
)
def app_uninstall(name: str, site: str | None, keep_data: bool, assume_yes: bool, vacuum: bool):
    """Remove an app from the site and clear its data in the database."""
    asyncio.run(
        _do_uninstall(name, site, keep_data=keep_data, assume_yes=assume_yes, vacuum=vacuum)
    )


@app_group.command("list")
@click.option("--site", default=None, help="Site name")
def app_list(site: str | None):
    """Show installed apps."""
    import json

    from grunt.site.manager import site_manager

    _sites = site_manager.get_sites()
    target_site: str | None = site or (_sites[0] if _sites else None)
    if target_site is None:
        click.echo("Error: site not found.", err=True)
        raise SystemExit(1)

    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text(encoding="utf-8"))
    apps = site_config.get("installed_apps", [])
    click.echo(f"Site: {target_site}")
    for a in apps:
        click.echo(f"  • {a}")


@app_group.command("doctor")
@click.argument("name", required=False)
def app_doctor(name: str | None):
    """Check apps for structural errors and fix them.

    Without NAME, checks all apps.
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
        click.echo(f"🩺 Checking app: {click.style(app_name, fg='cyan')}")

        # 1. Перевірка Git
        git_dir = app_path / ".git"
        if not git_dir.is_dir():
            click.echo(f"  [!] Git is not initialized. {click.style('Fixing...', fg='yellow')}")
            try:
                subprocess.run(["git", "init"], cwd=str(app_path), check=True, capture_output=True)

                # Додаємо базовий .gitignore
                gitignore = app_path / ".gitignore"
                if not gitignore.exists():
                    content = "__pycache__/\n*.py[cod]\n.env\n.venv/\nnode_modules/\ndist/\n"
                    gitignore.write_text(content, encoding="utf-8")

                click.echo(f"  {click.style('✓', fg='green')} Git repository created.")
            except Exception as e:
                click.echo(f"  {click.style('✗', fg='red')} Git initialization failed: {e}")

        # 2. Перевірка app.json
        app_json = app_path / "app.json"
        if not app_json.exists():
            click.echo(f"  [!] app.json is missing. {click.style('Creating...', fg='yellow')}")
            import json

            basic_meta = {
                "name": app_name,
                "title": app_name.replace("_", " ").title(),
                "description": f"App {app_name}",
                "version": "0.1.0",
            }
            app_json.write_text(
                json.dumps(basic_meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            click.echo(f"  {click.style('✓', fg='green')} app.json created.")

        # 3. Перевірка пакету (__init__.py)
        pkg_dir = app_path / app_name
        if pkg_dir.is_dir():
            init_py = pkg_dir / "__init__.py"
            if not init_py.exists():
                click.echo(
                    f"  [!] {app_name}/__init__.py is missing. "
                    f"{click.style('Creating...', fg='yellow')}"
                )
                init_py.touch()
                click.echo(f"  {click.style('✓', fg='green')} __init__.py created.")

    click.echo(f"\n{click.style('Doctor finished!', bold=True)}")
