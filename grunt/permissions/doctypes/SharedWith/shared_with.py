"""SharedWith controller — only someone who may write a document can share it.

The grant itself is enforced in :mod:`grunt.permissions.shares`.
"""

from __future__ import annotations

from grunt.document.base import Document


class SharedWith(Document):
    reference_doctype: str
    reference_id: str
    permission: str

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user.
        target = (self.data.get("user") or "").strip()
        if not target:
            self.grunt.throw("Вкажіть користувача")
        self.data["user"] = target
        if self.permission not in ("Read", "Write"):
            self.data["permission"] = "Read"
        if not await self.grunt.db.exists("User", target):
            self.grunt.throw(f"Користувача «{target}» не знайдено", "NOT_FOUND")
        await self._require_write_on_reference()

    async def before_delete(self) -> None:
        await self._require_write_on_reference()

    async def _require_write_on_reference(self) -> None:
        from grunt.permissions.rbac import permission_checker

        if self.user is None:
            return
        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_value(self.reference_doctype, self.reference_id, "*")
        if dt is None or doc is None:
            self.grunt.throw("Документ не знайдено", "NOT_FOUND")
        if not await permission_checker.check(self.user, dt, "write", doc):
            self.grunt.throw(
                "Поділитися документом може лише той, хто має право його змінювати",
                "PERMISSION_DENIED",
            )
