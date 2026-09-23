"""FastAPI application entry point.

A thin assembly: create the app, add middleware, wire routes. Startup and
shutdown live in :mod:`grunt.startup.lifespan`; route groups in
:mod:`grunt.startup.{dev,errors,website}`; app/hook discovery in
:mod:`grunt.apps`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from grunt.api.v1.router import v1_router
from grunt.apps import load_core
from grunt.config import settings
from grunt.i18n.middleware import LanguageMiddleware
from grunt.middleware.logging import RequestLoggingMiddleware
from grunt.middleware.rate_limit import RateLimitMiddleware
from grunt.middleware.security import SecurityHeadersMiddleware
from grunt.site.middleware import SiteContextMiddleware
from grunt.startup.dev import register_dev_proxy
from grunt.startup.errors import register_exception_handlers
from grunt.startup.lifespan import lifespan
from grunt.startup.website import register_website_routes
from grunt.storage.signing import SignedFileURLResponse

# Wire the framework's own hooks/resources ("app zero"). External apps are
# loaded from the lifespan, once the DB says which are installed.
load_core()

app = FastAPI(
    title="Ґрунт API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    # Signs private-file URLs in every JSON response (grunt.storage.signing).
    default_response_class=SignedFileURLResponse,
)

app.add_middleware(LanguageMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SiteContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_dev_proxy(app)
app.include_router(v1_router, prefix="/api/v1")
register_exception_handlers(app)

# Must be last: register_website_routes() ends with the "/{path:path}"
# catch-all, which would shadow anything mounted after it.
register_website_routes(app)
