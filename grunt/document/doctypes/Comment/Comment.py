"""Comment DocType controller — validation and permission enforcement."""

from __future__ import annotations

from typing import Any

from grunt.document.base import Document


class Comment(Document):
    reference_doctype: str
    reference_id: str
    content: str
    comment_type: str

    async def validate(self) -> None:
        if not (self.content or "").strip():
            self.grunt.throw("Вміст коментаря не може бути порожнім")

    async def before_delete(self) -> None:
        if (
            self.user
            and not getattr(self.user, "is_superadmin", False)
            and self.owner != self.user.email
        ):
            self.grunt.throw("Видалити коментар може лише автор або адміністратор")

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
        from grunt.app import grunt  # noqa: PLC0415

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
        from grunt.app import grunt  # noqa: PLC0415

        return await grunt.get_list(
            "Comment",
            filters={"reference_doctype": doctype, "reference_id": doc_id},
            order_by="created_at",
            order="asc",
            limit=1000,
        )

    @classmethod
    async def delete(cls, comment_id: str) -> None:
        """Delete a comment. Controller enforces ownership check."""
        from grunt.app import grunt  # noqa: PLC0415

        await grunt.delete_doc("Comment", comment_id)
