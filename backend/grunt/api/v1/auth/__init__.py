"""Auth API — modular routes."""

from fastapi import APIRouter

from grunt.api.v1.auth.admin import router as admin_router
from grunt.api.v1.auth.api_keys import router as api_keys_router
from grunt.api.v1.auth.core import router as core_router
from grunt.api.v1.auth.mfa import router as mfa_router
from grunt.api.v1.auth.password import router as password_router

router = APIRouter()

# Include all sub-routers
router.include_router(core_router)
router.include_router(password_router)
router.include_router(admin_router)
router.include_router(mfa_router)
router.include_router(api_keys_router)
