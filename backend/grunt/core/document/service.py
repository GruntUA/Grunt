"""DocumentService — dynamic CRUD for any DocType.

Knows nothing about specific schemas ahead of time; everything comes from the
DocType registry at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from grunt.app import grunt as _grunt
from grunt.core.document.mixins.read import DocumentReadMixin
from grunt.core.document.mixins.write import DocumentWriteMixin
from grunt.core.document.multi_link import MultiLinkService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import User

logger = structlog.get_logger()


class DocumentService(DocumentReadMixin, DocumentWriteMixin):
    """Dynamic CRUD for any registered DocType."""

    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self.session = session
        self.engine = engine
        self._ml = MultiLinkService(session)

    def _set_grunt_context(self, user: User) -> tuple:
        """Activate the grunt ContextVar context for the current lifecycle scope."""
        return _grunt.set_context(session=self.session, engine=self.engine, user=user)

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None:
        _grunt.reset_context(tokens)
