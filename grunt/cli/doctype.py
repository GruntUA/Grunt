import asyncio
import json
from pathlib import Path

import click

from grunt.cli.utils import AliasedGroup, _site_session
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
lazy from grunt.utils.testgen import generate_tests


@click.group("doctype", cls=AliasedGroup, aliases={"apply": "sync"})
def doctype_group():
    """DocType management commands."""
    pass


# Lookup


def _search_dirs() -> list[tuple[Path, str]]:
    """(doctypes dir, owning app): the framework's modules first, then every app."""
    search_dirs: list[tuple[Path, str]] = [(d, "grunt") for d in _find_doctype_dirs()]
    if site_manager.bench_dir:
        for app_dir in sorted((site_manager.bench_dir / "apps").iterdir()):
            if not app_dir.is_dir() or app_dir.name == "grunt":
                continue
            for dt_dir in (app_dir / app_dir.name / "doctypes", app_dir / "doctypes"):
                if dt_dir.is_dir():
                    search_dirs.append((dt_dir, app_dir.name))
    return search_dirs


def _find_doctype_json(name: str) -> tuple[Path, str] | None:
    """The DocType's JSON file on disk and the app that owns it."""
    for dt_dir, app_name in _search_dirs():
        # <Name>.json in apps, <name_snake>.json in the core
        for filename in (f"{name}.json", f"{to_snake_case(name)}.json"):
            candidate = dt_dir / name / filename
            if candidate.exists():
                return candidate, app_name
    return None


def _load_doctype_json(name: str) -> dict:
    found = _find_doctype_json(name)
    if found is None:
        click.echo(f"Error: JSON file for '{name}' not found.", err=True)
        raise SystemExit(1)
    return json.loads(found[0].read_text(encoding="utf-8"))


def _app_doctype_names(app: str | None) -> list[str]:
    """DocType names of one app (or of all apps when app is None), from the JSON on disk."""
    names = set()
    for dt_dir, app_name in _search_dirs():
        if app_name == "grunt" or (app is not None and app_name != app):
            continue
        names.update(p.parent.name for p in dt_dir.glob("*/*.json") if p.stem == p.parent.name)
    return sorted(names)


# sync / list


async def _sync_one(name: str, session, eng) -> bool:
    """Re-read one DocType's JSON from disk into the database. False on a user error."""
    # Track which app owns the file so we can both stamp DocType.app (core
    # doctype JSON never sets it - only the startup path did, until now) and
    # refuse to silently push one app's definition over another's.
    found = _find_doctype_json(name)
    if found is None:
        click.echo(f"Error: JSON file for '{name}' not found.", err=True)
        return False
    json_file, owning_app = found

    dt = DocType.model_validate(json.loads(json_file.read_text()))
    if not dt.app:
        dt.app = owning_app

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
            return False
        await doctype_registry.update(dt, session, eng)
        action = "updated"
    else:
        await doctype_registry.register(dt, session, eng)
        action = "registered"
    await session.commit()

    click.echo(f"DocType '{name}' {action} from {json_file.relative_to(json_file.parents[3])}.")
    return True


@doctype_group.command("sync")
@click.argument("names", nargs=-1, metavar="[NAME...]")
@click.option("--app", default=None, help="Sync every DocType of this app")
@click.option("--all", "all_apps", is_flag=True, help="Sync every DocType of every app")
@click.option("--site", default=None, help="Site name")
def doctype_sync(names: tuple[str, ...], app: str | None, all_apps: bool, site: str | None):
    """Sync DocTypes: re-read their JSON from disk, update the database and the table schema.

    \b
    Examples:
      grunt doctype sync Invoice Customer
      grunt doctype sync --app crm
      grunt doctype sync --all
    """
    if names:
        targets = list(names)
    elif app or all_apps:
        targets = _app_doctype_names(app)
        if not targets:
            click.echo("Nothing to sync.")
            return
    else:
        click.echo("Error: give DocType names, --app APP or --all.", err=True)
        raise SystemExit(1)

    async def _run() -> int:
        errors = 0
        async with _site_session(site) as (session, eng):
            # The DocType table itself may lag behind DocType.json (new property
            # columns) when only alembic ran - bring it up to date first.
            await store.ensure_table(session)
            for name in targets:
                if not await _sync_one(name, session, eng):
                    errors += 1
        return errors

    if asyncio.run(_run()):
        raise SystemExit(1)


