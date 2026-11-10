"""LetterHead controller - keeps a single default letterhead."""

from grunt.db.api import GruntDB
from grunt.document.base import Document

_db = GruntDB()  # stateless: reads through the context's session


class LetterHead(Document):
    """DocType controller for LetterHead."""

    async def validate(self) -> None:
        if self.get("disabled"):
            self.is_default = False

    async def after_save(self) -> None:
        if not self.get("is_default"):
            return
        # Setting a new default clears the old one.
        await _db.bulk_update(
            "LetterHead", {"is_default": True, "name__ne": self.id}, {"is_default": False}
        )
