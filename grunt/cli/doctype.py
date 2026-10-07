import asyncio
from pathlib import Path

import click

from grunt.cli.utils import _site_session
from grunt.utils.strings import to_snake_case


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
        import json

        from grunt.metadata.doctype import DocType
        from grunt.metadata.registry import doctype_registry
        from grunt.startup.doctypes import _find_doctype_dirs

        # Find JSON file across all grunt/*/doctypes/ and app doctypes/, tracking
        # which app owns each search dir so we can both stamp DocType.app (core
        # doctype JSON never sets it - only the startup path did, until now) and
        # refuse to silently push one app's definition over another's.
        json_file = None
        owning_app = "grunt"
        from grunt.site.manager import site_manager

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

        dt_data = json.loads(json_file.read_text(encoding="utf-8"))
        dt = DocType.model_validate(dt_data)
        if not dt.app:
            dt.app = owning_app

        async with _site_session(site) as (session, eng):
            from grunt.metadata import store

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
        from grunt.metadata.registry import doctype_registry

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
    import json

    from grunt.utils.codegen import build_controller_context, render_template

    if not name or name[0].islower():
        click.echo("Error: the DocType name must start with an uppercase letter.", err=True)
        raise SystemExit(1)

    from grunt.site.manager import site_manager

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
    json_file.write_text(
        json.dumps(json_content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 2. Python controller via Jinja template
    py_ctx = build_controller_context(name, initial_fields)
    py_file = doctype_dir / f"{to_snake_case(name)}.py"
    py_file.write_text(render_template("doctype/controller.py.jinja", py_ctx), encoding="utf-8")

    # 3. JS client script via Jinja template
    js_file = doctype_dir / f"{to_snake_case(name)}.js"
    js_file.write_text(
        render_template("doctype/client_script.js.jinja", {"name": name}), encoding="utf-8"
    )

    # 4. __init__.py
    (doctype_dir / "__init__.py").write_text("", encoding="utf-8")

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


@doctype_group.command("sync-types")
@click.argument("name")
@click.option("--app", default="web", help="App folder containing the DocType")
@click.option("--all", "all_doctypes", is_flag=True, help="Update all DocTypes in the app")
def doctype_sync_types(name: str, app: str, all_doctypes: bool):
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
    import json

    from grunt.site.manager import site_manager
    from grunt.utils.codegen import sync_controller_types

    app_path = site_manager.bench_dir / "apps" / app

    if all_doctypes:
        updated = 0
        skipped = 0
        for json_file in sorted(app_path.glob("doctypes/*/*.json")):
            dt_name = json_file.stem
            py_file = json_file.parent / f"{dt_name}.py"
            if not py_file.exists():
                continue
            try:
                fields = json.loads(json_file.read_text(encoding="utf-8")).get("fields", [])
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

    json_file = app_path / "doctypes" / name / f"{name}.json"
    py_file = app_path / "doctypes" / name / f"{name}.py"

    if not json_file.exists():
        click.echo(f"Error: {json_file} not found.", err=True)
        raise SystemExit(1)
    if not py_file.exists():
        click.echo(f"Error: {py_file} not found.", err=True)
        raise SystemExit(1)

    fields = json.loads(json_file.read_text(encoding="utf-8")).get("fields", [])
    changed = sync_controller_types(py_file, name, fields)
    if changed:
        click.echo(f"✓ Types updated: {py_file}")
    else:
        click.echo(f"Unchanged: {py_file}")
