"""Controller for the ``ServerScript`` DocType."""

from grunt.document.base import Document


class ServerScript(Document):
    """DocType controller for ServerScript."""

    script_type: str | None
    ref_doctype: str | None
    event: str | None
    api_method: str | None
    cron: str | None
    script: str | None
    is_enabled: bool | None
    allow_guest: bool | None
    is_standard: bool | None
    app: str | None
