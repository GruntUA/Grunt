"""Shared ContextVar storage for Grunt request context.

Both ``grunt.api.context`` and ``grunt.app`` import these objects so that
setting session / engine / user in one place is immediately visible everywhere.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser

_session_ctx: ContextVar[Optional["AsyncSession"]] = ContextVar("grunt_session", default=None)
_engine_ctx: ContextVar[Optional["AsyncEngine"]] = ContextVar("grunt_engine", default=None)
_user_ctx: ContextVar[Optional["GruntUser"]] = ContextVar("grunt_user", default=None)
_site_ctx: ContextVar[Optional[str]] = ContextVar("grunt_site", default=None)
