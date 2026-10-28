import asyncio
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
lazy import tarfile

import click
from sqlalchemy import func, inspect, select

lazy import grunt
lazy from grunt.apps.deps import app_updates, install_app_packages, uninstall_app_package
lazy from grunt.apps.manifest import is_app, read_manifest
lazy from grunt.apps.required import (
    CORE_APP,
    DependencyCycleError,
    MissingAppError,
    clone_missing,
    dependents,
)
lazy from grunt.backups import DEFAULT_COMPRESSION_LEVEL, zstd_options
lazy from grunt.metadata.compiler import SA_METADATA, compile_doctype_to_table
lazy from grunt.metadata.extensions import extensions_for_site
lazy from grunt.metadata.field import is_physical_fieldtype
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.site.manager import current_site, site_manager
lazy from grunt.startup import load_core_doctypes, sync_installed_apps
lazy from grunt.utils.app_helpers import load_app_hook_module
lazy from grunt.utils.boilerplate import make_boilerplate


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

    dest_path = Path(dest) if dest else site_manager.bench_dir / "apps"
    dest_path.mkdir(parents=True, exist_ok=True)
    make_boilerplate(dest_path, name, no_git=no_git)


async def _do_install(name: str, site: str | None = None) -> None:
    """Встановлює додаток: реєструє в grunt.site, завантажує DocTypes, fixtures, after_install."""

    _sites = site_manager.get_sites()
    target_site = site or (_sites[0] if _sites else None)
    if target_site is None:
        raise SystemExit("Error: site not found.")

    app_dir = site_manager.bench_dir / "apps" / name
    if not app_dir.is_dir():
        raise SystemExit(f"Error: directory '{app_dir}' does not exist.")
    if not is_app(app_dir):
        raise SystemExit(f"Error: '{app_dir / 'pyproject.toml'}' has no [tool.grunt] section.")

    app_meta = read_manifest(app_dir)

    # Реєструємо в grunt.site
    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text())
    installed = site_config.get("installed_apps", [])
    if name not in installed:
        installed.append(name)
        site_config["installed_apps"] = installed
        site_file.write_text(json.dumps(site_config, ensure_ascii=False, indent=2))

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
            # again (sync_db=True - same as `grunt migrate`).
            await load_core_doctypes(
                session, sync_db=True, extensions=extensions_for_site(target_site)
            )
            await doctype_registry.load_all(session)
            async with grunt.system_context(session, eng):
                await sync_installed_apps(session, target_site)
            await session.commit()
    finally:
        current_site.reset(token)

    title = app_meta["title"]
    print(f"✓ App {title} installed on site {target_site}")
    print(f"  Apps: {', '.join(site_manager.get_installed_apps(target_site))}")


def _apps_dir() -> Path:

    return site_manager.bench_dir / "apps"


@app_group.command("deps")
@click.argument("names", nargs=-1)
@click.option(
    "--upgrade",
    is_flag=True,
    help="Also move the packages only apps depend on to their newest versions.",
)
@click.option(
    "--outdated",
    is_flag=True,
    help="Only list what --upgrade would move (`name old → new`, one per line).",
)
def app_deps(names: tuple[str, ...], upgrade: bool, outdated: bool):
    """Fetch the apps bench apps depend on, then install their Python dependencies.

    Clones the missing ``depends_on`` apps (from their ``url``), then installs
    apps/<app>/pyproject.toml packages. Without arguments, all apps. Runs after
    the framework's `uv sync` (so `grunt update` brings new dependencies in).
    With --upgrade (`grunt update --upgrade-packages`), the packages not pinned
    by the framework's uv.lock go to their newest versions.
    """

    if outdated:
        for line in app_updates(_apps_dir()):
            click.echo(line)
        return
    try:
        cloned = clone_missing(_apps_dir(), list(names) or None)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"git clone failed: {' '.join(map(str, e.cmd))}") from e
    if cloned:
        click.echo(f"Cloned dependencies: {', '.join(cloned)}")
    installed = install_app_packages(
        _apps_dir(), [*names, *cloned] if names else None, upgrade=upgrade
    )
    click.echo(f"App dependencies: {', '.join(installed) or 'no apps with pyproject.toml'}")


