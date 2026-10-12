"""CommentReaction controller - you react for yourself, on comments you can read."""

from __future__ import annotations

from grunt import _
from grunt.activity.reactions import reaction_choices
from grunt.document.base import Document
from grunt.permissions.rbac import permission_checker


class CommentReaction(Document):
    comment: str
    emoji: str

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user.
        if self.user is not None and self.user.email:
            self.data["user"] = self.user.email
        if not self.data.get("user"):
            self.grunt.throw(_("Specify a user"))

        if self.emoji not in await reaction_choices():
            self.grunt.throw(_("This reaction is not available"))

        ref = await self.grunt.db.get_value(
            "Comment", self.comment, ["reference_doctype", "reference_id"], as_dict=True
        )
        if ref is None:
            self.grunt.throw(_("Comment not found"), "NOT_FOUND")
        dt = await self.grunt.get_meta(ref.reference_doctype)
        doc = await self.grunt.db.get_value(ref.reference_doctype, ref.reference_id, "*")
        if dt is None or doc is None:
            self.grunt.throw(_("Document not found"), "NOT_FOUND")
        if self.user is not None and not await permission_checker.check(self.user, dt, "read", doc):
            self.grunt.throw(_("No access to the document"), "PERMISSION_DENIED")

    async def before_insert(self) -> None:
        if await self.grunt.db.exists(
            "CommentReaction",
            {"comment": self.comment, "emoji": self.emoji, "user": self.data["user"]},
        ):
            self.grunt.throw(_("You already reacted this way"), "DUPLICATE_DATA")
