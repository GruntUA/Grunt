"""DocLike controller - you like documents for yourself, and only ones you can read."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.permissions.rbac import permission_checker


class DocLike(Document):
    reference_doctype: str
    reference_id: str

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user.
        if self.user:
            self.data["user"] = self.user
        if not self.data.get("user"):
            throw(_("Specify a user"))

        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_value(self.reference_doctype, self.reference_id, "*")
        if dt is None or doc is None:
            throw(_("Document not found"), "NOT_FOUND")
        if self.user and not await permission_checker.check(dt, "read", doc):
            throw(_("No access to the document"), "PERMISSION_DENIED")

    async def before_insert(self) -> None:
        if await self.grunt.db.exists(
            "DocLike",
            {
                "reference_doctype": self.reference_doctype,
                "reference_id": self.reference_id,
                "user": self.data["user"],
            },
        ):
            throw(_("You already like this document"), "DUPLICATE_DATA")
