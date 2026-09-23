"""DocFollow controller — you follow documents for yourself, and only ones you can read."""

from __future__ import annotations

from grunt.document.base import Document


class DocFollow(Document):
    reference_doctype: str
    reference_id: str

    async def validate(self) -> None:
        from grunt.permissions.rbac import permission_checker

        # ``user`` is a field here, but ``self.user`` is the acting user.
        if self.user is not None and self.user.email:
            self.data["user"] = self.user.email
        if not self.data.get("user"):
            self.grunt.throw("Вкажіть користувача")

        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_value(self.reference_doctype, self.reference_id, "*")
        if dt is None or doc is None:
            self.grunt.throw("Документ не знайдено", "NOT_FOUND")
        if self.user is not None and not await permission_checker.check(self.user, dt, "read", doc):
            self.grunt.throw("Немає доступу до документа", "PERMISSION_DENIED")

    async def before_insert(self) -> None:
        if await self.grunt.db.exists(
            "DocFollow",
            {
                "reference_doctype": self.reference_doctype,
                "reference_id": self.reference_id,
                "user": self.data["user"],
            },
        ):
            self.grunt.throw("Ви вже стежите за цим документом", "DUPLICATE_DATA")
