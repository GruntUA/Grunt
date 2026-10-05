"""DocFollow controller - you follow documents for yourself, and only ones you can read."""

from __future__ import annotations

from grunt import _
from grunt.document.base import Document
from grunt.permissions.rbac import permission_checker


class DocFollow(Document):
    reference_doctype: str
    reference_id: str

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user.
        if self.user is not None and self.user.email:
            self.data["user"] = self.user.email
        if not self.data.get("user"):
            self.grunt.throw(_("Specify a user"))

        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_value(self.reference_doctype, self.reference_id, "*")
        if dt is None or doc is None:
            self.grunt.throw(_("Document not found"), "NOT_FOUND")
        if self.user is not None and not await permission_checker.check(self.user, dt, "read", doc):
            self.grunt.throw(_("No access to the document"), "PERMISSION_DENIED")

    async def before_insert(self) -> None:
        if await self.grunt.db.exists(
            "DocFollow",
            {
                "reference_doctype": self.reference_doctype,
                "reference_id": self.reference_id,
                "user": self.data["user"],
            },
        ):
            self.grunt.throw(_("You are already following this document"), "DUPLICATE_DATA")
