"""Comment DocType controller - validation and permission enforcement."""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _
from grunt.document.base import Document
from grunt.permissions.roles import user_has_roles


class Comment(Document):
    reference_doctype: str
    reference_id: str
    content: str
    comment_type: str

    async def validate(self) -> None:
        if not (self.content or "").strip():
            self.grunt.throw(_("The comment cannot be empty"))
        await self._validate_parent()

    async def _validate_parent(self) -> None:
        """Threads are one level deep: a reply to a reply joins the root's thread."""
        parent_id = self.get("parent_comment")
        if not parent_id:
            return
        if parent_id == self.id:
            self.grunt.throw(_("A comment cannot reply to itself"))
        parent = await grunt.db.get_value(
            "Comment",
            parent_id,
            ["reference_doctype", "reference_id", "parent_comment"],
            as_dict=True,
        )
        if parent is None:
            self.grunt.throw(_("The comment you reply to no longer exists"), "NOT_FOUND")
        if (parent.reference_doctype, str(parent.reference_id)) != (
            self.reference_doctype,
            str(self.reference_id),
        ):
            self.grunt.throw(_("A reply must belong to the same document"))
        if parent.parent_comment:
            self.parent_comment = parent.parent_comment

    async def before_delete(self) -> None:
        is_admin = bool(self.user) and user_has_roles(self.user, ["System Manager"])
        if self.user and not is_admin and self.owner != self.user.email:
            self.grunt.throw(_("Only the author or an administrator can delete a comment"))

        replies = await grunt.db.get_all(
            "Comment", filters={"parent_comment": self.id}, fields=["name", "owner"], limit=10_000
        )
        if not replies:
            return
        # The thread goes with its root - someone else's replies only by an admin.
        if self.user and not is_admin and any(r["owner"] != self.user.email for r in replies):
            self.grunt.throw(
                _("Others replied to this comment - only an administrator can delete the thread")
            )
        for reply in replies:
            await grunt.delete_doc("Comment", reply["name"])

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
        return await grunt.new_doc(
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
    async def get_all(cls, doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Get all comments on a document."""
        return await grunt.get_list(
            "Comment",
            filters={"reference_doctype": doctype, "reference_id": doc_id},
            order_by="created_at",
            order="asc",
            limit=1000,
        )
