"""Controller for the ``Language`` DocType."""

from grunt.document.base import Document


class Language(Document):
    """DocType controller for Language."""

    code: str | None
    title: str | None
    native_name: str | None
    script: str | None
    is_active: bool | None
