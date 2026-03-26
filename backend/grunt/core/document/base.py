from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from grunt.core.auth.models import GruntUser


class Document:
    """Base class for all DocType controllers.

    Custom DocType logic should inherit from this class and be placed in
    the app's `controllers` or `doctypes` directory.
    """

    def __init__(
        self,
        doctype: str,
        data: dict[str, Any],
        user: GruntUser | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self.doctype = doctype
        self.data = data
        self.user = user
        self.session = session

    def __getattr__(self, name: str) -> Any:
        return self.data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("doctype", "data", "user", "session"):
            super().__setattr__(name, value)
        else:
            self.data[name] = value

    async def before_insert(self) -> None:
        """Called before a new document is inserted into the database."""
        pass

    async def after_insert(self) -> None:
        """Called after a new document is inserted into the database."""
        pass

    async def before_save(self) -> None:
        """Called before an existing document is updated in the database."""
        pass

    async def after_save(self) -> None:
        """Called after an existing document is updated in the database."""
        pass

    async def before_delete(self) -> None:
        """Called before a document is deleted from the database."""
        pass

    async def after_delete(self) -> None:
        """Called after a document is deleted from the database."""
        pass

    async def validate(self) -> None:
        """Custom validation logic."""
        pass
