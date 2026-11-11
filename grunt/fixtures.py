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
see :func:`apply_doctype_fixture`.

Only schema fields are exported: system columns (``id``, ``owner``,
timestamps, …), virtual/layout fields and ``Password`` values never leave the
site. Child rows keep their ``doctype`` and data fields only - the parent
re-creates them.
"""

import json
import re as _re
from dataclasses import dataclass, field
from datetime import UTC
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.db.api import GruntDB
from grunt.document.serde import to_json, with_doctype
from grunt.local import system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.utils.strings import to_snake_case
lazy from grunt.document.api import documents
lazy from grunt.document.meta import Meta

_db = GruntDB()  # stateless: reads through the context's session


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
            child_meta = await doctype_registry.get_meta(f.options or "")
            if child_meta is None or not value:
                continue
            out[f.fieldname] = [
                with_doctype(child_meta.doc.name, await clean_record(child_meta, row, child=True))
                for row in value
            ]
        elif f.fieldname in multilink_fieldnames:
            if value:
                out[f.fieldname] = list(value)
        elif f.is_physical and not f.has_trait("sensitive"):
            out[f.fieldname] = value

    return to_json_compatible(out)


def to_json_compatible(value: Any) -> Any:
    """Round-trip through JSON so dates/decimals compare equal to a fixture file."""
    return json.loads(to_json(value))


async def export_records(spec: FixtureSpec) -> list[dict[str, Any]]:
    """Load every record matching *spec* (with child tables) in fixture form.

    Must run inside a grunt context (e.g. ``grunt.system_context``).
    """
    meta = await doctype_registry.get_meta(spec.doctype)
    if meta is None:
        raise ValueError(f"DocType “{spec.doctype}” not found")

    names = await _db.get_all(
        spec.doctype,
        filters=spec.filters or None,
        pluck="name",
        limit=None,
        order_by="name",
        order="asc",
    )
    return [await clean_record(meta, await documents.get_doc(spec.doctype, name)) for name in names]


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
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        written.append((path, len(records)))
    return written


# Loading records back (install / migrate)


def _coerce_fixture_value(fieldtype: str, value: object) -> object:
    """Coerce a JSON fixture value to the Python type expected by SQLAlchemy.

    JSON has no native date/time/datetime types - everything arrives as str.
    SQLite (and other backends) reject raw strings for Time/Date/Datetime columns.
    """
    if value is None:
        return None
    if fieldtype == "Time" and isinstance(value, str):
        parts = value.split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            return _time(h, m, s)
        except ValueError, IndexError:
            return None
    if fieldtype == "Date" and isinstance(value, str) and _re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        try:
            y, mo, d = value.split("-")
            return _date(int(y), int(mo), int(d))
        except ValueError:
            return None
    if fieldtype == "Datetime" and isinstance(value, str):
        try:
            dt = _datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            return None
    return value


async def apply_doctype_fixture(
    doctype_name: str,
    records: list,
    session: AsyncSession,
    eng: AsyncEngine,
    *,
    sync: bool = False,
) -> int:
    """Apply fixture records for a regular DocType.

    Missing records are inserted. Existing ones are skipped - unless *sync*
    (a file written by ``grunt fixtures export``), then they are updated to
    match the file whenever the stored values differ.

    Returns how many records were inserted or updated.
    """
    dt = await doctype_registry.get_meta(doctype_name)
    if dt is None:
        log.warning("startup.fixture_doctype_not_found", doctype=doctype_name)
        return 0

    written = 0

    physical_fields = dt.get_physical_fields()

    async with system_context(session, eng):
        for rec in records:
            name_val = rec.get("name") or rec.get(dt.title_field or "")
            if not name_val:
                continue

            existing_id = await documents.exists(doctype_name, {"name": name_val})
            if existing_id:
                if sync and await _sync_fixture_record(dt, doctype_name, existing_id, rec):
                    written += 1
                continue

            payload: dict[str, object] = dict(rec)
            payload["name"] = str(name_val)

            for field in physical_fields:
                if field.fieldname in payload:
                    payload[field.fieldname] = _coerce_fixture_value(
                        field.fieldtype,
                        payload[field.fieldname],
                    )
                elif field.default is not None:
                    payload[field.fieldname] = _coerce_fixture_value(field.fieldtype, field.default)

            # A savepoint per record: an IntegrityError rolls back this insert
            # only, not everything the caller did earlier in the session.
            try:
                async with session.begin_nested():
                    await documents.new_doc(doctype_name, payload)
                written += 1
            except IntegrityError:
                log.warning("startup.fixture_record_conflict", doctype=doctype_name, name=name_val)

    await session.flush()
    return written


def _without_doctype(value: Any) -> Any:
    """*value* without the ``"doctype"`` keys a document's JSON names itself with -
    a fixture written before child rows carried them still compares equal."""
    if isinstance(value, dict):
        return {k: _without_doctype(v) for k, v in value.items() if k != "doctype"}
    if isinstance(value, list):
        return [_without_doctype(v) for v in value]
    return value


def _matches(current: Any, desired: Any) -> bool:
    """Whether the stored *current* value already is the fixture's *desired* one.

    Child rows compare on the keys the fixture gives: a saved row also holds
    the empty values its other fields were filled with.
    """
    if isinstance(desired, dict) and isinstance(current, dict):
        return all(_matches(current.get(k), v) for k, v in desired.items())
    if isinstance(desired, list) and isinstance(current, list):
        return len(current) == len(desired) and all(map(_matches, current, desired, strict=True))
    return current == desired


async def _sync_fixture_record(dt: Meta, doctype_name: str, doc_id: str, rec: dict) -> bool:
    """Update an existing record to the fixture's values - only if they differ.

    Compared in exported form (:func:`clean_record`), so an
    unchanged record is never re-saved (no DocVersion/ActivityLog noise on
    every migrate). Fields absent from the fixture - in child rows too - are
    left untouched.
    """
    current = _without_doctype(
        await clean_record(dt, await documents.get_doc(doctype_name, doc_id))
    )
    desired = _without_doctype(to_json_compatible(rec))
    changed = {k: v for k, v in desired.items() if k != "name" and not _matches(current.get(k), v)}
    if not changed:
        return False

    fieldtypes = {f.fieldname: f.fieldtype for f in dt.get_physical_fields()}
    payload = {
        k: _coerce_fixture_value(fieldtypes[k], v) if k in fieldtypes else v
        for k, v in changed.items()
    }
    await documents.save_doc(doctype_name, doc_id, payload)
    log.info(
        "startup.fixture_synced", doctype=doctype_name, name=rec.get("name"), fields=sorted(changed)
    )
    return True
