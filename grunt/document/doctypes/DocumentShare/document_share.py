"""DocumentShare DocType controller."""

import secrets

from grunt.document.base import Document
from grunt.errors import not_found
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.permissions.rbac import permission_checker
lazy from grunt.document.api import documents


class DocumentShare(Document):
    doctype_name: str
    doc_id: str
    token: str
    is_active: bool

    async def before_insert(self) -> None:
        """Creating a share token grants guest-level read access to the
        target document - get_shared_document() intentionally skips
        permission guards, since the token itself IS the authorization.
        Checked here (not only at the create_share() call site) so the
        generic docs CRUD path (POST /api/v1/docs/DocumentShare) can't be
        used to mint a public link to a document the creator can't even
        read themselves. Raises 403/404 via the same guard get_doc() uses
        everywhere else - and the ``share`` permission (with ``write``) on it.
        """
        target_doctype = self.data.get("doctype_name")
        target_id = self.data.get("doc_id")
        if target_doctype and target_id:
            doc = await documents.get_doc(target_doctype, target_id)
            dt = await doctype_registry.get_meta(target_doctype)
            if dt is None:
                raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": target_doctype})
            await permission_checker.require_share(dt, doc)

        if not self.data.get("token"):
            self.data["token"] = secrets.token_urlsafe(32)
