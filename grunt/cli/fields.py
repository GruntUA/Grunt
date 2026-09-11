from __future__ import annotations

import json
from pathlib import Path

import click

# ── Discovery helpers ─────────────────────────────────────────────────────────


def _is_bench_root(path: Path) -> bool:
    """True if path looks like a bench root (has apps/grunt/frontend)."""
    return (path / "apps" / "grunt" / "frontend").is_dir()


def _find_bench_root(start: Path) -> Path | None:
    """Walk up from start to find a bench root."""
    for directory in [start.resolve(), *start.resolve().parents]:
        if _is_bench_root(directory):
            return directory
    return None


# ── Commands ──────────────────────────────────────────────────────────────────


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
    """Sync each field type's storage_class in its frontend manifest.json.

    storage_class mirrors FieldType.column_spec (grunt/metadata/field.py) so the
    DocType «Конструктор» can warn about DB retypes without a backend round-trip.
    Run this after adding a field type or changing its column_spec, so manifest.json
    never has to be hand-edited to match.
    """
    from grunt.metadata.field import get_registered_fieldtypes, get_storage_class

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

        storage_class = get_storage_class(fieldtype)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if data.get("storage_class") == storage_class:
            continue

        changed.append(fieldtype)
        if not check:
            data["storage_class"] = storage_class
            manifest_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    if changed:
        verb = "out of sync" if check else "updated"
        click.echo(f"{verb}: {', '.join(changed)}")
    else:
        click.echo("all manifests already in sync")
    if skipped:
        click.echo(f"no manifest.json (skipped): {', '.join(skipped)}")

    if check and changed:
        raise SystemExit(1)
