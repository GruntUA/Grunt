"""Startup — fixture loading utilities for DocTypes and Workspaces."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


def _load_app_meta(app_dir: Path) -> dict | None:
    """Load app metadata from app.json and/or grunt_app.py with fallback merging.

    Priority: app.json values override grunt_app.py values.
    Guarantees presence of: name, title, version, modules, icon, color, description.
    """
    import json  # noqa: PLC0415

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
            exec(grunt_app.read_text(), ns)  # noqa: S102
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
        except Exception:  # noqa: BLE001
            logger.exception("suppressed_error")

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
        except Exception:  # noqa: BLE001
            logger.exception("suppressed_error")

    return result


def _coerce_fixture_value(fieldtype: str, value: object) -> object:
    """Coerce a JSON fixture value to the Python type expected by SQLAlchemy.

    JSON has no native date/time/datetime types — everything arrives as str.
    SQLite (and other backends) reject raw strings for Time/Date/Datetime columns.
    """
    if value is None:
        return None
    if fieldtype == "Time" and isinstance(value, str):
        from datetime import time as _time  # noqa: PLC0415

        parts = value.split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            return _time(h, m, s)
        except ValueError, IndexError:
            return None
    if fieldtype == "Date" and isinstance(value, str):
        import re as _re  # noqa: PLC0415
        from datetime import date as _date  # noqa: PLC0415

        if _re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            try:
                y, mo, d = value.split("-")
                return _date(int(y), int(mo), int(d))
            except ValueError:
                return None
    if fieldtype == "Datetime" and isinstance(value, str):
        from datetime import datetime as _datetime  # noqa: PLC0415

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
) -> None:
    """Insert fixture records for a regular DocType, skipping duplicates."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.metadata.registry import doctype_registry  # noqa: PLC0415

    try:
        dt = await doctype_registry.get(doctype_name)
    except Exception:  # noqa: BLE001
        logger.warning("startup.fixture_doctype_not_found", doctype=doctype_name)
        return

    async with grunt.system_context(session, eng):
        for rec in records:
            name_val = rec.get("name") or rec.get(dt.title_field or "")
            if not name_val:
                continue

            if await grunt.exists(doctype_name, {"name": name_val}):
                continue

            from grunt.metadata.field import NON_PHYSICAL_FIELDS  # noqa: PLC0415

            payload: dict[str, object] = dict(rec)
            payload["name"] = str(name_val)

            for field in dt.fields:
                if field.fieldtype in NON_PHYSICAL_FIELDS:
                    continue
                if field.fieldname in payload:
                    payload[field.fieldname] = _coerce_fixture_value(
                        field.fieldtype,
                        payload[field.fieldname],
                    )
                elif field.default is not None:
                    payload[field.fieldname] = _coerce_fixture_value(field.fieldtype, field.default)

            try:
                await grunt.new_doc(doctype_name, payload)
            except Exception as _insert_exc:  # noqa: BLE001
                from sqlalchemy.exc import IntegrityError as _IntegrityError  # noqa: PLC0415

                if isinstance(_insert_exc, _IntegrityError):
                    await session.rollback()
                    continue
                raise

    await session.flush()
