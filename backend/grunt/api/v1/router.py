"""V1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from grunt.api.v1.auth import router as auth_router
from grunt.api.v1.meta import router as meta_router
from grunt.api.v1.docs import router as docs_router
from grunt.api.v1.ws import router as ws_router
from grunt.api.v1.apps import router as apps_router
from grunt.api.v1.reports import router as reports_router
from grunt.api.v1.pages import router as pages_router
from grunt.api.v1.workspace import router as workspace_router
from grunt.api.v1.search import router as search_router
from grunt.api.v1.files import router as files_router

v1_router = APIRouter()

v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
v1_router.include_router(meta_router, prefix="/meta", tags=["meta"])
v1_router.include_router(docs_router, prefix="/docs", tags=["docs"])
v1_router.include_router(ws_router, tags=["websocket"])
v1_router.include_router(apps_router, prefix="/apps", tags=["apps"])
v1_router.include_router(reports_router, prefix="/reports", tags=["reports"])
v1_router.include_router(pages_router, prefix="/pages", tags=["pages"])
v1_router.include_router(workspace_router, prefix="/workspaces", tags=["workspaces"])
v1_router.include_router(search_router, tags=["search"])
v1_router.include_router(files_router, prefix="/files", tags=["files"])