@app_group.command("install")
@click.argument("name")
@click.option("--site", default=None, help="Site name")
def app_install(name: str, site: str | None):
    """Install an app (and the apps it depends_on) and register its workspace right away."""

    cloned = clone_missing(_apps_dir(), [name])
    if cloned:
        click.echo(f"Cloned dependencies: {', '.join(cloned)}")
    install_app_packages(_apps_dir(), [name, *cloned])  # their Python dependencies first
    try:
        asyncio.run(_do_install(name, site))
    except (MissingAppError, DependencyCycleError) as e:
        raise click.ClickException(str(e)) from e


async def _plan_app_uninstall(session, app_doctypes: list) -> list:
    """Compile each app DocType's table and count its rows.

    Returns ``[(doctype_name, table, row_count | None)]`` - count is None
    when the table doesn't exist (or can't be counted), used later to skip
    the DROP TABLE step for it.
    """

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
    contributed_rows: int = 0,
    ext_fields: list | None = None,
) -> None:
    click.echo(f"Site: {target_site}. Will be removed:")
    for dt_name, table, cnt in plan:
        rows = "no table" if cnt is None else f"{cnt} rows"
        click.echo(f"  • DocType {dt_name} ({getattr(table, 'name', '?')}: {rows})")
    if has_workspace:
        click.echo(f"  • Workspace '{name}' with its menu items")
    if contributed_rows:
        click.echo(f"  • {contributed_rows} menu rows it added to other apps' menus")
    for dt, fields in ext_fields or []:
        names = ", ".join(f.fieldname for f in fields)
        click.echo(f"  • Fields it added to DocType {dt.name}: {names}")
    if has_installed_row:
        click.echo(f"  • GruntInstalledApp record '{name}'")


async def _run_before_uninstall_hook(session, target_site: str, name: str) -> None:
    """Call apps/<name>/install.py:before_uninstall(session, site), if defined."""

    install_mod = load_app_hook_module(site_manager.bench_dir / "apps" / name, name)
    if install_mod is not None and hasattr(install_mod, "before_uninstall"):
        await install_mod.before_uninstall(session, target_site)


async def _delete_naming_series_counters(session, app_doctypes: list) -> None:
    """Clear NamingSeries prefix counters derived from this app's autoname doctypes."""

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


_MENU_CHILDREN = ("WorkspaceSidebarItem", "WorkspaceSection")


async def _delete_workspace_and_registration(
    *, name: str, has_workspace: bool, has_installed_row: bool
) -> None:

    # Sections and items the app contributed to other apps' menus (source_app).
    for child in _MENU_CHILDREN:
        await grunt.db.delete(child, {"source_app": name})
    if has_workspace:
        await grunt.db.delete("WorkspaceSidebarItem", {"parent_name": name})
        await grunt.delete_doc("AppMenu", name)
    if has_installed_row:
        await grunt.delete_doc("GruntInstalledApp", name)


def _extension_fields(name: str, doctypes: list, skip: set[str]) -> list:
    """``[(doctype, [fields])]`` - fields *name* added to other DocTypes (``doctype_ext/``)."""
    found = []
    for dt in doctypes:
        mine = [f for f in dt.fields if f.source_app == name]
        if mine and dt.name not in skip:
            found.append((dt, mine))
    return found


async def _strip_extension_fields(session, eng, ext_fields: list) -> None:
    for dt, fields in ext_fields:
        base = dt.model_copy(deep=True)
        drop = {f.fieldname for f in fields}
        base.fields = [f for f in base.fields if f.fieldname not in drop]
        await doctype_registry.update(base, session, eng)


