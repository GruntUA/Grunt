"""Controller for the ``DocTypeAction`` DocType."""

from grunt.document.base import Document


class DocTypeAction(Document):
    """DocType controller for DocTypeAction."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    action: str  # Action
    label: str | None = None  # Label
    group: str | None = None  # Group
    variant: str | None = None  # Button style
    hidden: bool | None = None  # Hidden
    condition: str | None = None  # Display condition

    # end: auto-generated types
