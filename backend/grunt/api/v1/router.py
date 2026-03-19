"""V1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from grunt.api.v1.auth import router as auth_router
from grunt.api.v1.meta import router as meta_router
from grunt.api.v1.docs import router as docs_router

v1_router = APIRouter()

v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
v1_router.include_router(meta_router, prefix="/meta", tags=["meta"])
v1_router.include_router(docs_router, prefix="/docs", tags=["docs"])
