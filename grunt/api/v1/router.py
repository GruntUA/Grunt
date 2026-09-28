"""V1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from grunt.api.v1.auth_methods import router as auth_methods_router
from grunt.api.v1.dashboard_data import router as dashboard_data_router
from grunt.api.v1.docs import router as docs_router
from grunt.api.v1.health import router as health_router
from grunt.api.v1.method import router as method_router
from grunt.api.v1.oauth import router as oauth_router
from grunt.api.v1.webhooks import router as webhooks_router
from grunt.api.v1.ws import router as ws_router

v1_router = APIRouter()

# System endpoints
v1_router.include_router(health_router, tags=["health"])
v1_router.include_router(ws_router, tags=["websocket"])

# Core Meta / Method invocation
v1_router.include_router(method_router, prefix="/method", tags=["method"])

# DocType RESTful API (The core engine)
v1_router.include_router(docs_router, prefix="/docs", tags=["docs"])

# Dashboard widget data
v1_router.include_router(dashboard_data_router, tags=["dashboard"])

# Pluggable authentication providers (password-less, passkeys, SSO, ...)
v1_router.include_router(auth_methods_router, prefix="/auth", tags=["auth"])

# External / Binary endpoints
v1_router.include_router(oauth_router, prefix="/oauth", tags=["oauth"])
v1_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
