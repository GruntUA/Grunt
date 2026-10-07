"""Claim pending uploads a saved document refers to.

A file uploaded from a form before the document has an id (a new record, or
an image dropped into a rich-text field) is stored as a *pending* attachment:
``attached_to_doctype`` set, ``attached_to_id`` empty. When the document is
saved, every pending file of that DocType that one of its file-bearing fields
(Attach, Image, RichText - child-table rows included) points at is bound to
it, so the file shows among the document's attachments and inherits its
permissions.

Only the saving user's own pending uploads are claimed: library files, files
of another document and someone else's uploads are merely *referenced*.

A DocType with ``public_attachments`` is website content: linking a file from
it publishes the file - every referenced file the saving user can read becomes
``is_public``, so site visitors can download it by its plain URL (a file from
someone's private folder included; it stays out of other people's lists).
With ``is_published_field`` set, only a published document does that.
"""

from __future__ import annotations

import re
from typing import Any

import grunt
from grunt import log

# Attach / Image store a file URL; RichText holds any number of them in HTML.
_FILE_FIELD_TYPES = frozenset({"Attach", "Image", "RichText"})
_FILE_ID = re.compile(r"get_content\?file_id=([A-Za-z0-9_-]+)")


def file_ids_in(value: Any) -> set[str]:
    """``File`` ids behind every ``get_content?file_id=…`` URL in *value*."""
    return set(_FILE_ID.findall(value)) if isinstance(value, str) else set()


async def referenced_file_ids(doctype: str, doc: dict[str, Any]) -> set[str]:
    """File ids the document's Attach / Image / RichText fields point at."""
    meta = await grunt.get_meta(doctype)
    if meta is None:
        return set()
    ids: set[str] = set()
    for field in meta.fields:
        value = doc.get(field.fieldname)
        if field.fieldtype in _FILE_FIELD_TYPES:
            ids |= file_ids_in(value)
        elif field.fieldtype == "Table" and field.options and isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    ids |= await referenced_file_ids(field.options, row)
    return ids


async def claim_referenced_files(**kwargs: Any) -> None:
    """``after_save`` stage: bind the user's pending uploads to the saved document."""
    doctype, doc, user = kwargs.get("doctype"), kwargs.get("doc"), kwargs.get("user")
    if not doctype or doctype == "File" or not isinstance(doc, dict) or not doc.get("name"):
        return
    email = getattr(user, "email", None)
    if not email:
        return
    meta = await grunt.get_meta(doctype)
    if meta is None or meta.is_child or meta.is_virtual:
        return
    ids = await referenced_file_ids(doctype, doc)
    if not ids:
        return
    published = not meta.is_published_field or doc.get(meta.is_published_field)
    if meta.public_attachments and published:
        await _publish(ids, user)
    claimed = await grunt.db.bulk_update(
        "File",
        {
            "name__in": sorted(ids),
            "attached_to_doctype": doctype,
            "attached_to_id__is": "not set",
            "uploaded_by": email,
        },
        {"attached_to_id": str(doc["name"])},
    )
    if claimed:
        log.debug("storage.files_claimed", doctype=doctype, doc_id=doc["name"], count=claimed)


async def _publish(ids: set[str], user: Any) -> None:
    """Make the private files among *ids* that *user* may read public."""
    from grunt.permissions.rbac import permission_checker

    meta = await grunt.get_meta("File")
    if meta is None:
        return
    rows = await grunt.db.get_all(
        "File", filters={"name__in": sorted(ids)}, fields=["*"], limit=None
    )
    readable = [
        r["name"]
        for r in rows
        if not r.get("is_public") and await permission_checker.check(user, meta, "read", r)
    ]
    if readable:
        await grunt.db.bulk_update("File", {"name__in": readable}, {"is_public": 1})
        log.debug("storage.files_published", count=len(readable))
