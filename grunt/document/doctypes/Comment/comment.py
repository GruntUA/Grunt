"""Comment DocType controller - validation and permission enforcement."""

from typing import Any

from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import session_user
from grunt.permissions.perms import has_perm
from grunt.utils.attr_dict import AttrDict
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session


class Comment(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    reference_doctype: str  # Document type
    reference_id: str  # Document ID
    content: str  # Content
    comment_type: str | None = None  # Type
    parent_comment: str | None = None  # Reply to

    # end: auto-generated types

    async def validate(self) -> None:
        if not (self.content or "").strip():
            throw(_("The comment cannot be empty"))
        await self._validate_parent()

    async def _validate_parent(self) -> None:
        """Threads are one level deep: a reply to a reply joins the root's thread."""
        parent_id = self.parent_comment
        if not parent_id:
            return
        if parent_id == self.id:
            throw(_("A comment cannot reply to itself"))
        parent = await _db.get_value(
            "Comment",
            parent_id,
            ["reference_doctype", "reference_id", "parent_comment"],
            as_dict=True,
        )
        if parent is None:
            throw(_("The comment you reply to no longer exists"), "NOT_FOUND")
        if (parent.reference_doctype, str(parent.reference_id)) != (
            self.reference_doctype,
            str(self.reference_id),
        ):
            throw(_("A reply must belong to the same document"))
        if parent.parent_comment:
            self.parent_comment = parent.parent_comment

    async def before_delete(self) -> None:
        is_admin = bool(session_user()) and await has_perm("grunt.moderate_comments")
        if session_user() and not is_admin and self.owner != session_user():
            throw(_("Only the author or an administrator can delete a comment"))

        replies = await _db.get_all(
            "Comment", filters={"parent_comment": self.id}, fields=["name", "owner"], limit=10_000
        )
        if not replies:
            return
        # The thread goes with its root - someone else's replies only by an admin.
        if session_user() and not is_admin and any(r.owner != session_user() for r in replies):
            throw(_("Others replied to this comment - only an administrator can delete the thread"))
        for reply in replies:
            await documents.delete_doc("Comment", reply.name)

    # Helper Classmethods

    @classmethod
    async def add(
        cls,
        doctype: str,
        doc_id: str,
        text: str,
        is_private: bool = False,
        parent_comment: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment (or, with ``parent_comment``, a reply) to a document."""
        return await documents.new_doc(
            "Comment",
            {
                "reference_doctype": doctype,
                "reference_id": doc_id,
                "content": text,
                "comment_type": "Comment",
                "is_private": is_private,
                "parent_comment": parent_comment,
            },
        )

    @classmethod
    async def get_all(cls, doctype: str, doc_id: str) -> list[AttrDict]:
        """Get all comments on a document."""
        return await documents.get_list(
            "Comment",
            filters={"reference_doctype": doctype, "reference_id": doc_id},
            order_by="created_at",
            order="asc",
            limit=1000,
        )
