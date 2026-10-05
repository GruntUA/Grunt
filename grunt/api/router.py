"""Custom FastAPI routers for the Grunt framework."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from grunt.auth.dependencies import grunt_context, grunt_context_optional


class GruntRouter(APIRouter):
    """APIRouter that automatically injects the Grunt context dependency.

    This removes the need for developers to manually add `Depends(grunt_context)`
    (or, for guest-accessible routers, `Depends(grunt_context_optional)`) to every
    endpoint - and the need for individual route handlers to open their own
    `async with grunt.context(...)`/`system_context(...)` just to make a session
    visible to `grunt.get_doc`/`grunt.db`/etc.

    Pass ``optional_auth=True`` for routers that mix anonymous and authenticated
    endpoints (login, register, password reset, ...) - ``grunt_context`` itself
    depends on ``current_user``, which raises 401 for guests, so it cannot be
    used router-wide when any route must work without a token. Routes that do
    require a real user still declare their own `Depends(current_user)` (or
    `Depends(superadmin_user)`, etc.) - `optional_auth` only controls whether the
    *ambient grunt context* is populated with a guest (``user=None``) or requires
    real authentication upfront.
    """

    def __init__(self, *args: Any, optional_auth: bool = False, **kwargs: Any) -> None:
        dependency = grunt_context_optional if optional_auth else grunt_context
        dependencies = kwargs.get("dependencies", [])
        dependencies.append(Depends(dependency))
        kwargs["dependencies"] = dependencies
        super().__init__(*args, **kwargs)
