"""Comment DocType controller — validation and permission enforcement."""

from __future__ import annotations

from typing import Any

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

    async def before_delete(self) -> None:
        if (
            self.user
            and not user_has_roles(self.user, ["System Manager"])
            and self.owner != self.user.email
        ):
            self.grunt.throw(_("Only the author or an administrator can delete a comment"))

    # ------------------------------------------------------------------
    # Helper Classmethods
    # ------------------------------------------------------------------

    @classmethod
    async def add(
        cls,
        doctype: str,
        doc_id: str,
        text: str,
        is_private: bool = False,
    ) -> dict[str, Any]:
        """Add a comment to a document."""
        import grunt

        return await grunt.new_doc(
            "Comment",
            {
                "reference_doctype": doctype,
                "reference_id": doc_id,
                "content": text,
                "comment_type": "Comment",
                "is_private": is_private,
            },
        )

    @classmethod
    async def get_all(cls, doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Get all comments on a document."""
        import grunt

        return await grunt.get_list(
            "Comment",
            filters={"reference_doctype": doctype, "reference_id": doc_id},
            order_by="created_at",
            order="asc",
            limit=1000,
        )
