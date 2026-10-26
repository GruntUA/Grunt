import asyncio
import importlib
import json
from pathlib import Path

import click

from grunt.cli.utils import _site_session
lazy import grunt
lazy from grunt.apps.loader import _ensure_on_syspath, _hooks_import_path
lazy from grunt.fixtures import export_fixtures, parse_fixture_specs
lazy from grunt.site.manager import site_manager


@click.group("fixtures")
def fixtures_group():
    """Fixtures: export app fixtures; dump/load a DocType's records as JSON."""
    pass


@fixtures_group.command("export")
@click.argument("app")
@click.option("--site", default=None, help="Site name")
def fixtures_export(app: str, site: str | None):
    """Export the records declared in `fixtures` in the app's hooks.py to <module>/fixtures/.

    Files are written with `"sync": true`, so migrate updates existing records.
    """

    async def _run():

        app_dir = site_manager.bench_dir / "apps" / app
        if not app_dir.is_dir():
            click.echo(f"Error: app '{app}' not found ({app_dir}).", err=True)
            raise SystemExit(1)
        _ensure_on_syspath(app_dir)

        targets = []
        for hooks_file in sorted(app_dir.glob("*/hooks.py")):
            mod = importlib.import_module(_hooks_import_path(app, hooks_file.parent.name))
            entries = getattr(mod, "fixtures", None)
            if entries:
                targets.append((hooks_file.parent / "fixtures", parse_fixture_specs(entries)))

        if not targets:
            click.echo(f"The hooks.py of app '{app}' declares no `fixtures`; nothing to export.")
            return

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            for fixtures_dir, specs in targets:
                for path, count in await export_fixtures(specs, fixtures_dir):
                    click.echo(f"  {path.relative_to(app_dir)}: {count} records")

    asyncio.run(_run())


@fixtures_group.command("dump")
@click.argument("doctype")
@click.option("-o", "--output", default=None, help="Output file (default: <doctype>_fixtures.json)")
@click.option("--limit", default=1000, show_default=True, help="Maximum number of records")
@click.option("--filters", default=None, help='JSON filters, e.g. {"status": "Active"}')
@click.option("--site", default=None, help="Site name")
def fixtures_dump(
    doctype: str, output: str | None, limit: int, filters: str | None, site: str | None
):
    """Dump a DocType's records to a JSON file (read back with `fixtures load`).

    \b
    Examples:
      grunt fixtures dump Invoice
      grunt fixtures dump Invoice -o invoices.json --limit 100
      grunt fixtures dump Invoice --filters '{"status": "Draft"}'
    """
    try:
        parsed_filters = json.loads(filters) if filters else None
    except json.JSONDecodeError as e:
        raise click.ClickException(f"invalid JSON in --filters: {e}") from e
    out = Path(output or f"{doctype.lower()}_fixtures.json")

    async def _run():
        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            records = list(
                await grunt.get_list(
                    doctype, filters=parsed_filters, limit=limit, include_total=False
                )
            )
        payload = {"doctype": doctype, "records": records, "count": len(records)}
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        click.echo(f"Exported {len(records)} records to {out}")

    asyncio.run(_run())


# Server-managed fields: never written back from a dump
_SKIP_FIELDS = {"id", "docstatus", "creation", "modified", "modified_by"}


@fixtures_group.command("load")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice(["create", "upsert", "update"]),
    default="create",
    show_default=True,
    help="create: fail if the record exists; update: existing only; upsert: either",
)
@click.option("--skip-errors", is_flag=True, help="Keep going after a failed record")
@click.option("--site", default=None, help="Site name")
def fixtures_load(file: Path, mode: str, skip_errors: bool, site: str | None):
    """Load records from a JSON file written by `fixtures dump`.

    \b
    Examples:
      grunt fixtures load invoices.json
      grunt fixtures load invoices.json --mode upsert --skip-errors
    """
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"invalid JSON: {e}") from e
    doctype = data.get("doctype")
    records = data.get("records")
    if not doctype or not isinstance(records, list):
        raise click.ClickException("the file needs 'doctype' and 'records' keys")

    async def _save(rec: dict) -> None:
        rec_id = rec.get("id") or rec.get("name")
        clean = {k: v for k, v in rec.items() if k not in _SKIP_FIELDS}
        if mode == "create":
            await grunt.new_doc(doctype, clean)
        elif mode == "update":
            if not rec_id:
                raise ValueError("id/name required for update mode")
            await grunt.set_value(doctype, rec_id, clean)
        elif rec_id:  # upsert
            try:
                await grunt.set_value(doctype, rec_id, clean)
            except Exception:
                await grunt.new_doc(doctype, clean)
        else:
            await grunt.new_doc(doctype, clean)

    async def _run() -> int:
        loaded = errors = 0
        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            for i, rec in enumerate(records, 1):
                try:
                    await _save(rec)
                    loaded += 1
                except Exception as e:
                    errors += 1
                    click.echo(f"  ! record {i}: {e}", err=True)
                    if not skip_errors:
                        break
            await session.commit()
        click.echo(f"Loaded: {loaded}, errors: {errors}")
        return errors

    if asyncio.run(_run()) and not skip_errors:
        raise SystemExit(1)
