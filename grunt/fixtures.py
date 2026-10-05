"""Fixtures - export configuration records from a site's database into an
app's ``<module>/fixtures/*.json`` files, so they travel with the app's code.

An app declares what to export in its ``hooks.py``::

    fixtures = [
        "Role",                                            # every record
        {"doctype": "Role", "filters": {"name__in": ["Діловод"]}, "file": "00_roles.json"},
        {"doctype": "Page", "filters": {"name": "letter-home"}},
    ]

``grunt fixtures export <app>`` writes one file per entry in the format the
fixture loader already reads (``{"doctype", "records"}``) plus ``"sync": true``.
On install/migrate a *sync* file updates existing records to match it, while a
hand-written seed file (no ``sync``) only inserts records that are missing -
see :func:`grunt.startup.fixtures._apply_doctype_fixture`.

Only schema fields are exported: system columns (``id``, ``owner``,
timestamps, …), virtual/layout fields and ``Password`` values never leave the
site. Child rows keep their data fields only - the parent re-creates them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import grunt
from grunt.utils.strings import to_snake_case

if TYPE_CHECKING:
    from pathlib import Path

    from grunt.document.meta import Meta


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    doctype: str
    filters: dict[str, Any] = field(default_factory=dict)
    file: str = ""

    @property
    def filename(self) -> str:
        return self.file or f"{to_snake_case(self.doctype)}.json"


def parse_fixture_specs(entries: list[str | dict[str, Any]]) -> list[FixtureSpec]:
    """Normalise a ``hooks.py`` ``fixtures`` list into :class:`FixtureSpec` objects."""
    specs: list[FixtureSpec] = []
    for entry in entries:
        if isinstance(entry, str):
            specs.append(FixtureSpec(doctype=entry))
        elif isinstance(entry, dict) and entry.get("doctype"):
            specs.append(
                FixtureSpec(
                    doctype=entry["doctype"],
                    filters=dict(entry.get("filters") or {}),
                    file=entry.get("file", ""),
                )
            )
        else:
            raise ValueError(f"Invalid fixtures entry: {entry!r}")
    return specs


async def clean_record(meta: Meta, data: dict[str, Any], *, child: bool = False) -> dict[str, Any]:
    """Reduce a loaded document to its portable fixture form (schema order).

    Keeps ``name`` for top-level records (it is the identity the loader
    matches on), every physical non-``Password`` field, MultiLink lists and
    child tables (recursively cleaned). ``None`` values are dropped.
    """
    out: dict[str, Any] = {}
    if not child and data.get("name") is not None:
        out["name"] = data["name"]

    table_fieldnames = meta.get_table_fieldnames()
    multilink_fieldnames = {f.fieldname for f in meta.get_multilink_fields()}

    for f in meta.doc.fields:
        value = data.get(f.fieldname)
        if value is None or f.fieldname == "name":
            continue
        if f.fieldname in table_fieldnames:
            child_meta = await grunt.get_meta(f.options or "")
            if child_meta is None or not value:
                continue
            out[f.fieldname] = [await clean_record(child_meta, row, child=True) for row in value]
        elif f.fieldname in multilink_fieldnames:
            if value:
                out[f.fieldname] = list(value)
        elif f.is_physical and f.fieldtype != "Password":
            out[f.fieldname] = value

    return to_json_compatible(out)


def to_json_compatible(value: Any) -> Any:
    """Round-trip through JSON so dates/decimals compare equal to a fixture file."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=_json_default))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


async def export_records(spec: FixtureSpec) -> list[dict[str, Any]]:
    """Load every record matching *spec* (with child tables) in fixture form.

    Must run inside a grunt context (e.g. ``grunt.system_context``).
    """
    meta = await grunt.get_meta(spec.doctype)
    if meta is None:
        raise ValueError(f"DocType “{spec.doctype}” not found")

    names = await grunt.db.get_all(
        spec.doctype,
        filters=spec.filters or None,
        pluck="name",
        limit=None,
        order_by="name",
        order="asc",
    )
    return [await clean_record(meta, await grunt.get_doc(spec.doctype, name)) for name in names]


async def export_fixtures(specs: list[FixtureSpec], fixtures_dir: Path) -> list[tuple[Path, int]]:
    """Write one sync-fixture file per spec into *fixtures_dir*.

    Returns ``(path, record_count)`` for each written file.
    """
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, int]] = []
    for spec in specs:
        records = await export_records(spec)
        path = fixtures_dir / spec.filename
        payload = {"doctype": spec.doctype, "sync": True, "records": records}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append((path, len(records)))
    return written
