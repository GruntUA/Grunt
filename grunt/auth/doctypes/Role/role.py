"""Role DocType controller."""

from grunt.document.base import Document


class Role(Document):
    """DocType controller for Role."""

    role_name: str
    description: str | None
