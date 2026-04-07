"""ActivityLog DocType controller — auto-fills user from request context."""

from __future__ import annotations

from grunt.core.document.base import Document


class ActivityLog(Document):
    # NOTE: 'doctype' and 'user' are reserved names in Document base class.
    # Access these fields via self.data.get("doctype") / self.data.get("user").
    doc_id: str
    action: str
    details: dict

    async def before_insert(self) -> None:
        # Auto-set 'user' field from request context if caller didn't provide it.
        if not self.data.get("user") and self.user:
            self.data["user"] = self.user.email
