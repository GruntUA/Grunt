"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

import grunt.core.auth.models  # noqa: F401

# Ensure all ORM models are imported so metadata is complete
import grunt.core.db.system_tables  # noqa: F401
import grunt.core.print.hooks  # noqa: F401
from grunt.api.v1.router import v1_router
from grunt.config import settings
from grunt.core.document.registry import document_registry
from grunt.core.hooks import register_doc_events, register_doctype_overrides
from grunt.core.metadata.registry import doctype_registry
from grunt.core.site.manager import current_site, site_manager
from grunt.core.site.middleware import SiteContextMiddleware
from grunt.core.tasks.broker import broker
from grunt.core.tasks.registry import discover_tasks
from grunt.core.tasks.scheduler import register_scheduler_events, start_scheduler, stop_scheduler

document_registry.discover_core_controllers()

# Auto-refresh in-memory permissions when DocTypePermission is saved/deleted
register_doc_events(
    {
        "DocTypePermission": {
            "after_save": ["grunt.core.permissions.sync.sync_permissions"],
            "after_delete": ["grunt.core.permissions.sync.sync_permissions"],
        },
        # Log all document lifecycle events to ActivityLog
        "*": {
            "after_insert": ["grunt.core.activity.log_activity"],
            "after_update": ["grunt.core.activity.log_activity"],
            "after_delete": ["grunt.core.activity.log_activity"],
        },
    }
)

# Register core doctypes dir for lazy client script loading + eager server script loading
from pathlib import Path as _Path  # noqa: E402, I001

from grunt.core.scripting.file_scripts import (  # noqa: E402, I001
    _load_doctype_dir_scripts as _load_dt_scripts,
    register_client_script_dir as _reg_client_dirs,
)

_core_doctypes_dir = _Path(__file__).parent / "core" / "doctypes"
_reg_client_dirs("grunt", _core_doctypes_dir)
for _dt_dir in sorted(_core_doctypes_dir.iterdir()):
    if _dt_dir.is_dir() and not _dt_dir.name.startswith((".", "_")):
        _load_dt_scripts(_dt_dir, "grunt")

# Phase 3 modules (imported for side-effects: table registration)
# workflow, permissions, reports engines are imported on-demand in endpoints

from grunt.core.middleware.language import LanguageMiddleware  # noqa: E402
from grunt.core.middleware.logging import RequestLoggingMiddleware  # noqa: E402
from grunt.core.middleware.security import SecurityHeadersMiddleware  # noqa: E402

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("grunt.startup", version="0.1.0")

    import importlib  # noqa: PLC0415

    from grunt.core.startup import (
        apply_doctype_overrides,
        load_core_doctypes,
        populate_system_doctypes,
        seed_app_workspaces,
        seed_grunt_workspace,
        seed_system_settings,
    )  # noqa: PLC0415

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

            async with maker() as session:
                # Load core DocType definitions into registry (no table sync — use grunt migrate)
                await load_core_doctypes(session)
                # Register names of user-created DocTypes for lazy loading
                await doctype_registry.prefetch_names(session)
                # Merge in-memory field extensions from app hooks (no table sync)
                await apply_doctype_overrides(session, eng)
                # Populate the DocType document table
                await populate_system_doctypes(session, eng)
                await seed_system_settings(session, eng)
                await seed_grunt_workspace(session)
                # Permissions: migrate DocType meta → DocTypePermission, then load into memory
                from grunt.core.permissions.sync import (
                    load_all_permissions_from_db,
                    migrate_doctype_meta_permissions,
                )  # noqa: PLC0415

                await migrate_doctype_meta_permissions(session)
                await session.flush()
                await load_all_permissions_from_db(session)
                await session.commit()

            # Seed app workspaces (needs registry populated)
            async with maker() as session:
                await seed_app_workspaces(session, site)
                await session.commit()

        except Exception as e:
            logger.error("grunt.site.startup_error", site=site, error=str(e))
        finally:
            current_site.reset(token)

    # ── Post-startup: discover resources from installed external apps (bench_dir/apps/*) ──
    from grunt.core.scripting.file_scripts import (
        discover_file_scripts as _discover_scripts,  # noqa: PLC0415
    )

    import sys  # noqa: PLC0415

    ext_apps_dir = site_manager.bench_dir / "apps"
    if ext_apps_dir.is_dir():
        # Ensure external apps are importable
        ext_apps_str = str(ext_apps_dir)
        if ext_apps_str not in sys.path:
            sys.path.insert(0, ext_apps_str)

        for ext_app in sorted(ext_apps_dir.iterdir()):
            if (
                ext_app.is_dir()
                and ext_app.name not in ("grunt",)
                and not ext_app.name.startswith((".", "_"))
            ):
                _discover_scripts(ext_app.parent, app_filter=ext_app.name)
                document_registry.discover_controllers_from_app(ext_app)

                # Load hooks from external app modules: {app}/{module}/hooks.py
                for hooks_file in ext_app.glob("*/hooks.py"):
                    hooks_module_name = hooks_file.parent.name
                    hooks_import = f"{ext_app.name}.{hooks_module_name}.hooks"
                    try:
                        hooks_mod = importlib.import_module(hooks_import)
                        logger.info("hooks.loaded", module=hooks_import)

                        if hasattr(hooks_mod, "doc_events"):
                            register_doc_events(hooks_mod.doc_events)
                        if hasattr(hooks_mod, "override_doctype_class"):
                            document_registry.register_overrides(hooks_mod.override_doctype_class)
                        if hasattr(hooks_mod, "scheduler_events"):
                            register_scheduler_events(hooks_mod.scheduler_events)
                    except Exception as e:
                        logger.warning("hooks.load_error", module=hooks_import, error=str(e))

                # Discover app API routers: {app}/{module}/routes.py → router: APIRouter
                for routes_file in ext_app.glob("*/routes.py"):
                    module_name = routes_file.parent.name
                    import_path = f"{ext_app.name}.{module_name}.routes"
                    try:
                        mod = importlib.import_module(import_path)
                        if hasattr(mod, "router"):
                            app.include_router(
                                mod.router,
                                prefix=f"/api/v1/app/{ext_app.name}",
                            )
                            logger.info(
                                "app_router.registered", app=ext_app.name, module=module_name
                            )
                    except Exception as e:
                        logger.warning("app_router.load_error", path=import_path, error=str(e))

    # Initialize Sentry (optional)
    if settings.sentry_dsn:
        try:
            import sentry_sdk  # noqa: PLC0415
            from sentry_sdk.integrations.fastapi import FastApiIntegration  # noqa: PLC0415
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration  # noqa: PLC0415

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
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SiteContextMiddleware)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: rate limiting via slowapi
try:
    from slowapi import _rate_limit_exceeded_handler  # noqa: PLC0415
    from slowapi.errors import RateLimitExceeded  # noqa: PLC0415

    from grunt.core.middleware.rate_limit import limiter  # noqa: PLC0415

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    pass  # slowapi not installed — rate limiting disabled

app.include_router(v1_router, prefix="/api/v1")


# ── Exception handlers ───────────────────────────────────────────────────


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Помилка валідації",
                "details": [str(e["msg"]) for e in exc.errors()],
            },
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": detail,
                "details": exc.detail if isinstance(exc.detail, list) else [],
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error=str(exc))
    details = [str(exc)] if settings.debug else []
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутрішня помилка сервера",
                "details": details,
            },
        },
    )