async def _drop_extension_columns(eng, ext_fields: list) -> None:
    """DROP COLUMN for the removed extension fields (with their indexes first -
    SQLite refuses to drop an indexed column). A failure is reported, not fatal:
    the field is already gone from the DocType, only its data stays."""
    prep = eng.dialect.identifier_preparer
    for dt, fields in ext_fields:
        table = compile_doctype_to_table(dt).name  # cached Table may already lack the columns
        for field in fields:
            if not is_physical_fieldtype(field.fieldtype):
                continue
            try:
                async with eng.begin() as conn:
                    indexes = await conn.run_sync(lambda c, t=table: inspect(c).get_indexes(t))
                    for index in indexes:
                        if field.fieldname in index["column_names"]:
                            await conn.exec_driver_sql(f"DROP INDEX {prep.quote(index['name'])}")
                    await conn.exec_driver_sql(
                        f"ALTER TABLE {prep.quote(table)} DROP COLUMN {prep.quote(field.fieldname)}"
                    )
            except Exception as e:
                click.echo(f"  ! {table}.{field.fieldname} not dropped: {e}", err=True)


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

    _sites = site_manager.get_sites()
    target_site = site or (_sites[0] if _sites else None)
    if target_site is None:
        raise SystemExit("Error: site not found.")
    if name == "grunt":
        raise SystemExit("Error: the base grunt app cannot be removed.")

    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text())
    installed: list[str] = site_config.get("installed_apps", [])
    is_registered = name in installed

    def _unregister() -> None:
        if name in installed:
            installed.remove(name)
            site_config["installed_apps"] = installed
            site_file.write_text(json.dumps(site_config, ensure_ascii=False, indent=2))

    if keep_data:
        if not is_registered:
            raise SystemExit(f"Error: app '{name}' is not installed.")
        _unregister()
        click.echo(f"✓ App '{name}' removed from site {target_site} (data kept)")
        click.echo(f"  Apps: {', '.join(installed)}")
        return

    # Модулі додатку - з маніфесту; якщо директорії вже немає, це [name]
    app_modules = read_manifest(site_manager.bench_dir / "apps" / name)["modules"]

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        plan: list = []
        ext_fields: list = []

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
                contributed_rows = sum(
                    [await grunt.db.count(c, {"source_app": name}) for c in _MENU_CHILDREN]
                )
                ext_fields = _extension_fields(
                    name,
                    await doctype_registry.list_all(),
                    skip={dt.name for dt in app_doctypes},
                )

                if not (
                    is_registered
                    or app_doctypes
                    or has_installed_row
                    or has_workspace
                    or contributed_rows
                    or ext_fields
                ):
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
                    contributed_rows=contributed_rows,
                    ext_fields=ext_fields,
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
                await _strip_extension_fields(session, eng, ext_fields)

            await session.commit()

        # DDL після коміту, окремим з'єднанням - інакше SQLite тримає lock
        await _drop_app_tables(eng, plan)
        await _drop_extension_columns(eng, ext_fields)

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


# Regenerable by `grunt app get`/`uv sync`/`npm install` - not worth archiving.
_ARCHIVE_SKIP = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}


def _archive_path(name: str) -> Path:
    """archive/apps/<name>-<date>.tar.zst in the bench, unused (time added on a clash)."""

    now = datetime.now()
    base = site_manager.bench_dir / "archive" / "apps"
    target = base / f"{name}-{now:%Y-%m-%d}.tar.zst"
    if target.exists():
        target = base / f"{name}-{now:%Y-%m-%d-%H%M%S}.tar.zst"
    return target


