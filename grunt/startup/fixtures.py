"""Startup — fixture loading utilities for DocTypes and Workspaces."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.document.meta import Meta


_GRUNT_ROOT = Path(__file__).parent.parent  # grunt/startup/../ = grunt/


async def load_core_fixtures(session: AsyncSession, eng: AsyncEngine) -> None:
    """Load seed fixtures from grunt/*/fixtures/*.json (core module data).

    Scans all grunt/<module>/fixtures/ directories and applies records
    that don't yet exist in the database. Safe to call repeatedly.
    """
    import json

    for fixtures_dir in sorted(_GRUNT_ROOT.glob("*/fixtures")):
        for fx_file in sorted(fixtures_dir.glob("*.json")):
            try:
                fx = json.loads(fx_file.read_text(encoding="utf-8"))
                fx_doctype = fx.get("doctype", "")
                records = fx.get("records", [])
                if not fx_doctype or not records:
                    continue
                await _apply_doctype_fixture(
                    fx_doctype, records, session, eng, sync=bool(fx.get("sync"))
                )
                log.info("startup.core_fixture_applied", file=fx_file.name, doctype=fx_doctype)
            except Exception as e:
                log.warning("startup.core_fixture_failed", file=fx_file.name, error=str(e))


def _load_app_meta(app_dir: Path) -> dict | None:
    """Load app metadata from app.json and/or grunt_app.py with fallback merging.

    Priority: app.json values override grunt_app.py values.
    Guarantees presence of: name, title, version, modules, icon, color, description.
    """
    import json

    app_json = app_dir / "app.json"
    grunt_app = app_dir / "grunt_app.py"

    result: dict[str, Any] = {
        "name": app_dir.name,
        "title": app_dir.name,
        "version": "0.1.0",
        "description": "",
        "author": "",
        "modules": [],
        "icon": "📦",
        "color": "#2D6A4F",
    }

    if grunt_app.exists():
        ns: dict = {}
        try:
            exec(grunt_app.read_text(), ns)
            result.update(
                {
                    "name": ns.get("APP_NAME", result["name"]),
                    "title": ns.get("APP_TITLE", result["title"]),
                    "version": ns.get("APP_VERSION", result["version"]),
                    "description": ns.get("APP_DESCRIPTION", result["description"]),
                    "author": ns.get("APP_AUTHOR", result["author"]),
                    "modules": ns.get("MODULES", result["modules"]),
                    "icon": ns.get("APP_ICON", result["icon"]),
                    "color": ns.get("APP_COLOR", result["color"]),
                }
            )
        except Exception:
            log.exception("suppressed_error")

    if app_json.exists():
        try:
            app_data = json.loads(app_json.read_text())
            for key in (
                "name",
                "title",
                "version",
                "description",
                "author",
                "modules",
                "icon",
                "color",
            ):
                if key in app_data:
                    result[key] = app_data[key]
        except Exception:
            log.exception("suppressed_error")

    return result


def _coerce_fixture_value(fieldtype: str, value: object) -> object:
    """Coerce a JSON fixture value to the Python type expected by SQLAlchemy.

    JSON has no native date/time/datetime types — everything arrives as str.
    SQLite (and other backends) reject raw strings for Time/Date/Datetime columns.
    """
    if value is None:
        return None
    if fieldtype == "Time" and isinstance(value, str):
        from datetime import time as _time

        parts = value.split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            return _time(h, m, s)
        except ValueError, IndexError:
            return None
    if fieldtype == "Date" and isinstance(value, str):
        import re as _re
        from datetime import date as _date

        if _re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            try:
                y, mo, d = value.split("-")
                return _date(int(y), int(mo), int(d))
            except ValueError:
                return None
    if fieldtype == "Datetime" and isinstance(value, str):
        from datetime import datetime as _datetime

        try:
            dt = _datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            return None
    return value


async def _apply_doctype_fixture(
    doctype_name: str,
    records: list,
    session: AsyncSession,
    eng: AsyncEngine,
    *,
    sync: bool = False,
) -> None:
    """Apply fixture records for a regular DocType.

    Missing records are inserted. Existing ones are skipped — unless *sync*
    (a file written by ``grunt fixtures export``), then they are updated to
    match the file whenever the stored values differ.
    """
    from grunt.app import grunt

    dt = await grunt.get_meta(doctype_name)
    if dt is None:
        log.warning("startup.fixture_doctype_not_found", doctype=doctype_name)
        return

    physical_fields = dt.get_physical_fields()

    async with grunt.system_context(session, eng):
        for rec in records:
            name_val = rec.get("name") or rec.get(dt.title_field or "")
            if not name_val:
                continue

            existing_id = await grunt.exists(doctype_name, {"name": name_val})
            if existing_id:
                if sync:
                    await _sync_fixture_record(dt, doctype_name, existing_id, rec)
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

            try:
                await grunt.new_doc(doctype_name, payload)
            except Exception as _insert_exc:
                from sqlalchemy.exc import IntegrityError as _IntegrityError

                if isinstance(_insert_exc, _IntegrityError):
                    await session.rollback()
                    continue
                raise

    await session.flush()


async def _sync_fixture_record(dt: Meta, doctype_name: str, doc_id: str, rec: dict) -> None:
    """Update an existing record to the fixture's values — only if they differ.

    Compared in exported form (:func:`grunt.fixtures.clean_record`), so an
    unchanged record is never re-saved (no DocVersion/ActivityLog noise on
    every migrate). Fields absent from the fixture are left untouched.
    """
    from grunt.app import grunt
    from grunt.fixtures import clean_record, to_json_compatible

    current = await clean_record(dt, await grunt.get_doc(doctype_name, doc_id))
    desired = to_json_compatible(rec)
    changed = {k: v for k, v in desired.items() if k != "name" and current.get(k) != v}
    if not changed:
        return

    fieldtypes = {f.fieldname: f.fieldtype for f in dt.get_physical_fields()}
    payload = {
        k: _coerce_fixture_value(fieldtypes[k], v) if k in fieldtypes else v
        for k, v in changed.items()
    }
    await grunt.save_doc(doctype_name, doc_id, payload)
    log.info(
        "startup.fixture_synced", doctype=doctype_name, name=rec.get("name"), fields=sorted(changed)
    )
