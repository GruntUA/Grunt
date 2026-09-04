"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from grunt.api.v1.router import v1_router
from grunt.apps import load_core, load_external_apps
from grunt.config import settings
from grunt.metadata.registry import doctype_registry
from grunt.middleware.language import LanguageMiddleware
from grunt.middleware.logging import RequestLoggingMiddleware
from grunt.middleware.rate_limit import RateLimitMiddleware
from grunt.middleware.security import SecurityHeadersMiddleware
from grunt.site.manager import current_site, site_manager
from grunt.site.middleware import SiteContextMiddleware
from grunt.startup.errors import register_exception_handlers
from grunt.startup.website import register_website_routes
from grunt.tasks.broker import broker
from grunt.tasks.scheduler import start_scheduler, stop_scheduler

# Wire the framework's own hooks/resources ("app zero"). External apps are
# loaded from the lifespan below, once the DB says which are installed.
load_core()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    from grunt.logging_config import configure_logging

    configure_logging(
        bench_dir=site_manager.bench_dir,
        site_names=site_manager.get_sites(),
        log_level=settings.log_level,
        log_to_file=settings.log_to_file,
        debug=settings.debug,
    )

    logger.info("grunt.startup", version="0.1.0")

    from grunt.startup import (
        apply_doctype_overrides,
        load_core_doctypes,
        load_validators,
    )

    load_validators()

    sites = site_manager.get_sites()
    if not sites:
        logger.warning("grunt.startup.no_sites")

    for site in sites:
        token = current_site.set(site)
        try:
            logger.info("grunt.site.startup", site=site)
            # Create all system tables if they don't exist
            eng = site_manager.get_engine(site)
            maker = site_manager.get_session_maker(site)

            # Ensure the full-text search index table exists (DDL, not Alembic)
            from grunt.search.service import search_index_service

            await search_index_service.ensure_table(eng)

            async with maker() as session:
                # Load core DocType definitions into registry (no table sync — use grunt migrate)
                await load_core_doctypes(session)
                # Register names of user-created DocTypes for lazy loading
                await doctype_registry.prefetch_names(session)
                # Merge in-memory field extensions from app hooks (no table sync)
                await apply_doctype_overrides(session, eng)
                await session.commit()

        except Exception as e:
            logger.error("grunt.site.startup_error", site=site, error=str(e))
        finally:
            current_site.reset(token)

    # ── Post-startup: discover resources from installed external apps ──
    # Only apps installed on at least one site are loaded — an app present in
    # apps/ but installed nowhere stays dormant (its hooks, controllers and
    # startup tasks must not act on sites that never opted in).
    await load_external_apps(
        app,
        bench_dir=site_manager.bench_dir,
        installed_apps=site_manager.get_all_installed_apps(),
    )

    # Initialize Sentry (optional)
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.sentry_environment,
                integrations=[FastApiIntegration(), SqlalchemyIntegration()],
                traces_sample_rate=0.1,
            )
            logger.info("sentry.initialized", environment=settings.sentry_environment)
        except ImportError:
            logger.warning("sentry.not_installed", hint="pip install sentry-sdk[fastapi]")

    # Initialize TaskIQ broker
    await broker.startup()

    # Start Scheduler
    await start_scheduler()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    await stop_scheduler()
    await broker.shutdown()

    for eng in site_manager.engines.values():
        await eng.dispose()
    logger.info("grunt.shutdown")


app = FastAPI(
    title="Ґрунт API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
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

# ── Vite Dev Proxy (Development only) ───────────────────────────────────
if settings.debug:
    import httpx
    from fastapi.responses import StreamingResponse

    VITE_SERVER_URL = "http://localhost:5173"

    @app.get("/frontend/{path:path}")
    @app.get("/@vite/{path:path}")
    @app.get("/@id/{path:path}")
    @app.get("/@fs/{path:path}")
    @app.get("/node_modules/{path:path}")
    async def vite_proxy(request: Request):
        path = request.url.path
        query = request.url.query
        target_url = f"{VITE_SERVER_URL}{path}{'?' + query if query else ''}"

        async with httpx.AsyncClient() as client:
            # We skip content-length to let StreamingResponse handle it
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }
            try:
                # Proxy the request to Vite
                v_res = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=await request.body(),
                    follow_redirects=True,
                )
                return StreamingResponse(
                    v_res.aiter_raw(),
                    status_code=v_res.status_code,
                    headers=dict(v_res.headers),
                )
            except Exception as e:
                logger.warning("vite.proxy.error", url=target_url, error=str(e))
                raise HTTPException(status_code=502, detail="Vite server unreachable") from e


app.include_router(v1_router, prefix="/api/v1")

register_exception_handlers(app)

# Must be last: register_website_routes() ends with the "/{path:path}"
# catch-all, which would shadow anything mounted after it.
register_website_routes(app)
