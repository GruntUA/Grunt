import asyncio
import json
from pathlib import Path

import click

from grunt.cli.utils import _site_session
from grunt.utils.strings import to_snake_case
lazy from grunt.metadata import store
lazy from grunt.metadata.doctype import DocType
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.site.manager import site_manager
lazy from grunt.startup.doctypes import _find_doctype_dirs
lazy from grunt.utils.codegen import (
    build_controller_context,
    render_template,
    sync_controller_types,
)


@click.group("doctype")
def doctype_group():
    """DocType management commands."""
    pass


@doctype_group.command("sync")
@click.argument("name")
@click.option("--site", default=None, help="Site name")
def doctype_sync(name: str, site: str | None):
    """Sync a DocType: re-read its JSON from disk, update the database and the table schema."""

    async def _run():

        # Find JSON file across all grunt/*/doctypes/ and app doctypes/, tracking
        # which app owns each search dir so we can both stamp DocType.app (core
        # doctype JSON never sets it - only the startup path did, until now) and
        # refuse to silently push one app's definition over another's.
        json_file = None
        owning_app = "grunt"

        search_dirs: list[tuple[Path, str]] = [(d, "grunt") for d in _find_doctype_dirs()]
        # Also search installed app doctypes
        if site_manager.bench_dir:
            for app_dir in sorted((site_manager.bench_dir / "apps").iterdir()):
                dt_dir = app_dir / app_dir.name / "doctypes"
                if dt_dir.is_dir():
                    search_dirs.append((dt_dir, app_dir.name))
                dt_dir2 = app_dir / "doctypes"
                if dt_dir2.is_dir():
                    search_dirs.append((dt_dir2, app_dir.name))

        for dt_dir, app_name in search_dirs:
            candidate = dt_dir / name / f"{name}.json"
            if candidate.exists():
                json_file = candidate
                owning_app = app_name
                break
            # Fallback: snake_case filename
            snake = to_snake_case(name)
            candidate2 = dt_dir / name / f"{snake}.json"
            if candidate2.exists():
                json_file = candidate2
                owning_app = app_name
                break

        if json_file is None:
            click.echo(f"Error: JSON file for '{name}' not found.", err=True)
            raise SystemExit(1)

        dt_data = json.loads(json_file.read_text())
        dt = DocType.model_validate(dt_data)
        if not dt.app:
            dt.app = owning_app

        async with _site_session(site) as (session, eng):
            # The DocType table itself may lag behind DocType.json (new property
            # columns) when only alembic ran - bring it up to date first.
            await store.ensure_table(session)
            existing_data = await store.get_definition(session, dt.name)
            if existing_data is not None:
                existing_app = existing_data.get("app")
                if existing_app and existing_app != owning_app:
                    click.echo(
                        f"Error: DocType '{name}' belongs to app '{existing_app}', "
                        f"but the file found belongs to app '{owning_app}' "
                        f"({json_file}). Sync cancelled.",
                        err=True,
                    )
                    raise SystemExit(1)
                await doctype_registry.update(dt, session, eng)
                action = "updated"
            else:
                await doctype_registry.register(dt, session, eng)
                action = "registered"
            await session.commit()

        click.echo(f"DocType '{name}' {action} from {json_file.relative_to(json_file.parents[3])}.")

    asyncio.run(_run())


@doctype_group.command("list")
@click.option("--site", default=None, help="Site name")
def doctype_list(site: str | None):
    """List all DocTypes."""

    async def _run():

        async with _site_session(site) as (session, _eng):
            all_dts = await doctype_registry.list_all()
            if not all_dts:
                click.echo("No DocTypes found.")
                return
            click.echo(f"{'Name':<35} {'Module':<20}")
            click.echo("-" * 55)
            for dt in sorted(all_dts, key=lambda d: d.name):
                click.echo(f"{dt.name:<35} {dt.module:<20}")

    asyncio.run(_run())


