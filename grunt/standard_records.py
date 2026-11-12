"""Standard records - documents that ship with an app as JSON files.

A DocType with ``standard_records`` has ``is_standard`` + ``app`` fields. In
developer mode (``settings.debug``) saving a standard record writes it into
its app::

    <app>/<module>/records/<doctype_snake>/<record>/<record>.json
    <app>/<module>/records/<doctype_snake>/<record>/<code field>.<ext>

The JSON is the document's JSON (``"doctype"`` key, child rows included)
without system columns; each non-empty Code field goes to a file of its own
so templates and scripts diff and edit like code. Deleting the record, or
unmarking it, removes its folder.

``grunt migrate`` reads the folders back (:func:`apply_records`): a missing
record is inserted, an existing one updated to match - the files are the
source of truth - and an unchanged one is not touched.
"""

import hashlib
import json
import shutil
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.config import settings
from grunt.db.api import GruntDB
from grunt.document.serde import to_json, with_doctype
from grunt.fixtures import apply_doctype_fixture, clean_record
from grunt.local import require_engine, require_session, system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import site_manager
from grunt.utils.slug import slugify
from grunt.utils.strings import to_snake_case
lazy from grunt.apps.manifest import read_manifest
lazy from grunt.document.api import documents
lazy from grunt.document.meta import Meta

_GRUNT_ROOT = Path(__file__).parent  # the grunt package dir

_db = GruntDB()  # stateless: reads through the context's session

RECORDS_DIR = "records"

# Code field ``options`` (its language) -> file extension.
_CODE_EXTENSIONS = {
    "html": "html",
    "jinja": "html",
    "css": "css",
    "js": "js",
    "javascript": "js",
    "py": "py",
    "python": "py",
    "sql": "sql",
    "json": "json",
    "markdown": "md",
    "md": "md",
}


def _code_extension(options: str | None) -> str:
    return _CODE_EXTENSIONS.get((options or "").strip().lower(), "txt")


def _app_root(app: str) -> Path | None:
    """The package directory of *app* that holds its ``records/`` folder."""

    if app == "grunt":
        return _GRUNT_ROOT
    app_dir = site_manager.bench_dir / "apps" / app
    if not app_dir.is_dir():
        return None
    for module in [*read_manifest(app_dir)["modules"], app]:
        if (app_dir / module).is_dir():
            return app_dir / module
    return None


def _records_dirs(app: str) -> list[Path]:
    """Every ``records/`` folder of *app* (core: one per module)."""

    if app == "grunt":
        return sorted(_GRUNT_ROOT.glob(f"*/{RECORDS_DIR}"))
    app_dir = site_manager.bench_dir / "apps" / app
    modules = read_manifest(app_dir)["modules"]
    return [app_dir / m / RECORDS_DIR for m in modules if (app_dir / m / RECORDS_DIR).is_dir()]


def _doctype_dir(app: str, meta: Meta) -> Path | None:
    root = _GRUNT_ROOT / meta.doc.module if app == "grunt" else _app_root(app)
    if root is None or not root.is_dir():
        return None
    return root / RECORDS_DIR / to_snake_case(meta.doc.name.replace(" ", ""))


def _record_name(folder: Path) -> str | None:
    try:
        data = json.loads((folder / f"{folder.name}.json").read_text())
    except OSError, ValueError:
        return None
    return data.get("name") if isinstance(data, dict) else None


def _folder_for(doctype_dir: Path, meta: Meta, doc: dict[str, Any]) -> Path:
    """The record's folder: its title (or name) as a slug, unique within the DocType."""
    name = str(doc["name"])
    title_field = meta.get_title_field()
    label = str(doc.get(title_field) or name)
    folder = doctype_dir / slugify(label).replace("-", "_")
    if folder.exists() and _record_name(folder) not in (None, name):
        folder = doctype_dir / f"{folder.name}_{hashlib.sha1(name.encode()).hexdigest()[:6]}"
    return folder


def _folders_of(doctype: str, name: str) -> list[Path]:
    """Folders of the record *name* in any installed app."""
    folders: list[Path] = []
    subdir = to_snake_case(doctype.replace(" ", ""))
    for app in sorted(site_manager.get_all_installed_apps() | {"grunt"}):
        for records_dir in _records_dirs(app):
            doctype_dir = records_dir / subdir
            if not doctype_dir.is_dir():
                continue
            folders += [f for f in doctype_dir.iterdir() if f.is_dir() and _record_name(f) == name]
    return folders


def _write(path: Path, text: str) -> None:
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


async def export_record(meta: Meta, doc: dict[str, Any]) -> Path | None:
    """Write the standard record *doc* to its app; returns its folder."""
    app = doc.get("app")
    doctype_dir = _doctype_dir(str(app), meta) if app else None
    if doctype_dir is None:
        log.warning("standard_records.no_app_dir", doctype=meta.doc.name, app=app)
        return None

    record = with_doctype(meta.doc.name, await clean_record(meta, doc))
    folder = _folder_for(doctype_dir, meta, doc)
    folder.mkdir(parents=True, exist_ok=True)

    files = {f"{folder.name}.json"}
    for field in meta.doc.fields:
        if field.fieldtype != "Code" or not record.get(field.fieldname):
            continue
        filename = f"{field.fieldname}.{_code_extension(field.options)}"
        _write(folder / filename, str(record.pop(field.fieldname)))
        files.add(filename)
    _write(folder / f"{folder.name}.json", to_json(record, indent=2) + "\n")

    for stale in folder.iterdir():
        if stale.is_file() and stale.name not in files:
            stale.unlink()
    return folder


