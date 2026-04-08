"""Comment DocType controller — validation and permission enforcement."""

from __future__ import annotations

from grunt.core.document.base import Document


class Comment(Document):
    reference_doctype: str
    reference_id: str
    content: str
    comment_type: str

    async def validate(self) -> None:
        if not (self.content or "").strip():
            self.grunt.throw("Вміст коментаря не може бути порожнім")

    async def before_delete(self) -> None:
        if self.user and not getattr(self.user, "is_superadmin", False):
            if self.owner != self.user.email:
                self.grunt.throw("Видалити коментар може лише автор або адміністратор")
