"""LetterHead controller - keeps a single default letterhead."""

from grunt.db.api import GruntDB
from grunt.document.base import Document

_db = GruntDB()  # stateless: reads through the context's session


class LetterHead(Document):
    """DocType controller for LetterHead."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    is_default: bool | None = None  # Default
    disabled: bool | None = None  # Disabled
    logo: str | None = None  # Logo
    header: str | None = None  # Header HTML
    footer: str | None = None  # Footer HTML

    # end: auto-generated types

    async def validate(self) -> None:
        if self.disabled:
            self.is_default = False

    async def after_save(self) -> None:
        if not self.is_default:
            return
        # Setting a new default clears the old one.
        await _db.bulk_update(
            "LetterHead", {"is_default": True, "name__ne": self.id}, {"is_default": False}
        )
