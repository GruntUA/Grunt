"""Controller for the ``FormTourStep`` DocType."""

from grunt.document.base import Document


class FormTourStep(Document):
    """DocType controller for FormTourStep."""

    title: str | None
    description: str | None
    fieldname: str | None
    element: str | None