def remove_record(doctype: str, name: str, *, keep: Path | None = None) -> None:
    for folder in _folders_of(doctype, name):
        if folder != keep:
            shutil.rmtree(folder)
            log.info("standard_records.removed", doctype=doctype, name=name, path=str(folder))


async def sync_files(event: str, **kwargs: Any) -> None:
    """``after_save`` / ``after_delete`` / ``after_rename`` hook: mirror the
    standard records of a ``standard_records`` DocType into their apps."""
    doctype = kwargs.get("doctype")
    # Applying the files themselves (migrate, a test) - nothing to write back.
    if not settings.debug or not doctype or _applying.get():
        return
    meta = await doctype_registry.get_meta(doctype)
    if meta is None or not meta.doc.standard_records:
        return

    if event == "after_delete":
        doc = kwargs.get("doc") or {}
        if doc.get("name"):
            remove_record(doctype, str(doc["name"]))
        return
    if event == "after_rename":
        remove_record(doctype, str(kwargs.get("old_id")))
        name = kwargs.get("new_id")
    else:
        name = (kwargs.get("doc") or {}).get("name")
    if not name:
        return

    async with system_context(require_session()):
        doc = await documents.get_doc(doctype, str(name))
    if doc.get("is_standard") and not doc.get("app"):
        # Nowhere to write it - but that's no reason to delete the files it has
        # (a test saving a shipped record with app=None used to wipe them).
        log.warning("standard_records.no_app", doctype=doctype, name=name)
        return
    folder = await export_record(meta, doc) if doc.get("is_standard") else None
    remove_record(doctype, str(name), keep=folder)
    if folder is not None:
        log.info("standard_records.exported", doctype=doctype, name=name, path=str(folder))


def read_record(folder: Path) -> dict[str, Any] | None:
    """The document JSON in *folder*, with its Code fields read back in."""
    try:
        record = json.loads((folder / f"{folder.name}.json").read_text())
    except OSError, ValueError:
        return None
    if not isinstance(record, dict) or not record.get("doctype") or not record.get("name"):
        return None
    for path in folder.iterdir():
        stem = path.name.split(".", 1)[0]
        if path.is_file() and path.name != f"{folder.name}.json" and stem not in record:
            record[stem] = path.read_text()
    return record


async def apply_records(
    app: str, session: AsyncSession, eng: AsyncEngine, *, doctype: str | None = None
) -> int:
    """Insert or update every standard record shipped in *app*'s files (only
    *doctype*'s, when given).

    Returns how many records were inserted or updated.
    """
    pattern = f"{to_snake_case(doctype)}/*/*.json" if doctype else "*/*/*.json"
    folders = [
        json_file.parent
        for records_dir in _records_dirs(app)
        for json_file in sorted(records_dir.glob(pattern))
        if json_file.stem == json_file.parent.name
    ]
    count = 0
    async with system_context(session, eng):
        for folder in folders:
            count += await _apply_folder(app, folder, session, eng)
    return count


async def _apply_folder(
    app: str,
    folder: Path,
    session: AsyncSession,
    eng: AsyncEngine,
    *,
    raise_errors: bool = False,
) -> int:

    record = read_record(folder)
    if record is None:
        if raise_errors:
            raise ValueError(f"unreadable standard record: {folder}")
        log.warning("standard_records.unreadable", path=str(folder))
        return 0
    meta = await doctype_registry.get_meta(record["doctype"])
    if meta is None or not meta.doc.standard_records:
        log.warning("standard_records.not_standard", path=str(folder))
        return 0
    record = {k: v for k, v in record.items() if k == "name" or meta.has_field(k)}
    record.update(is_standard=True, app=app)
    if meta.has_field("is_customized"):
        if await _db.get_value(meta.doc.name, str(record["name"]), "is_customized"):
            # Edited on this site - keep it (``reset`` follows the app again).
            log.info("standard_records.customized_kept", doctype=meta.doc.name, name=record["name"])
            return 0
        record["is_customized"] = False
    token = _applying.set(True)
    try:
        return await apply_doctype_fixture(meta.doc.name, [record], session, eng, sync=True)
    except Exception as e:
        if raise_errors:
            raise
        log.warning("standard_records.apply_failed", path=str(folder), error=str(e))
        return 0
    finally:
        _applying.reset(token)


# Set while the files are applied: a save then is the app's, not a local edit.
_applying: ContextVar[bool] = ContextVar("standard_records_applying", default=False)


def mark_customized(doc: Any) -> None:
    """For a controller's ``validate``: a standard record saved on a site
    (not in developer mode, not by :func:`apply_records`) is a local edit -
    ``grunt migrate`` stops overwriting it. The DocType opts in with an
    ``is_customized`` Check field."""
    if doc.get("is_standard") and not settings.debug and not _applying.get():
        doc.is_customized = True


async def reset(doctype: str, name: str) -> bool:
    """Bring a customized standard record back to its app's files; False when
    no file ships it. A failed apply leaves it customized and raises - the
    next ``grunt migrate`` must not take the local edits for the app's."""
    folders = _folders_of(doctype, name)
    if not folders:
        return False
    session = require_session()
    app = await _db.get_value(doctype, name, "app") or "grunt"
    await _db.set_value(doctype, name, "is_customized", False)
    try:
        await _apply_folder(str(app), folders[0], session, require_engine(), raise_errors=True)
    except Exception:
        await _db.set_value(doctype, name, "is_customized", True)
        raise
    return True
