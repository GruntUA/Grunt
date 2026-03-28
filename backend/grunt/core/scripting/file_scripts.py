"""File-based script discovery for app developers.

Scripts are colocated with their DocType definition::

    myapp/
      mymodule/
        doctypes/
          Applicant/
            Applicant.json       # DocType definition
            Applicant.js         # Client script (auto-linked to DocType)
            Applicant.py         # Controller (Document subclass)
            validate_tax_id.py   # Extra server script (API/Event/Scheduler)

Server script metadata is parsed from comment headers::

    # Script Type: API
    # Method: validate_tax_id

    # Script Type: DocType Event
    # Event: before_save

File-based scripts are treated as **trusted** — they bypass sandbox
validation (no import blocking), since they are part of the app code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# ── Registries ────────────────────────────────────────────────────────────

# Server scripts: {("api", method): {...}} or {("doctype_event", doctype, event): {...}}
FILE_SCRIPT_REGISTRY: dict[tuple[str, ...], dict[str, Any]] = {}

# Client scripts: {doctype: [{name, script}]}
FILE_CLIENT_SCRIPT_REGISTRY: dict[str, list[dict[str, str]]] = {}

_HEADER_RE = re.compile(r"^#\s*(\w[\w\s]+\w)\s*:\s*(.+)$", re.MULTILINE)


def _parse_script_meta(source: str) -> dict[str, str]:
    """Extract metadata from comment headers at the top of a script."""
    meta: dict[str, str] = {}
    for match in _HEADER_RE.finditer(source):
        key = match.group(1).strip().lower().replace(" ", "_")
        meta[key] = match.group(2).strip()
    return meta


def discover_file_scripts(apps_dir: str | Path, *, app_filter: str | None = None) -> None:
    """Scan all app module directories for client and server scripts.

    Called once during startup in ``main.py``.
    If *app_filter* is given, only that app subdirectory is scanned.
    """
    apps_dir = Path(apps_dir)
    if not apps_dir.exists():
        return

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith((".", "_")):
            continue
        if app_filter and app_dir.name != app_filter:
            continue

        # DocType-colocated scripts: {module}/doctypes/{Name}/{Name}.js / .py
        for doctypes_dir in app_dir.glob("*/doctypes"):
            if not doctypes_dir.is_dir():
                continue
            for dt_dir in sorted(doctypes_dir.iterdir()):
                if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                    continue
                _load_doctype_dir_scripts(dt_dir, app_dir.name)


def _load_doctype_dir_scripts(dt_dir: Path, app_name: str) -> None:
    """Load scripts colocated with a DocType definition.

    Expects a directory like ``doctypes/Applicant/`` containing:
    - ``Applicant.js``  → client script for DocType "Applicant"
    - ``Applicant.py``  → server-side controller/script (trusted)
    - Any other ``.py`` files → server scripts with metadata headers
    """
    doctype = dt_dir.name

    # Client script: {DocType}.js
    js_file = dt_dir / f"{doctype}.js"
    if js_file.exists():
        source = js_file.read_text(encoding="utf-8")
        entry = {"name": f"{app_name}:{doctype}.js", "script": source}
        FILE_CLIENT_SCRIPT_REGISTRY.setdefault(doctype, []).append(entry)
        logger.info("file_scripts.client_loaded", app=app_name, doctype=doctype, file=str(js_file))

    # Server scripts: any .py file in the directory (except __init__.py)
    for py_file in sorted(dt_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        # Skip the controller file (same name as DocType) — handled by document registry
        if py_file.stem == doctype:
            continue
        source = py_file.read_text(encoding="utf-8")
        meta = _parse_script_meta(source)
        script_type = meta.get("script_type", "").lower()
        script_name = f"{app_name}:{py_file.name}"

        entry_dict: dict[str, Any] = {
            "name": script_name,
            "script": source,
            "trusted": True,
        }

        if script_type == "api":
            method = meta.get("method", py_file.stem)
            entry_dict["api_method"] = method
            entry_dict["allow_guest"] = meta.get("allow_guest", "").lower() == "true"
            FILE_SCRIPT_REGISTRY[("api", method)] = entry_dict
            logger.info("file_scripts.server_loaded", app=app_name, type="API", method=method)
        elif script_type in ("doctype_event", "doctype event"):
            event = meta.get("event")
            if event:
                FILE_SCRIPT_REGISTRY[("doctype_event", doctype, event)] = entry_dict
                logger.info("file_scripts.server_loaded", app=app_name, type="DocType Event", doctype=doctype, event=event)
        else:
            # Default: treat extra .py as API script using filename as method
            method = py_file.stem
            entry_dict["api_method"] = method
            entry_dict["allow_guest"] = False
            FILE_SCRIPT_REGISTRY[("api", method)] = entry_dict
            logger.info("file_scripts.server_loaded", app=app_name, type="API (auto)", method=method)


# ── Lookup helpers (used by ServerScriptRunner) ──────────────────────────


def get_file_api_script(method: str) -> dict[str, Any] | None:
    """Get a file-based API script by method name."""
    return FILE_SCRIPT_REGISTRY.get(("api", method))


def get_file_doctype_scripts(doctype: str, event: str) -> list[dict[str, Any]]:
    """Get file-based DocType Event scripts."""
    entry = FILE_SCRIPT_REGISTRY.get(("doctype_event", doctype, event))
    return [entry] if entry else []


def get_file_client_scripts(doctype: str) -> list[dict[str, str]]:
    """Get file-based client scripts for a DocType."""
    return FILE_CLIENT_SCRIPT_REGISTRY.get(doctype, [])
