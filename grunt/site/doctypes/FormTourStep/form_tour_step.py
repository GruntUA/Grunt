"""Controller for the ``FormTourStep`` DocType."""

from grunt.document.base import Document


class FormTourStep(Document):
    """DocType controller for FormTourStep."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    description: str | None = None  # Description
    fieldname: str | None = None  # Field
    element: str | None = None  # Element

    # end: auto-generated types
