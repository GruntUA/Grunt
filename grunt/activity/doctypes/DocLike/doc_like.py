"""DocLike controller - you like documents for yourself, and only ones you can read."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import session_user
from grunt.permissions.rbac import permission_checker


class DocLike(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    reference_doctype: str  # Document type
    reference_id: str  # Document
    user: str | None = None  # User

    # end: auto-generated types

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user.
        if session_user():
            self.data["user"] = session_user()
        if not self.data.get("user"):
            throw(_("Specify a user"))

        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_doc(self.reference_doctype, self.reference_id)
        if dt is None or doc is None:
            throw(_("Document not found"), "NOT_FOUND")
        if session_user() and not await permission_checker.check(dt, "read", doc):
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
