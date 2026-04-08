"""Shared ContextVar storage for Grunt request context.

Both ``grunt.api.context`` and ``grunt.app`` import these objects so that
setting session / engine / user in one place is immediately visible everywhere.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser

_session_ctx: ContextVar[AsyncSession | None] = ContextVar("grunt_session", default=None)
_engine_ctx: ContextVar[AsyncEngine | None] = ContextVar("grunt_engine", default=None)
_user_ctx: ContextVar[GruntUser | None] = ContextVar("grunt_user", default=None)
_site_ctx: ContextVar[str | None] = ContextVar("grunt_site", default=None)
