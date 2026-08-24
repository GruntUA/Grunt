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

from grunt.utils.strings import to_snake_case

logger = structlog.get_logger()

# ── Registries ────────────────────────────────────────────────────────────

# Server scripts: {("api", method): {...}} or {("doctype_event", doctype, event): {...}}
FILE_SCRIPT_REGISTRY: dict[tuple[str, ...], dict[str, Any]] = {}

# Client scripts: lazy cache — populated on first request per DocType
# {doctype: [{name, script}]}
FILE_CLIENT_SCRIPT_REGISTRY: dict[str, list[dict[str, str]]] = {}

# Registered (app_name, doctypes_dir) pairs for lazy client script scanning
_client_script_dirs: list[tuple[str, Path]] = []

# Doctypes already scanned (including misses) — avoids repeated disk reads
_client_script_scanned: set[str] = set()

_HEADER_RE = re.compile(r"^#\s*(\w[\w\s]+\w)\s*:\s*(.+)$", re.MULTILINE)


def _parse_script_meta(source: str) -> dict[str, str]:
    """Extract metadata from comment headers at the top of a script."""
    meta: dict[str, str] = {}
    for match in _HEADER_RE.finditer(source):
        key = match.group(1).strip().lower().replace(" ", "_")
        meta[key] = match.group(2).strip()
    return meta


def register_client_script_dir(app_name: str, doctypes_dir: str | Path) -> None:
    """Register a doctypes directory for lazy client script scanning.

    Call this instead of eagerly loading .js files at startup.
    Scripts are read from disk only when first requested per DocType.
    """
    _client_script_dirs.append((app_name, Path(doctypes_dir)))


def _iter_doctype_dirs(root_dir: Path) -> list[Path]:
    """Return all nested doctypes directories under a package/app root.

    The framework keeps DocType folders under both of these layouts:
    - apps/{app}/{module}/doctypes/{Name}/
    - apps/{app}/{package}/metadata/doctypes/{Name}/

    Using only ``*/doctypes`` misses the second form entirely, which is why
    client scripts for built-in doctypes such as ``DocType`` never loaded.
    """
    seen: set[Path] = set()
    results: list[Path] = []

    for match in sorted(root_dir.glob("**/doctypes")):
        if not match.is_dir():
            continue
        resolved = match.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        results.append(match)

    for match in sorted(root_dir.glob("doctypes")):
        if not match.is_dir():
            continue
        resolved = match.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        results.append(match)

    return results


