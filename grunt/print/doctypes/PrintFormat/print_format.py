"""Controller for the ``PrintFormat`` DocType."""

from grunt.document.base import Document


class PrintFormat(Document):
    """DocType controller for PrintFormat."""

    ref_doctype: str | None
    template_type: str | None
    is_default: bool | None
    letter_head: str | None
    no_letter_head: bool | None
    is_standard: bool | None
    app: str | None
    template: str | None