@doctype_group.command("scaffold")
@click.argument("name")
@click.option("--app", default="web", help="App folder to place the DocType in (default: web)")
@click.option("--module", default=None, help="Module (default: app name)")
@click.option("--force", is_flag=True, help="Overwrite existing files")
def doctype_scaffold(name: str, app: str, module: str | None, force: bool):
    """Create a new DocType from templates.

    Generates the folder structure:
        {app}/doctypes/{Name}/
            ├── {Name}.json          # DocType metadata
            ├── {Name}.py            # controller with auto-generated types
            ├── {Name}.js            # client script
            └── __init__.py
    """

    if not name or name[0].islower():
        click.echo("Error: the DocType name must start with an uppercase letter.", err=True)
        raise SystemExit(1)

    app_path = site_manager.bench_dir / "apps" / app
    if not app_path.exists():
        click.echo(f"Error: app '{app}' not found at {app_path}.", err=True)
        raise SystemExit(1)

    doctype_dir = app_path / "doctypes" / name
    if doctype_dir.exists() and not force:
        click.echo(
            f"Error: folder {doctype_dir} already exists. Use --force to overwrite.",
            err=True,
        )
        raise SystemExit(1)

    doctype_dir.mkdir(parents=True, exist_ok=True)

    module_name = module or app
    initial_fields = [{"fieldname": "name", "label": "Name", "fieldtype": "Data", "required": True}]

    # 1. JSON metadata
    json_content = {
        "name": name,
        "label": name,
        "module": module_name,
        "doctype": "DocType",
        "fields": initial_fields,
    }
    json_file = doctype_dir / f"{to_snake_case(name)}.json"
    json_file.write_text(json.dumps(json_content, ensure_ascii=False, indent=2) + "\n")

    # 2. Python controller via Jinja template
    py_ctx = build_controller_context(name, initial_fields)
    py_file = doctype_dir / f"{to_snake_case(name)}.py"
    py_file.write_text(render_template("doctype/controller.py.jinja", py_ctx))

    # 3. JS client script via Jinja template
    js_file = doctype_dir / f"{to_snake_case(name)}.js"
    js_file.write_text(render_template("doctype/client_script.js.jinja", {"name": name}))

    # 4. __init__.py
    (doctype_dir / "__init__.py").write_text("")

    try:
        rel_path = doctype_dir.relative_to(Path.cwd())
    except ValueError:
        rel_path = doctype_dir

    click.echo(f"✓ Created DocType '{name}' in {rel_path}")
    click.echo(f"  ├── {to_snake_case(name)}.json")
    click.echo(f"  ├── {to_snake_case(name)}.py  (controller with auto-generated types)")
    click.echo(f"  ├── {to_snake_case(name)}.js  (client script)")
    click.echo("  └── __init__.py")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"1. Edit {name}.json to define the fields")
    click.echo(f"2. Run: grunt doctype sync-types {name} --app {app}")
    click.echo("3. Run: grunt serve --reload")


def _controller_file(json_file: Path) -> Path | None:
    """The DocType's controller: <Name>.py in apps, <name_snake>.py in the core."""
    for candidate in (json_file.stem, to_snake_case(json_file.stem)):
        py_file = json_file.parent / f"{candidate}.py"
        if py_file.exists():
            return py_file
    return None


@doctype_group.command("sync-types")
@click.argument("name", required=False)
@click.option("--app", required=True, help="App folder containing the DocType")
@click.option("--all", "all_doctypes", is_flag=True, help="Update all DocTypes in the app")
def doctype_sync_types(name: str | None, app: str, all_doctypes: bool):
    """Update the auto-generated types in the controller from the JSON metadata.

    Replaces only the block between:
        # begin: auto-generated types
        # end: auto-generated types
    The rest of the controller code is left untouched.

    \b
    Examples:
      grunt doctype sync-types Invoice --app crm
      grunt doctype sync-types --all --app crm
    """

    app_path = site_manager.bench_dir / "apps" / app
    # DocTypes live in the app's modules: apps/<app>/<module>/doctypes/<Name>/
    # (the framework's own one level deeper: apps/grunt/grunt/<module>/doctypes/).
    json_files = sorted(
        [*app_path.glob("*/doctypes/*/*.json"), *app_path.glob("*/*/doctypes/*/*.json")]
    )

    if all_doctypes:
        updated = 0
        skipped = 0
        for json_file in json_files:
            dt_name = json_file.stem
            py_file = _controller_file(json_file)
            if py_file is None:
                continue
            try:
                fields = json.loads(json_file.read_text()).get("fields", [])
                changed = sync_controller_types(py_file, dt_name, fields)
                if changed:
                    click.echo(f"  ✓ {dt_name}")
                    updated += 1
                else:
                    skipped += 1
            except Exception as exc:
                click.echo(f"  ! {dt_name}: {exc}", err=True)
        click.echo(f"\nUpdated: {updated}, unchanged: {skipped}")
        return

    if not name:
        click.echo("Error: give a DocType name or --all.", err=True)
        raise SystemExit(1)
    json_file = next((f for f in json_files if f.stem == name and f.parent.name == name), None)
    if json_file is None:
        click.echo(f"Error: DocType {name} not found in {app_path}/*/doctypes/.", err=True)
        raise SystemExit(1)
    py_file = _controller_file(json_file) or json_file.parent / f"{name}.py"
    if not py_file.exists():
        click.echo(f"Error: {py_file} not found.", err=True)
        raise SystemExit(1)

    fields = json.loads(json_file.read_text()).get("fields", [])
    changed = sync_controller_types(py_file, name, fields)
    if changed:
        click.echo(f"✓ Types updated: {py_file}")
    else:
        click.echo(f"Unchanged: {py_file}")
