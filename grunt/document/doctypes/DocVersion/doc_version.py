"""Controller for the ``DocVersion`` DocType."""

from typing import Any

from grunt.document.base import Document


class DocVersion(Document):
    """DocType controller for DocVersion."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # Document type
    doc_id: str  # Document ID
    version: int  # Version
    user: str  # User
    changes: Any | None = None  # Changes

    # end: auto-generated types
