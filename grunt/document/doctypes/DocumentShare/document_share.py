"""DocumentShare DocType controller."""

from __future__ import annotations

import secrets

import grunt
from grunt.document.base import Document


class DocumentShare(Document):
    doctype_name: str
    doc_id: str
    token: str
    is_active: bool

    async def before_insert(self) -> None:
        """Creating a share token grants guest-level read access to the
        target document — get_shared_document() intentionally skips
        permission guards, since the token itself IS the authorization.
        Checked here (not only at the create_share() call site) so the
        generic docs CRUD path (POST /api/v1/docs/DocumentShare) can't be
        used to mint a public link to a document the creator can't even
        read themselves. Raises 403/404 via the same guard get_doc() uses
        everywhere else.
        """
        target_doctype = self.data.get("doctype_name")
        target_id = self.data.get("doc_id")
        if target_doctype and target_id:
            await grunt.get_doc(target_doctype, target_id)

        if not self.data.get("token"):
            self.data["token"] = secrets.token_urlsafe(32)