def _archive_app(app_dir: Path, target: Path) -> None:
    """Pack *app_dir* into a zstd tarball (unpacks to <name>/)."""

    def _skip(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        return None if Path(info.name).name in _ARCHIVE_SKIP else info

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    with tarfile.open(partial, "w:zst", options=zstd_options(DEFAULT_COMPRESSION_LEVEL)) as tar:
        tar.add(app_dir, arcname=app_dir.name, filter=_skip)
    partial.rename(target)


@app_group.command("remove")
@click.argument("name")
@click.option(
    "--no-archive",
    is_flag=True,
    default=False,
    help="Delete the app directory instead of packing it into archive/apps/",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Remove even if a site has it installed or another app depends on it",
)
@click.option("--yes", "-y", "assume_yes", is_flag=True, default=False, help="No confirmation")
def app_remove(name: str, no_archive: bool, force: bool, assume_yes: bool):
    """Remove an app from the bench (like `bench remove-app`).

    Uninstalls its Python package and packs apps/NAME into
    archive/apps/NAME-<date>.tar.zst (unpack: tar --zstd -xf FILE -C apps/).
    The sites must not have it installed - run `grunt app uninstall NAME` first.
    """

    if name == CORE_APP:
        raise click.ClickException("the base grunt app cannot be removed.")
    app_dir = _apps_dir() / name
    if not app_dir.is_dir():
        raise click.ClickException(f"app '{name}' is not in the bench ({app_dir}).")

    problems = [
        f"installed on site {site} - `grunt app uninstall {name} --site {site}`"
        for site in site_manager.get_sites()
        if name in site_manager.get_installed_apps(site)
    ]
    problems += [f"app '{user}' depends on it" for user in dependents(_apps_dir(), name)]
    if problems:
        details = "\n".join(f"  • {p}" for p in problems)
        if not force:
            raise click.ClickException(f"cannot remove '{name}':\n{details}")
        click.echo(click.style(f"Removing anyway (--force):\n{details}", fg="yellow"))

    target = None if no_archive else _archive_path(name)
    action = "delete" if target is None else f"pack into {target}"
    if not assume_yes and not click.confirm(f"Remove app '{name}' ({action})?"):
        raise SystemExit("Cancelled.")

    try:
        package = uninstall_app_package(app_dir)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"package uninstall failed: {' '.join(map(str, e.cmd))}") from e
    if package:
        click.echo(f"  Python package {package} uninstalled")

    if target is not None:
        _archive_app(app_dir, target)
    shutil.rmtree(app_dir)
    click.echo(f"✓ App '{name}' removed" + ("" if target is None else f", archived to {target}"))


@app_group.command("list")
@click.option("--site", default=None, help="Site name")
def app_list(site: str | None):
    """Show installed apps."""

    _sites = site_manager.get_sites()
    target_site: str | None = site or (_sites[0] if _sites else None)
    if target_site is None:
        click.echo("Error: site not found.", err=True)
        raise SystemExit(1)

    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text())
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
                    gitignore.write_text(content)

                click.echo(f"  {click.style('✓', fg='green')} Git repository created.")
            except Exception as e:
                click.echo(f"  {click.style('✗', fg='red')} Git initialization failed: {e}")

        # 2. Перевірка маніфесту ([tool.grunt] у pyproject.toml)
        pyproject = app_path / "pyproject.toml"
        if not pyproject.exists():
            click.echo(f"  {click.style('✗', fg='red')} pyproject.toml is missing.")
        elif not is_app(app_path):
            click.echo(f"  [!] [tool.grunt] is missing. {click.style('Adding...', fg='yellow')}")
            title = json.dumps(app_name.replace("_", " ").title(), ensure_ascii=False)
            text = pyproject.read_text().rstrip("\n")
            pyproject.write_text(f"{text}\n\n[tool.grunt]\ntitle = {title}\n")
            click.echo(f"  {click.style('✓', fg='green')} [tool.grunt] added.")

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


@app_group.command("export")
@click.argument("name")
def app_export(name: str) -> None:
    """Copy the app's DocType JSON files to apps/<name>/exported_doctypes/ (no server needed)."""
    app_dir = site_manager.bench_dir / "apps" / name
    if not app_dir.is_dir():
        click.echo(f"Error: app '{name}' not found ({app_dir}).", err=True)
        raise SystemExit(1)
    dt_files = sorted(app_dir.glob("*/doctypes/*/*.json"))
    if not dt_files:
        click.echo(f"No DocType JSON found in {app_dir}.")
        return
    out_dir = app_dir / "exported_doctypes"
    out_dir.mkdir(exist_ok=True)
    for dt_file in dt_files:
        shutil.copyfile(dt_file, out_dir / dt_file.name)
    click.echo(f"✓ Exported {len(dt_files)} DocType(s) to {out_dir}")
