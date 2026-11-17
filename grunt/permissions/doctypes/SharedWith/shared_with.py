"""SharedWith controller - who may share a document, with whom, and the
notification that tells them.

A share goes to exactly one of a user, a role or everyone. The sharer needs
``share`` on the document *and* the level they hand out (``read`` for Read,
``write`` for Write) - a share never passes on more than the sharer has. Who
received a share may drop it themselves. The grant itself is enforced in
:mod:`grunt.permissions.shares`.
"""

from datetime import date, datetime
from typing import Any

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.notification.events import trigger
from grunt.permissions.rbac import permission_checker
from grunt.permissions.roles import role_holders

SHARE_EVENT = "grunt.share.created"


class SharedWith(Document):
    reference_doctype: str
    reference_id: str
    permission: str

    async def validate(self) -> None:
        # ``user`` is a field here, but ``self.user`` is the acting user.
        target = (self.data.get("user") or "").strip() or None
        role = (self.data.get("role") or "").strip() or None
        everyone = bool(self.data.get("everyone"))
        # "All" is every user, held implicitly - that's what "everyone" is;
        # a guest never gets a share (only a public link).
        if role == "All":
            role, everyone = None, True
        if role == "Guest":
            throw(_("Guests see a document only through a public link"))
        if sum((target is not None, role is not None, everyone)) != 1:
            throw(_("Share with one of: a user, a role or everyone"))
        self.data.update(user=target, role=role, everyone=everyone)
        if self.permission not in ("Read", "Write"):
            self.data["permission"] = "Read"
        self.data["can_reshare"] = bool(self.data.get("can_reshare"))
        if target and not await self.grunt.db.exists("User", target):
            throw(_("User “%(user)s” not found") % {"user": target}, "NOT_FOUND")
        if role and not await self.grunt.db.exists("Role", role):
            throw(_("Role “%(role)s” not found") % {"role": role}, "NOT_FOUND")
        valid_to = _day(self.data.get("valid_to"))
        if valid_to is not None and valid_to < date.today():
            throw(_("The end date has already passed"))
        await self._require_share_on_reference(self.permission)

    async def before_delete(self) -> None:
        # Whoever received a share may give it up; anyone else needs to be
        # able to share the document.
        if self.user is not None and self.data.get("user") == self.user:
            return
        await self._require_share_on_reference("Read")

    async def after_insert(self) -> None:
        recipients: list[str] = []
        if self.data.get("user"):
            recipients = [self.data["user"]]
        elif self.data.get("role"):
            holders = await role_holders([self.data["role"]])
            recipients = [h["email"] for h in holders if h.get("email")]
        # "Everyone" tells nobody: a notification to every account is noise.
        recipients = [r for r in recipients if r != self.user]
        if not recipients:
            return
        ref = (self.reference_doctype, str(self.reference_id))
        await trigger(
            SHARE_EVENT,
            doc={**self.data, "name": self.id},
            doctype="SharedWith",
            link=ref,
            recipients=recipients,
            actor=self.user or "",
            extra={"target": f"{ref[0]} {ref[1]}", "level": self._level_label},
            session=self.session,
        )

    def _level_label(self) -> str:
        return _("edit") if self.permission == "Write" else _("view")

    async def _require_share_on_reference(self, level: str) -> None:
        if self.user is None:
            return
        dt = await self.grunt.get_meta(self.reference_doctype)
        doc = await self.grunt.db.get_value(self.reference_doctype, self.reference_id, "*")
        if dt is None or doc is None:
            throw(_("Document not found"), "NOT_FOUND")
        if not await permission_checker.can_share(dt, doc, level=level):
            throw(
                _("You may share this document only at a level you have yourself"),
                "PERMISSION_DENIED",
            )


def _day(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
