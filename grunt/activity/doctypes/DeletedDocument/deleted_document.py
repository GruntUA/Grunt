"""``DeletedDocument`` - restorable JSON snapshots of deleted documents.

Snapshots are written by the ``after_delete`` hook in :mod:`grunt.activity.trash`.
This module holds the controller plus the whitelisted :func:`restore` /
:func:`bulk_restore` RPCs the trash-bin UI calls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import grunt
from grunt import _, log
from grunt.document.base import Document
from grunt.metadata.registry import doctype_registry
from grunt.permissions.roles import user_has_roles

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
    if not user_has_roles(grunt.get_user(), ["System Manager"]):
        grunt.throw(_("Only a System Manager can restore documents"), code="FORBIDDEN")


def _snapshot_payload(snap: dict[str, Any]) -> dict[str, Any]:
    raw = snap.get("data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            grunt.throw(_("The snapshot is corrupted: invalid JSON"), code="INVALID_SNAPSHOT")
    if not isinstance(raw, dict):
        grunt.throw(_("The snapshot is empty"), code="INVALID_SNAPSHOT")
    return {k: v for k, v in raw.items() if k not in _STRIP_ON_RESTORE}


@grunt.whitelist()
async def restore(name: str, allow_rename: bool = False) -> dict[str, Any]:
    """Відновити один видалений документ зі знімка ``name``.

    Повертає відновлений документ. Якщо оригінальний ID зайнятий - кине
    помилку, доки не передано ``allow_rename=True`` (тоді буде згенеровано
    новий ID за правилом autoname цільового DocType).

    Обмеження: зв'язки з/на інші документи, почищені каскадно при видаленні,
    назад не відновлюються; ``owner`` та час створення стають поточними.
    """
    _require_system_manager()

    snap = await grunt.get_doc("DeletedDocument", name)
    if snap.get("restored"):
        grunt.throw(
            _("Already restored as “%(name)s”") % {"name": snap.get("restored_to") or "?"},
            code="ALREADY_RESTORED",
        )

    target_dt = snap["deleted_doctype"]
    try:
        await doctype_registry.get(target_dt)
    except Exception:
        grunt.throw(
            _("DocType “%(doctype)s” no longer exists") % {"doctype": target_dt},
            code="DOCTYPE_GONE",
        )

    payload = _snapshot_payload(snap)
    orig_name = str(snap["deleted_name"])

    if await grunt.db.exists(target_dt, orig_name):
        if not allow_rename:
            grunt.throw(
                _("Document “%(name)s” already exists. Restore with a new ID?")
                % {"name": orig_name},
                code="NAME_TAKEN",
            )
        payload.pop("name", None)

    async with grunt.system_context(grunt.get_session()):
        created = await grunt.new_doc(target_dt, payload)
        await grunt.set_value(
            "DeletedDocument",
            name,
            {
                "restored": 1,
                "restored_at": datetime.now(UTC),
                "restored_to": created["name"],
            },
        )

    log.info("trash.restored", doctype=target_dt, from_snapshot=name, restored_to=created["name"])
    return created


@grunt.whitelist()
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
