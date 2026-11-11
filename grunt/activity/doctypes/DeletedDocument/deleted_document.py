"""``DeletedDocument`` - restorable JSON snapshots of deleted documents.

Snapshots are written by the ``after_delete`` hook in :mod:`grunt.activity.trash`.
This module holds the controller plus the whitelisted :func:`restore` /
:func:`bulk_restore` RPCs the trash-bin UI calls.
"""

import json
from datetime import UTC, datetime
from typing import Any

from grunt.api.context import whitelist
from grunt.auth.current import acting_user
from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

# Ключі знімка, які не можна передавати в insert відновлюваного документа:
# per-user "seen" стан і аудит-поля (ядро проставляє власні).
_STRIP_ON_RESTORE = frozenset({"_seen", "owner", "created_at", "modified_at", "modified_by"})


class DeletedDocument(Document):
    deleted_doctype: str
    deleted_name: str
    title: str
    deleted_by: str
    restored: bool
    data: dict


# RPC


def _require_system_manager() -> None:
    if not acting_user().has_role("System Manager"):
        throw(_("Only a System Manager can restore documents"), code="FORBIDDEN")


def _snapshot_payload(snap: DeletedDocument) -> dict[str, Any]:
    # The field is called ``data`` too - ``snap.data`` is the whole record.
    raw = snap.get("data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            throw(_("The snapshot is corrupted: invalid JSON"), code="INVALID_SNAPSHOT")
    if not isinstance(raw, dict):
        throw(_("The snapshot is empty"), code="INVALID_SNAPSHOT")
    return {k: v for k, v in raw.items() if k not in _STRIP_ON_RESTORE}


@whitelist()
async def restore(name: str, allow_rename: bool = False) -> dict[str, Any]:
    """Відновити один видалений документ зі знімка ``name``.

    Повертає відновлений документ. Якщо оригінальний ID зайнятий - кине
    помилку, доки не передано ``allow_rename=True`` (тоді буде згенеровано
    новий ID за правилом autoname цільового DocType).

    Обмеження: зв'язки з/на інші документи, почищені каскадно при видаленні,
    назад не відновлюються; ``owner`` та час створення стають поточними.
    """
    _require_system_manager()

    snap = await documents.get_doc(DeletedDocument, name)
    if snap.restored:
        throw(
            _("Already restored as “%(name)s”") % {"name": snap.restored_to or "?"},
            code="ALREADY_RESTORED",
        )

    target_dt = snap.deleted_doctype
    try:
        await doctype_registry.get(target_dt)
    except Exception:
        throw(
            _("DocType “%(doctype)s” no longer exists") % {"doctype": target_dt},
            code="DOCTYPE_GONE",
        )

    payload = _snapshot_payload(snap)
    orig_name = str(snap.deleted_name)

    if await _db.exists(target_dt, orig_name):
        if not allow_rename:
            throw(
                _("Document “%(name)s” already exists. Restore with a new ID?")
                % {"name": orig_name},
                code="NAME_TAKEN",
            )
        payload.pop("name", None)

    async with system_context(require_session()):
        created = await documents.new_doc(target_dt, payload)
        await documents.set_value(
            "DeletedDocument",
            name,
            {
                "restored": True,
                "restored_at": datetime.now(UTC),
                "restored_to": created["name"],
            },
        )

    log.info("trash.restored", doctype=target_dt, from_snapshot=name, restored_to=created["name"])
    return created


@whitelist()
async def bulk_restore(names: list[str], allow_rename: bool = False) -> dict[str, Any]:
    """Відновити кілька знімків. Повертає ``{restored: [...], failed: [{name, error}]}``."""
    _require_system_manager()

    restored: list[str] = []
    failed: list[dict[str, str]] = []
    for n in names:
        try:
            doc = await restore(n, allow_rename=allow_rename)
            restored.append(doc["name"])
        except Exception as e:  # noqa: BLE001
            failed.append({"name": n, "error": str(getattr(e, "detail", e))})
    return {"restored": restored, "failed": failed}