@doctype_group.command("list")
@click.option("--module", default=None, help="Only DocTypes of this module")
@click.option("--site", default=None, help="Site name")
def doctype_list(module: str | None, site: str | None):
    """List all DocTypes."""

    async def _run():

        async with _site_session(site) as (session, _eng):
            all_dts = await doctype_registry.list_all()
            if module:
                all_dts = [dt for dt in all_dts if dt.module == module]
            if not all_dts:
                click.echo("No DocTypes found.")
                return
            click.echo(f"{'Name':<35} {'Module':<20}")
            click.echo("-" * 55)
            for dt in sorted(all_dts, key=lambda d: d.name):
                click.echo(f"{dt.name:<35} {dt.module:<20}")

    asyncio.run(_run())


# Files on disk: show / export / import / test-gen


_LAYOUT_FIELDTYPES = {"Section", "Column", "Tab"}


@doctype_group.command("show")
@click.argument("name")
def doctype_show(name: str):
    """Show a DocType and its fields (reads the JSON on disk)."""
    dt = _load_doctype_json(name)
    click.echo(f"{dt['name']}  {dt.get('label', '')}".rstrip())
    click.echo(f"Module: {dt.get('module', '')}\n")
    fields = [f for f in dt.get("fields", []) if f["fieldtype"] not in _LAYOUT_FIELDTYPES]
    rows = [
        (
            f["fieldname"],
            f.get("label", ""),
            f["fieldtype"],
            "✓" if f.get("required") else "",
            "✓" if f.get("in_list_view") else "",
        )
        for f in fields
    ]
    header = ("fieldname", "label", "type", "required", "in_list")
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        click.echo("  ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)).rstrip())


@doctype_group.command("export")
@click.argument("name")
@click.option("-o", "--output", default=None, help="Output file (default: <name>.json)")
def doctype_export(name: str, output: str | None):
    """Export a DocType's metadata to a JSON file (reads the JSON on disk, no server needed)."""
    dt = _load_doctype_json(name)
    output_file = Path(output or f"{name}.json")
    output_file.write_text(
        json.dumps({"doctype": dt}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    click.echo(f"✓ Exported DocType {name} to {output_file}")
    click.echo(f"  Import: grunt doctype import {output_file}")


@doctype_group.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--update", is_flag=True, help="Update the DocType if it already exists")
@click.option("--site", default=None, help="Site name")
def doctype_import(file: Path, update: bool, site: str | None):
    """Import DocType metadata from a JSON file (`grunt doctype export`) into the database."""
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"invalid JSON: {e}") from e

    if "doctype" in data:
        definitions = [data["doctype"]]
    elif "name" in data:
        definitions = [data]
    else:
        raise click.ClickException("the file needs a 'doctype' or 'name' key")
    definitions.extend(data.get("children", []))

    async def _run() -> int:
        errors = 0
        async with _site_session(site) as (session, eng):
            for dt_data in definitions:
                dt_name = dt_data.get("name", "?")
                try:
                    existing = await doctype_registry.get(dt_name)
                    if existing and not update:
                        click.echo(f"  ! {dt_name}: already exists (use --update)")
                        errors += 1
                        continue
                    dt = DocType.model_validate(dt_data)
                    await doctype_registry.update(dt, session, eng)
                    await session.commit()
                    click.echo(f"  ✓ {dt_name}: {'updated' if existing else 'created'}")
                except Exception as e:
                    click.echo(f"  ✗ {dt_name}: {e}")
                    errors += 1
        click.echo(f"\nImported: {len(definitions) - errors}, errors: {errors}")
        return errors

    if asyncio.run(_run()):
        raise SystemExit(1)


@doctype_group.command("test-gen")
@click.argument("name")
@click.option("-o", "--output", default=None, help="Output file (default: stdout)")
def doctype_test_gen(name: str, output: str | None):
    """Generate pytest tests for a DocType's REST API from its metadata.

    The tests expect `client` and `auth_headers` fixtures in the app's conftest.py.
    """
    content = generate_tests(_load_doctype_json(name))
    if not output:
        click.echo(content, nl=False)
        return
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    click.echo(f"✓ Tests written to {output}")
    click.echo(f"  Run: pytest {output} -v")


# Code generation: scaffold / sync-types


def _pick_app(apps_dir: Path) -> Path:
    """The only app in the bench, or the one the user picks."""
    app_dirs = sorted(
        d
        for d in apps_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name != "grunt"
    )
    if not app_dirs:
        click.echo(f"Error: no apps in {apps_dir}.", err=True)
        raise SystemExit(1)
    if len(app_dirs) == 1:
        return app_dirs[0]
    click.echo("Choose the app:")
    for i, d in enumerate(app_dirs, 1):
        click.echo(f"  {i}. {d.name}")
    return app_dirs[click.prompt("Number", type=click.IntRange(1, len(app_dirs))) - 1]


def _write_controller(json_file: Path, name: str) -> Path:
    fields = json.loads(json_file.read_text(encoding="utf-8")).get("fields", [])
    py_file = _controller_file(json_file) or json_file.parent / f"{name}.py"
    py_file.write_text(
        render_template("doctype/controller.py.jinja", build_controller_context(name, fields))
    )
    return py_file


@doctype_group.command("scaffold")
@click.argument("name")
@click.option("--app", default=None, help="App to place the DocType in (default: ask)")
@click.option("--module", default=None, help="Module package inside the app (default: the app's)")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option(
    "--py-only", is_flag=True, help="Only regenerate the controller of an existing DocType"
)
def doctype_scaffold(name: str, app: str | None, module: str | None, force: bool, py_only: bool):
    """Create a new DocType from templates.

    Generates the folder structure:
        apps/{app}/{module}/doctypes/{Name}/
            ├── {Name}.json          # DocType metadata
            ├── {Name}.py            # controller with auto-generated types
            ├── {Name}.js            # client script
            └── __init__.py
    """

    if not name or name[0].islower():
        click.echo("Error: the DocType name must start with an uppercase letter.", err=True)
        raise SystemExit(1)

    if py_only:
        found = _find_doctype_json(name)
        if found is None:
            click.echo(f"Error: DocType '{name}' not found.", err=True)
            raise SystemExit(1)
        click.echo(f"✓ Controller regenerated: {_write_controller(found[0], name)}")
        return

    apps_dir = site_manager.bench_dir / "apps"
    app_path = apps_dir / app if app else _pick_app(apps_dir)
    if not app_path.is_dir():
        click.echo(f"Error: app '{app}' not found at {app_path}.", err=True)
        raise SystemExit(1)

    module_path = app_path / (module or app_path.name)
    if not module_path.is_dir():
        click.echo(f"Error: module package {module_path} not found.", err=True)
        raise SystemExit(1)

    doctype_dir = module_path / "doctypes" / name
    if doctype_dir.exists() and not force:
        click.echo(
            f"Error: folder {doctype_dir} already exists. Use --force to overwrite.",
            err=True,
        )
        raise SystemExit(1)

    doctype_dir.mkdir(parents=True, exist_ok=True)

    # 1. JSON metadata
    json_content = {
        "name": name,
        "label": name,
        "module": module_path.name,
        "doctype": "DocType",
        "fields": [{"fieldname": "name", "label": "Name", "fieldtype": "Data", "required": True}],
    }
    json_file = doctype_dir / f"{name}.json"
    json_file.write_text(json.dumps(json_content, ensure_ascii=False, indent=2) + "\n")

    # 2. Python controller via Jinja template
    _write_controller(json_file, name)

    # 3. JS client script via Jinja template
    js_file = doctype_dir / f"{name}.js"
    js_file.write_text(render_template("doctype/client_script.js.jinja", {"name": name}))

    # 4. __init__.py
    (doctype_dir / "__init__.py").write_text("")

    try:
        rel_path = doctype_dir.relative_to(Path.cwd())
    except ValueError:
        rel_path = doctype_dir

    click.echo(f"✓ Created DocType '{name}' in {rel_path}")
    click.echo(f"  ├── {name}.json")
    click.echo(f"  ├── {name}.py  (controller with auto-generated types)")
    click.echo(f"  ├── {name}.js  (client script)")
    click.echo("  └── __init__.py")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"1. Edit {name}.json to define the fields")
    click.echo(f"2. Run: grunt doctype sync-types {name} --app {app_path.name}")
    click.echo(f"3. Run: grunt doctype sync {name}")


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
