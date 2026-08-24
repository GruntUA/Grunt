"""Backlinks RPC method, exposed as a static method of ``Document``.

RPC: grunt.document.base.Document.get_backlinks
"""

from __future__ import annotations

from typing import Any

import grunt


class DocumentMetaRPCMixin:
    """Cross-document metadata (backlinks), exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_backlinks(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return all documents that link to this document (backlinks)."""
        from grunt.app import grunt as grunt_app

        # Permission verification
        await grunt_app.get_doc(doctype, doc_id)

        from grunt.document.links import link_service

        return await link_service.get_backlinks(grunt_app._require_session(), doctype, doc_id)
