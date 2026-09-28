"""Soft-delete snapshots — Ґрунтів кошик видалених документів.

Коли документ видаляється, ядро (:class:`~grunt.document.mixins.write.DocumentWriteMixin`)
робить повний ``get_document`` знімок (скаляри + дочірні таблиці + MultiLink) і
проганяє його через ``fire("after_delete", doc=existing, ...)``. Тут ми ловимо
цей знімок і кладемо його у DocType ``DeletedDocument``, звідки документ можна
відновити методом :func:`restore`.

Реєстрація хука — у :mod:`grunt.main` (wildcard ``after_delete``), поряд із
``grunt.activity.log_activity``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import grunt
from grunt import log


def _title_of(dt: Any, doc: dict[str, Any]) -> str:
    """Best-effort human-readable label for the snapshot.

    Prefers the DocType's ``title_field``; when that is unset (``"name"``) falls
    back to a conventionally-named field so the trash list isn't a wall of ids.
    """
    tf = getattr(dt, "title_field", None) or "name"
    val = doc.get(tf) if tf != "name" else None
    if not val:
        for cand in ("title", "subject", "label", "full_name", "name"):
            if doc.get(cand):
                val = doc[cand]
                break
    return str(val or doc.get("name") or "")[:255]


async def snapshot_deleted_document(event: str, **kwargs: Any) -> None:
    """``after_delete`` wildcard hook: stash a restorable JSON snapshot.

    Best-effort — a failure here is logged and never blocks the delete
    (``_call_hook`` already swallows exceptions, but we guard anyway so a
    partial snapshot is never written).
    """
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    if not doctype or not isinstance(doc, dict):
        return
    if not doc.get("name"):
        return

    dt = await grunt.get_meta(doctype)
    if dt is None:
        return

    # Дочірні рядки їдуть у знімку батька; окремих табличних доктайпів,
    # віртуальних та інших журналів не чіпаємо.
    if getattr(dt, "is_child", False) or getattr(dt, "is_virtual", False):
        return
    if getattr(dt, "is_log", False):
        return
    # Точкове вимкнення для конкретного DocType (за замовчуванням увімкнено).
    if getattr(dt, "track_deletions", True) is False:
        return

    user_obj = kwargs.get("user")
    deleted_by = getattr(user_obj, "email", None) or str(user_obj or "system")

    session = grunt.get_session()
    try:
        async with grunt.system_context(session):
            await grunt.new_doc(
                "DeletedDocument",
                {
                    "deleted_doctype": doctype,
                    "deleted_name": str(doc["name"]),
                    "title": _title_of(dt, doc),
                    "deleted_by": deleted_by,
                    "deleted_at": datetime.now(UTC),
                    "data": doc,
                },
            )
    except Exception as e:  # noqa: BLE001
        log.warning("trash.snapshot_failed", error=str(e), doctype=doctype, doc_id=doc.get("name"))
