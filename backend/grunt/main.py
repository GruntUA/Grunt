"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from grunt.config import settings
from grunt.api.v1.router import v1_router
from grunt.core.db.base import Base
from grunt.core.metadata.registry import doctype_registry
from grunt.core.document.registry import document_registry
from grunt.core.hooks import register_doc_events
from grunt.core.tasks.broker import broker
from grunt.core.tasks.registry import discover_tasks
from grunt.core.tasks.scheduler import register_scheduler_events, start_scheduler, stop_scheduler
from grunt.core.site.manager import site_manager, current_site
from grunt.core.site.middleware import SiteContextMiddleware


# Ensure all ORM models are imported so Base.metadata is complete
import grunt.core.db.system_tables  # noqa: F401
import grunt.core.auth.models  # noqa: F401

# Phase 3 modules (imported for side-effects: table registration)
# workflow, permissions, reports engines are imported on-demand in endpoints

from grunt.core.middleware.security import SecurityHeadersMiddleware  # noqa: E402

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("grunt.startup", version="0.1.0")

    from grunt.core.startup import populate_system_doctypes, seed_grunt_workspace, seed_app_workspaces, load_core_doctypes  # noqa: PLC0415

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
            
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Ensure shared infrastructure tables (MultiLink junction, etc.)
            from grunt.core.metadata.compiler import SA_METADATA as _sa_meta  # noqa: PLC0415
            async with eng.begin() as conn:
                await conn.run_sync(_sa_meta.create_all)

            async with maker() as session:
                # Load/sync core JSON doctypes FIRST (creates physical tables, populates registry)
                await load_core_doctypes(session, eng)
                # Load user-created doctypes from grunt_meta_doctype
                await doctype_registry.load_all(session)
                # Populate the DocType document table
                await populate_system_doctypes(session, eng)
                await seed_grunt_workspace(session)
                await session.commit()

            # Seed app workspaces (needs registry populated)
            async with maker() as session:
                await seed_app_workspaces(session, site)
                await session.commit()
                
        except Exception as e:
            logger.error("grunt.site.startup_error", site=site, error=str(e))
        finally:
            current_site.reset(token)


    # Load hooks from installed apps
    import importlib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    apps_dir = Path("grunt_apps")
    if apps_dir.exists():
        import sys  # noqa: PLC0415

        # Add project root to sys.path so grunt_apps is importable
        project_root = str(Path.cwd())
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        for app_hooks in apps_dir.glob("*/hooks.py"):
            module_path = str(app_hooks).replace("/", ".").replace("\\", ".").removesuffix(".py")
            try:
                module = importlib.import_module(module_path)
                logger.info("hooks.loaded", module=module_path)
                
                # Register DocType-specific hooks if doc_events is defined
                if hasattr(module, "doc_events"):
                    register_doc_events(getattr(module, "doc_events"))
                    logger.info("hooks.doc_events_registered", module=module_path)

                # Register DocType overrides if override_doctype_class is defined
                if hasattr(module, "override_doctype_class"):
                    document_registry.register_overrides(getattr(module, "override_doctype_class"))
                    logger.info("hooks.overrides_registered", module=module_path)

                # Register Scheduler events if scheduler_events is defined
                if hasattr(module, "scheduler_events"):
                    register_scheduler_events(getattr(module, "scheduler_events"))
                    logger.info("hooks.scheduler_events_registered", module=module_path)
            except Exception as e:
                logger.warning("hooks.load_error", module=module_path, error=str(e))

        # Discover custom DocType controllers
        document_registry.discover_controllers(apps_dir)
        
        # Discover background tasks
        discover_tasks(apps_dir)

        # Discover file-based scripts (client JS + server Python)
        from grunt.core.scripting.file_scripts import discover_file_scripts  # noqa: PLC0415

        discover_file_scripts(apps_dir)

    # Discover resources from installed external apps (bench_dir/apps/*)
    from grunt.core.scripting.file_scripts import discover_file_scripts as _discover_scripts  # noqa: PLC0415

    ext_apps_dir = site_manager.bench_dir / "apps"
    if ext_apps_dir.is_dir():
        # Ensure external apps are importable
        import sys  # noqa: PLC0415
        ext_apps_str = str(ext_apps_dir)
        if ext_apps_str not in sys.path:
            sys.path.insert(0, ext_apps_str)

        for ext_app in sorted(ext_apps_dir.iterdir()):
            if ext_app.is_dir() and ext_app.name not in ("grunt",) and not ext_app.name.startswith((".", "_")):
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
                            register_doc_events(getattr(hooks_mod, "doc_events"))
                        if hasattr(hooks_mod, "override_doctype_class"):
                            document_registry.register_overrides(getattr(hooks_mod, "override_doctype_class"))
                        if hasattr(hooks_mod, "scheduler_events"):
                            register_scheduler_events(getattr(hooks_mod, "scheduler_events"))
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
                            logger.info("app_router.registered", app=ext_app.name, module=module_name)
                    except Exception as e:
                        logger.warning("app_router.load_error", path=import_path, error=str(e))

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
