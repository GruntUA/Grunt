"""Realtime: tell the open form of a document that it, or its timeline, changed.

``after_save`` / ``after_delete`` on every DocType (``core_hooks``). After the
commit, into the document's room (``doc:<DocType>:<id>`` - joining it already
requires read on the document):

- ``doc_change`` - the document itself was saved (submit, cancel and workflow
  transitions save it too) or deleted. The form reloads it unless it holds
  unsaved edits; the timeline reloads (a new version, a transition comment).
- ``timeline_change`` - an item of its timeline was added, changed or removed:
  a comment or a reaction to it, a letter, an attached file, an assignment.

One event per document, kind and transaction (``on_commit`` key): a save that
also writes comments and files sends each kind once.
"""

from typing import Any

from grunt.api.v1.ws import manager
from grunt.db.api import GruntDB
from grunt.db.commit import on_commit
from grunt.log import log
from grunt.metadata.registry import doctype_registry

_db = GruntDB()  # stateless: reads through the context's session

# Timeline items -> the fields that point at the document they belong to.
TIMELINE_REFS: dict[str, tuple[str, str]] = {
    "Comment": ("reference_doctype", "reference_id"),
    "ToDo": ("reference_doctype", "reference_id"),
    "File": ("attached_to_doctype", "attached_to_id"),
    "EmailMessage": ("ref_doctype", "ref_name"),
}


async def announce_change(**kwargs: Any) -> None:
    """``after_save`` / ``after_delete`` hook: queue the room event(s)."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc")
    if not doctype or not isinstance(doc, dict):
        return
    try:
        target = await _timeline_target(doctype, doc)
        if target is not None:
            _queue(*target, "timeline_change", {"source": doctype})
            return
        if doctype in _SKIP or not doc.get("name") or await _is_log(doctype):
            return
        deleted = kwargs.get("event") == "after_delete"
        data: dict[str, Any] = {"source": "delete" if deleted else "save"}
        # The form compares it with its copy: its own save needs no reload.
        modified_at = doc.get("modified_at")
        if modified_at is not None:
            iso = getattr(modified_at, "isoformat", None)
            data["modified_at"] = iso() if iso else str(modified_at)
        if doc.get("modified_by"):
            data["modified_by"] = doc["modified_by"]
        _queue(doctype, str(doc["name"]), "doc_change", data)
    except Exception:
        log.exception("live.announce_failed", doctype=doctype)


# Timeline items and reactions are announced to their document; never as themselves.
_SKIP = frozenset({*TIMELINE_REFS, "CommentReaction"})


async def _timeline_target(doctype: str, doc: dict[str, Any]) -> tuple[str, str] | None:
    """The document whose timeline *doc* belongs to, if it is a timeline item."""
    if doctype == "CommentReaction":
        comment = doc.get("comment")
        if not comment:
            return None
        rows = await _db.get_all(
            "Comment",
            filters={"name": comment},
            fields=["reference_doctype", "reference_id"],
            limit=1,
        )
        doc = dict(rows[0]) if rows else {}
        doctype = "Comment"
    refs = TIMELINE_REFS.get(doctype)
    if refs is None:
        return None
    ref_doctype, ref_id = doc.get(refs[0]), doc.get(refs[1])
    if not ref_doctype or not ref_id:
        return None
    return str(ref_doctype), str(ref_id)


async def _is_log(doctype: str) -> bool:
    """Append-only logs (ActivityLog, Version, ...) have no open form to refresh."""
    try:
        dt = await doctype_registry.get(doctype)
    except Exception:
        return True
    return bool(getattr(dt, "is_log", False) or getattr(dt, "is_child", False))


def _queue(doctype: str, doc_id: str, event: str, data: dict[str, Any]) -> None:
    async def send() -> None:
        await manager.broadcast_doc(doctype, doc_id, event, data)

    on_commit(send, key=f"live:{event}:{doctype}:{doc_id}")
