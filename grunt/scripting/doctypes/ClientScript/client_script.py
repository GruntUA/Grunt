"""Controller for the ``ClientScript`` DocType."""

from grunt.document.base import Document


class ClientScript(Document):
    """DocType controller for ClientScript."""

    ref_doctype: str | None
    script: str | None
    is_enabled: bool | None
    is_standard: bool | None
    app: str | None