def discover_file_scripts(apps_dir: str | Path, *, app_filter: str | None = None) -> None:
    """Scan all app module directories for server scripts.

    Register dirs for lazy client script loading.

    Server-side .py scripts are loaded eagerly (needed for hook system).
    Client-side .js scripts are registered for lazy loading per DocType.

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
        # and package-root layouts such as grunt/metadata/doctypes/{Name}/.
        for doctypes_dir in _iter_doctype_dirs(app_dir):
            if not doctypes_dir.is_dir():
                continue
            register_client_script_dir(app_dir.name, doctypes_dir)
            for dt_dir in sorted(doctypes_dir.iterdir()):
                if not dt_dir.is_dir() or dt_dir.name.startswith((".", "_")):
                    continue
                _load_doctype_dir_scripts(dt_dir, app_dir.name)


def _load_doctype_dir_scripts(dt_dir: Path, app_name: str) -> None:
    """Load server-side scripts colocated with a DocType definition.

    Expects a directory like ``doctypes/Applicant/`` containing:
    - ``Applicant.js``  → client script (registered for lazy loading, NOT read here)
    - ``Applicant.py``  → server-side controller/script (trusted)
    - Any other ``.py`` files → server scripts with metadata headers
    """
    doctype = dt_dir.name
    # Controller files are named either {snake_case}.py (preferred) or
    # {PascalCase}.py (legacy fallback) — see
    # DocumentRegistry.index_core_controllers, the actual controller loader
    # this must agree with. Comparing only against `doctype` (PascalCase)
    # missed every real controller (grunt/*/doctypes/*/*.py is snake_case in
    # practice), so controllers were being loaded a second time here as
    # bogus "API (auto)" server scripts.
    _controller_stems = {doctype, to_snake_case(doctype)}

    # Server scripts: any .py file in the directory (except __init__.py)
    for py_file in sorted(dt_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        # Skip the controller file — handled by document registry, not here.
        if py_file.stem in _controller_stems:
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
                logger.info(
                    "file_scripts.server_loaded",
                    app=app_name,
                    type="DocType Event",
                    doctype=doctype,
                    hook_event=event,
                )
        else:
            # Default: treat extra .py as API script using filename as method
            method = py_file.stem
            entry_dict["api_method"] = method
            entry_dict["allow_guest"] = False
            FILE_SCRIPT_REGISTRY[("api", method)] = entry_dict
            logger.info(
                "file_scripts.server_loaded", app=app_name, type="API (auto)", method=method
            )


# ── Lookup helpers (used by ServerScriptRunner) ──────────────────────────


def get_file_api_script(method: str) -> dict[str, Any] | None:
    """Get a file-based API script by method name."""
    return FILE_SCRIPT_REGISTRY.get(("api", method))


def get_file_doctype_scripts(doctype: str, event: str) -> list[dict[str, Any]]:
    """Get file-based DocType Event scripts."""
    entry = FILE_SCRIPT_REGISTRY.get(("doctype_event", doctype, event))
    return [entry] if entry else []


def get_file_client_scripts(doctype: str) -> list[dict[str, str]]:
    """Get file-based client scripts for a DocType (lazy — read from disk on first request)."""
    from grunt.config import settings

    if not settings.debug:
        if doctype in FILE_CLIENT_SCRIPT_REGISTRY:
            return FILE_CLIENT_SCRIPT_REGISTRY[doctype]

        if doctype in _client_script_scanned:
            return []

    _client_script_scanned.add(doctype)
    results: list[dict[str, str]] = []

    logger.debug("file_scripts.scan_start", doctype=doctype, dirs_count=len(_client_script_dirs))

    for app_name, doctypes_dir in _client_script_dirs:
        # Try exact match first (e.g. HromsStaffingTable/HromsStaffingTable.js)
        js_file = doctypes_dir / doctype / f"{doctype}.js"
        logger.debug(
            "file_scripts.try_path", app=app_name, path=str(js_file), exists=js_file.exists()
        )

        if not js_file.exists():
            # Try first-letter-capitalized (e.g. hromsStaffingTable → HromsStaffingTable)
            capitalized = doctype[0].upper() + doctype[1:] if doctype else doctype
            js_file = doctypes_dir / capitalized / f"{capitalized}.js"

        if not js_file.exists():
            # Try snake_case fallback (e.g. data_import/data_import.js)
            snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", doctype).lower()
            js_file = doctypes_dir / snake / f"{snake}.js"

        if not js_file.exists():
            # Try all-lowercase fallback (e.g. user/user.js)
            js_file = doctypes_dir / doctype.lower() / f"{doctype.lower()}.js"

        if not js_file.exists():
            # Last resort: case-insensitive directory scan
            try:
                for dir_entry in doctypes_dir.iterdir():
                    if dir_entry.is_dir() and dir_entry.name.lower() == doctype.lower():
                        candidate = dir_entry / f"{dir_entry.name}.js"
                        if candidate.exists():
                            js_file = candidate
                            break
            except OSError:
                pass

        if js_file.exists():
            source = js_file.read_text(encoding="utf-8")
            results.append({"name": f"{app_name}:{doctype}.js", "script": source})
            logger.debug(
                "file_scripts.client_loaded", app=app_name, doctype=doctype, file=str(js_file)
            )

    if not settings.debug:
        # Cache result (including empty — to avoid repeated disk reads)
        FILE_CLIENT_SCRIPT_REGISTRY[doctype] = results
    return results

