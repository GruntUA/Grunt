"""Middleware to set Grunt API context (session, user, engine) for each request."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from grunt.api import clear_context


class GruntContextMiddleware(BaseHTTPMiddleware):
    """Set up Grunt API context (session, user, engine) for each request.

    This allows developers to use `from grunt import Doc` and call
    `await Doc.get()` without manually passing session/user/engine.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # Get dependencies from request state (set by auth/db middleware)
        try:
            # Get session from dependency injection machinery
            # For now, we'll set a placeholder — the actual session comes from
            # the FastAPI dependency system in endpoints
            pass
        finally:
            # Clear context at end of request
            pass

        response = await call_next(request)
        clear_context()
        return response
