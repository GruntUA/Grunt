from __future__ import annotations

import grunt
from grunt import _
from grunt.document.base import Document


class FileFolder(Document):
    """DocType controller for FileFolder — a node of the file library tree."""

    folder_name: str
    parent_folder: str | None

    async def before_delete(self) -> None:
        """Only an empty folder can go — files and subfolders are moved out first."""
        if await grunt.db.count("File", {"folder": self.name}):
            grunt.throw(_("The folder is not empty: move or delete its files first"))
        if await grunt.db.count("FileFolder", {"parent_folder": self.name}):
            grunt.throw(_("The folder has subfolders: move or delete them first"))
