"""V1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from grunt.api.v1.health import router as health_router
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
from grunt.api.v1.notifications import router as notifications_router
from grunt.api.v1.translations import router as translations_router
from grunt.api.v1.scripting import router as scripting_router
from grunt.api.v1.webform import router as webform_router
from grunt.api.v1.dashboard import router as dashboard_router
from grunt.api.v1.metrics import router as metrics_router
from grunt.api.v1.oauth import router as oauth_router
from grunt.api.v1.data_import import router as data_import_router
from grunt.api.v1.activity import router as activity_router
from grunt.api.v1.hooks import router as hooks_router
from grunt.api.v1.email import router as email_router
from grunt.api.v1.assignment import router as assignment_router
from grunt.api.v1.dev import router as dev_router

v1_router = APIRouter()

v1_router.include_router(health_router, tags=["health"])
v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
v1_router.include_router(meta_router, prefix="/meta", tags=["meta"])
v1_router.include_router(docs_router, prefix="/docs", tags=["docs"])
v1_router.include_router(ws_router, tags=["websocket"])
v1_router.include_router(apps_router, prefix="/apps", tags=["apps"])
v1_router.include_router(reports_router, prefix="/reports", tags=["reports"])
v1_router.include_router(pages_router, prefix="/pages", tags=["pages"])
v1_router.include_router(workspace_router, prefix="/workspaces", tags=["workspaces"])
v1_router.include_router(search_router, prefix="/search", tags=["search"])
v1_router.include_router(files_router, prefix="/files", tags=["files"])
v1_router.include_router(notifications_router, tags=["notifications"])
v1_router.include_router(translations_router, tags=["i18n"])
v1_router.include_router(scripting_router, tags=["scripting"])
v1_router.include_router(webform_router, tags=["webform"])
v1_router.include_router(dashboard_router, tags=["dashboard"])
v1_router.include_router(metrics_router, tags=["monitoring"])
v1_router.include_router(oauth_router, prefix="/oauth", tags=["oauth"])
v1_router.include_router(data_import_router, prefix="/data-import", tags=["data-import"])
v1_router.include_router(activity_router, prefix="/activity", tags=["activity"])
v1_router.include_router(hooks_router, prefix="/hooks", tags=["hooks"])
v1_router.include_router(email_router, tags=["email"])
v1_router.include_router(assignment_router, tags=["assignment"])
v1_router.include_router(dev_router, tags=["dev"])
