import json
from pathlib import Path

import click

lazy from grunt.metadata.field import get_manifest_attrs, get_registered_fieldtypes

# Discovery helpers


def _is_bench_root(path: Path) -> bool:
    """True if path looks like a bench root (has apps/grunt/frontend)."""
    return (path / "apps" / "grunt" / "frontend").is_dir()


def _find_bench_root(start: Path) -> Path | None:
    """Walk up from start to find a bench root."""
    for directory in [start.resolve(), *start.resolve().parents]:
        if _is_bench_root(directory):
            return directory
    return None


# Commands


@click.group(name="fields")
def fields_group() -> None:
    """Field-type registry utilities."""


@fields_group.command(name="sync-manifests")
@click.option(
    "--check",
    is_flag=True,
    help="Exit non-zero if a manifest is out of sync instead of fixing it.",
)
def sync_manifests(check: bool) -> None:
    """Sync each field type's storage_class and traits in its frontend manifest.json.

    storage_class mirrors FieldType.column_spec and traits mirror FieldType.traits
    (grunt/metadata/field.py), so the frontend knows them without a backend round-trip.
    Run this after adding a field type or changing its column_spec / traits, so
    manifest.json never has to be hand-edited to match.
    """

    bench_root = _find_bench_root(Path.cwd())
    if bench_root is None:
        raise click.ClickException("Could not find bench root (no apps/grunt/frontend found).")

    fields_dir = bench_root / "apps" / "grunt" / "frontend" / "src" / "components" / "fields"

    changed: list[str] = []
    skipped: list[str] = []

    for fieldtype in get_registered_fieldtypes():
        manifest_path = fields_dir / fieldtype / "manifest.json"
        if not manifest_path.exists():
            skipped.append(fieldtype)
            continue

        data = json.loads(manifest_path.read_text())
        # traits is dropped when the type has none, so start from data without it.
        synced = {k: v for k, v in data.items() if k != "traits"} | get_manifest_attrs(fieldtype)
        if synced == data:
            continue

        changed.append(fieldtype)
        if not check:
            data = synced
            manifest_path.write_text(json.dumps(data, ensure_ascii=False))

    if changed:
        verb = "out of sync" if check else "updated"
        click.echo(f"{verb}: {', '.join(changed)}")
    else:
        click.echo("all manifests already in sync")
    if skipped:
        click.echo(f"no manifest.json (skipped): {', '.join(skipped)}")

    if check and changed:
        raise SystemExit(1)
