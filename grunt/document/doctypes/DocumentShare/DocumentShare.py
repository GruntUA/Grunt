"""DocumentShare DocType controller."""

from __future__ import annotations

import secrets

from grunt.document.base import Document


class DocumentShare(Document):
    doctype_name: str
    doc_id: str
    token: str
    is_active: bool

    async def before_insert(self) -> None:
        if not self.data.get("token"):
            self.data["token"] = secrets.token_urlsafe(32)
