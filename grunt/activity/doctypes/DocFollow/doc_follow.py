"""DocFollow controller - you follow documents for yourself, and only ones you can read."""

from grunt.auth.constants import SYSTEM_USER_EMAIL
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import session_user
from grunt.permissions.rbac import permission_checker


class DocFollow(Document):
    reference_doctype: str
    reference_id: str

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user. The
        # system (auto-follow, grunt.activity.follow) follows for whom it names.
        system = session_user() == SYSTEM_USER_EMAIL
        if session_user() and not system:
            self.data["user"] = session_user()
        if not self.data.get("user"):
            throw(_("Specify a user"))

        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_doc(self.reference_doctype, self.reference_id)
        if dt is None or doc is None:
            throw(_("Document not found"), "NOT_FOUND")
        # The system names someone else: they must be able to read it too, or
        # the followers' notifications would show them what they cannot open.
        reader = self.data["user"] if system else None
        if session_user() and not await permission_checker.check(dt, "read", doc, user=reader):
            throw(_("No access to the document"), "PERMISSION_DENIED")

    async def before_insert(self) -> None:
        if await self.grunt.db.exists(
            "DocFollow",
            {
                "reference_doctype": self.reference_doctype,
                "reference_id": self.reference_id,
                "user": self.data["user"],
            },
        ):
            throw(_("You are already following this document"), "DUPLICATE_DATA")
