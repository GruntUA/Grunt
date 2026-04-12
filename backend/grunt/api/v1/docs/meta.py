"""Metadata operations for Documents (Links)."""

from __future__ import annotations

from typing import Any

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt

router = GruntRouter(prefix="", tags=["meta"])


@router.get("/{doctype}/{doc_id}/links")
async def get_doc_links(
    doctype: str,
    doc_id: str,
) -> dict[str, Any]:
    """Return all documents that link to this document (backlinks)."""
    # Permission verification
    await grunt.get_doc(doctype, doc_id)

    from grunt.core.document.links import link_service

    links = await link_service.get_backlinks(grunt._require_session(), doctype, doc_id)
    return ok(links)
