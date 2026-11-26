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

from datetime import datetime
from typing import Any

from grunt.api.v1.ws import manager
from grunt.db.api import GruntDB
from grunt.db.commit import on_commit
from grunt.document.doctypes.Comment.comment import Comment
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.store.base import SQL
from grunt.store.lookup import supports
from grunt.utils.attr_dict import AttrDict, as_row

_db = GruntDB()  # stateless: reads through the context's session

# Items shown in a document's timeline. They are announced to that document,
# never in a room of their own.
TIMELINE_ITEMS = frozenset({"Comment", "CommentReaction", "ToDo", "File", "EmailMessage"})


async def announce_change(*, doctype: str, doc: dict[str, Any], event: str, **_: Any) -> None:
    """``after_save`` / ``after_delete`` hook of every DocType.

    Two cases:

    1. A timeline item changed (a comment, reaction, file, letter, assignment):
       the document it belongs to hears ``timeline_change``.
    2. Any other document changed: its own room hears ``doc_change``.
    """
    row = as_row(doc)
    try:
        if doctype in TIMELINE_ITEMS:
            owner = await _owner_of(doctype, row)
            if owner is not None:
                _queue(*owner, "timeline_change", {"source": doctype})
        elif await _has_form(doctype):
            deleted = event == "after_delete"
            _queue(doctype, str(row.name), "doc_change", _doc_change_data(row, deleted))
    except Exception:
        log.exception("live.announce_failed", doctype=doctype)


async def announce_moved(*, doctype: str, doc: dict[str, Any], **_: Any) -> None:
    """``before_save`` of a timeline item: an update that points it at another
    document tells the previous one too (after the commit, like the rest).

    *doc* is the update's payload - the changed fields and the ``id``; an
    insert has no ``id`` and no previous document.
    """
    payload = as_row(doc)
    if "id" not in payload:
        return
    try:
        stored = await _db.get_all(doctype, filters={"name": payload.id}, limit=1)
        if not stored:
            return
        before = stored[0]
        after = as_row({**before, **payload})
        old_owner = await _owner_of(doctype, before)
        if old_owner is not None and old_owner != await _owner_of(doctype, after):
            _queue(*old_owner, "timeline_change", {"source": doctype})
    except Exception:
        log.exception("live.announce_failed", doctype=doctype)


async def _owner_of(doctype: str, item: AttrDict) -> tuple[str, str] | None:
    """The document whose timeline shows *item*: (DocType, id), or None."""
    match doctype:
        case "Comment" | "ToDo":
            return _ref(item.reference_doctype, item.reference_id)
        case "File":
            return _ref(item.attached_to_doctype, item.attached_to_id)
        case "EmailMessage":
            return _ref(item.ref_doctype, item.ref_name)
        case "CommentReaction":
            comment = await _db.get_value(
                Comment, item.comment, ["reference_doctype", "reference_id"], as_dict=True
            )
            return _ref(comment.reference_doctype, comment.reference_id) if comment else None
        case _:
            return None


def _ref(ref_doctype: Any, ref_id: Any) -> tuple[str, str] | None:
    """(DocType, id) of a reference, or None when it points nowhere."""
    if not ref_doctype or not ref_id:
        return None
    return str(ref_doctype), str(ref_id)


async def _has_form(doctype: str) -> bool:
    """Whether a document of *doctype* is edited in a form of its own and kept
    in the database (with ``modified_at`` / ``modified_by``) - not an
    append-only log (ActivityLog, ...), a child table row or an outside store."""
    try:
        dt = await doctype_registry.get(doctype)
    except Exception:
        return False
    return not (dt.is_log or dt.is_child) and supports(dt, SQL)


def _doc_change_data(doc: AttrDict, deleted: bool) -> dict[str, Any]:
    """The ``doc_change`` payload. The form compares ``modified_at`` with its
    own copy - the save it made itself needs no reload - and ``modified_by``
    with the signed-in user - their own change needs no "updated by another
    user" toast."""
    data: dict[str, Any] = {"source": "delete" if deleted else "save"}
    if isinstance(doc.modified_at, datetime):
        data["modified_at"] = doc.modified_at.isoformat()
    elif doc.modified_at is not None:
        data["modified_at"] = str(doc.modified_at)
    if doc.modified_by:
        data["modified_by"] = doc.modified_by
    return data


def _queue(doctype: str, doc_id: str, event: str, data: dict[str, Any]) -> None:
    async def send() -> None:
        await manager.broadcast_doc(doctype, doc_id, event, data)

    on_commit(send, key=f"live:{event}:{doctype}:{doc_id}")
