"""Custom FastAPI routers for the Grunt framework."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from grunt.auth.dependencies import grunt_context


class GruntRouter(APIRouter):
    """APIRouter that automatically injects the Grunt context dependency.

    This removes the need for developers to manually add `Depends(grunt_context)`
    to every endpoint.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Prepend grunt_context to the dependencies list
        dependencies = kwargs.get("dependencies", [])
        dependencies.append(Depends(grunt_context))
        kwargs["dependencies"] = dependencies
        super().__init__(*args, **kwargs)
