"""FastAPI application entry point."""

from contextlib import asynccontextmanager

# Register core doctypes dir for lazy client script loading + eager server script loading
from pathlib import Path as _Path

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

# Ensure all ORM models are imported so metadata is complete
from grunt.api.messages import ApplicationError
from grunt.api.v1.router import v1_router
from grunt.config import settings
from grunt.document.registry import document_registry
from grunt.errors import GruntError, error_body
from grunt.hooks import register_doc_events

# Register built-in io exporters / importers
from grunt.io import register_exporter, register_importer
from grunt.io.exporters.csv import CsvExporter
from grunt.io.exporters.xlsx import XlsxExporter
from grunt.io.importers.csv import CsvImporter
from grunt.io.importers.xlsx import XlsxImporter
from grunt.metadata.registry import doctype_registry
from grunt.middleware.language import LanguageMiddleware
from grunt.middleware.logging import RequestLoggingMiddleware
from grunt.middleware.rate_limit import RateLimitMiddleware
from grunt.middleware.security import SecurityHeadersMiddleware
from grunt.scripting.file_scripts import (
    _load_doctype_dir_scripts as _load_dt_scripts,
)
from grunt.scripting.file_scripts import (
    register_client_script_dir as _reg_client_dirs,
)
from grunt.site.manager import current_site, site_manager
from grunt.site.middleware import SiteContextMiddleware
from grunt.startup.doctypes import _find_doctype_dirs as _grunt_doctype_dirs
from grunt.tasks.broker import broker
from grunt.tasks.scheduler import register_scheduler_events, start_scheduler, stop_scheduler
from grunt.website import make_website_handler, robots_txt, sitemap_xml, website_registry

document_registry.index_core_controllers()
register_exporter(XlsxExporter())
register_exporter(CsvExporter())
register_importer(CsvImporter())
register_importer(XlsxImporter())

# Auto-refresh in-memory permissions when DocTypePermission is saved/deleted
register_doc_events(
    {
        "DocTypePermission": {
            "after_save": ["grunt.permissions.sync.sync_permissions"],
            "after_delete": ["grunt.permissions.sync.sync_permissions"],
        },
        # Never hand a stored SMTP password back to a non-superadmin reader.
        "EmailAccount": {
            "after_read": ["grunt.email.hooks.mask_smtp_password"],
        },
        # Log all document lifecycle events to ActivityLog
        "*": {
            "after_insert": ["grunt.activity.log_activity"],
            "after_delete": ["grunt.activity.log_activity"],
        },
    }
)


for _doctypes_dir in _grunt_doctype_dirs():
    _reg_client_dirs("grunt", _doctypes_dir)
    for _dt_dir in sorted(_doctypes_dir.iterdir()):
        if _dt_dir.is_dir() and not _dt_dir.name.startswith((".", "_")):
            _load_dt_scripts(_dt_dir, "grunt")

# Phase 3 modules (imported for side-effects: table registration)
# workflow, permissions, reports engines are imported on-demand in endpoints


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

    import importlib

    from grunt.startup import (
        apply_doctype_overrides,
        load_core_doctypes,
        load_validators,
    )

    load_validators()

    from grunt.website import make_website_handler, website_registry

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
                # Permissions: migrate DocType meta → DocTypePermission, then load into memory
                from grunt.permissions.sync import (
                    load_all_permissions_from_db,
                    migrate_doctype_meta_permissions,
                )

                await migrate_doctype_meta_permissions(session)
                await session.flush()
                await load_all_permissions_from_db(session)
                await session.commit()

        except Exception as e:
            logger.error("grunt.site.startup_error", site=site, error=str(e))
        finally:
            current_site.reset(token)

    # ── Post-startup: discover resources from installed external apps (bench_dir/apps/*) ──
    import sys

    from grunt.scripting.file_scripts import (
        discover_file_scripts as _discover_scripts,
    )

    ext_apps_dir = site_manager.bench_dir / "apps"
    if ext_apps_dir.is_dir():
        # Ensure external apps are importable
        ext_apps_str = str(ext_apps_dir)
        if ext_apps_str not in sys.path:
            sys.path.insert(0, ext_apps_str)

        # Only load code from apps that are installed on at least one site. An
        # app present in apps/ but not installed anywhere must stay dormant —
        # its hooks, controllers and startup tasks must not run (they would act
        # on sites that never opted in, a source of noise, bugs and security
        # exposure).
        installed_apps = site_manager.get_all_installed_apps()

        for ext_app in sorted(ext_apps_dir.iterdir()):
            if (
                ext_app.is_dir()
                and ext_app.name not in ("grunt",)
                and ext_app.name in installed_apps
                and not ext_app.name.startswith((".", "_"))
            ):
                # Also add the app directory itself so that `import {app}` resolves
                # the inner Python package (apps/{app}/{app}/) rather than treating
                # apps/{app}/ as a namespace package. This allows `car_ua.services.*`
                # to work instead of requiring `car_ua.car_ua.services.*`.
                ext_app_str = str(ext_app)
                if ext_app_str not in sys.path:
                    sys.path.insert(0, ext_app_str)

                _discover_scripts(ext_app.parent, app_filter=ext_app.name)
                document_registry.index_external_app_controllers(ext_app)

                # Load hooks from external app modules: {app}/{module}/hooks.py
                for hooks_file in ext_app.glob("*/hooks.py"):
                    hooks_module_name = hooks_file.parent.name
                    # Same-name layout (apps/car_ua/car_ua/hooks.py): app dir is on
                    # sys.path so importable prefix is just the module name.
                    if hooks_module_name == ext_app.name:
                        hooks_import = f"{hooks_module_name}.hooks"
                    else:
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
                        if hasattr(hooks_mod, "on_startup"):
                            for startup_fn_path in hooks_mod.on_startup:
                                try:
                                    mod_path, fn_name = startup_fn_path.rsplit(".", 1)
                                    startup_mod = importlib.import_module(mod_path)
                                    fn = getattr(startup_mod, fn_name)
                                    await fn()
                                    logger.info("hooks.on_startup.called", handler=startup_fn_path)
                                except Exception as e:
                                    logger.warning(
                                        "hooks.on_startup.error",
                                        handler=startup_fn_path,
                                        error=str(e),
                                    )
                        if hasattr(hooks_mod, "io_exporters"):
                            from grunt.io import register_exporter as _reg_exp

                            for _exp in hooks_mod.io_exporters:
                                _reg_exp(_exp)
                                logger.info("io.exporter.registered", id=_exp.id, app=ext_app.name)
                        if hasattr(hooks_mod, "io_importers"):
                            from grunt.io import register_importer as _reg_imp

                            for _imp in hooks_mod.io_importers:
                                _reg_imp(_imp)
                                logger.info("io.importer.registered", id=_imp.id, app=ext_app.name)
                        if hasattr(hooks_mod, "website_block_types"):
                            from grunt.website.block_types import register_block_type

                            website_registry.add_template_source("grunt", ext_app / "www")
                            for _bt in hooks_mod.website_block_types:
                                register_block_type(_bt["name"], _bt["template"], _bt.get("fields"))
                                logger.info(
                                    "website.block_type.registered",
                                    name=_bt["name"],
                                    app=ext_app.name,
                                )
                        if hasattr(hooks_mod, "tree_title_resolvers"):
                            from grunt.document.tree import register_tree_title_resolver

                            for _dt_name, _resolver_path in hooks_mod.tree_title_resolvers.items():
                                try:
                                    _mod_path, _fn_name = _resolver_path.rsplit(".", 1)
                                    _resolver_mod = importlib.import_module(_mod_path)
                                    register_tree_title_resolver(
                                        _dt_name, getattr(_resolver_mod, _fn_name)
                                    )
                                    logger.info(
                                        "tree.title_resolver.registered",
                                        doctype=_dt_name,
                                        app=ext_app.name,
                                    )
                                except Exception as e:
                                    logger.warning(
                                        "tree.title_resolver.error",
                                        doctype=_dt_name,
                                        handler=_resolver_path,
                                        error=str(e),
                                    )
                    except Exception as e:
                        logger.warning("hooks.load_error", module=hooks_import, error=str(e))

                # Discover app API routers: {app}/{module}/routes.py → router: APIRouter
                for routes_file in ext_app.glob("*/routes.py"):
                    module_name = routes_file.parent.name
                    if module_name == ext_app.name:
                        import_path = f"{module_name}.routes"
                    else:
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

                # Mount app/public/ as static files at /assets/{app}/
                public_dir = ext_app / "public"
                if public_dir.is_dir():
                    from fastapi.staticfiles import StaticFiles

                    app.mount(
                        f"/assets/{ext_app.name}",
                        StaticFiles(directory=str(public_dir)),
                        name=f"assets_{ext_app.name}",
                    )
                    logger.info("www.assets.mounted", app=ext_app.name)

                # 2. Discover external app pages
                for page in website_registry.discover_app(ext_app, ext_app.name):
                    app.add_api_route(
                        page.url_pattern,
                        make_website_handler(page),
                        methods=["GET", "POST"],
                        include_in_schema=False,
                        tags=["www"],
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

# ── Register Core Website Pages (mounted at root) ──


core_website_dir = _Path(__file__).parent / "website"
for page in website_registry.discover_app(core_website_dir, "grunt", is_main_app=True):
    app.add_api_route(
        page.url_pattern,
        make_website_handler(page),
        methods=["GET", "POST"],
        include_in_schema=False,
        tags=["website"],
    )

app.add_api_route(
    "/sitemap.xml", sitemap_xml, methods=["GET"], include_in_schema=False, tags=["website"]
)
app.add_api_route(
    "/robots.txt", robots_txt, methods=["GET"], include_in_schema=False, tags=["website"]
)

# ── Static Assets ──
main_public_dir = _Path(__file__).parent.parent / "public"
if main_public_dir.is_dir():
    app.mount("/assets/grunt", StaticFiles(directory=str(main_public_dir)), name="assets_grunt")
# NOTE: Do NOT mount StaticFiles at "/" — it would intercept all paths
# (including SPA routes like /403) and return its own 404 before our
# website_catch_all ever runs.  Root-level static files are served
# inside website_catch_all below.


# ── Exception handlers ───────────────────────────────────────────────────


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR",
            "Помилка валідації",
            [str(e["msg"]) for e in exc.errors()],
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # APIError carries a semantic code + details; plain HTTPException falls back
    # to HTTP_<status> with any list detail surfaced as details.
    code = getattr(exc, "code", None) or f"HTTP_{exc.status_code}"
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    details = getattr(exc, "details", None)
    if details is None:
        details = exc.detail if isinstance(exc.detail, list) else []
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, details),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(GruntError)
async def grunt_error_handler(request: Request, exc: GruntError) -> JSONResponse:
    """Map GruntError to appropriate HTTP status codes based on title."""
    status_map = {
        "PERMISSION_DENIED": 403,
        "NOT_FOUND": 404,
        "CONFLICT": 409,
        "VALIDATION_ERROR": 422,
    }
    status_code = status_map.get(exc.title or "APPLICATION_ERROR", 422)
    return JSONResponse(
        status_code=status_code,
        content=error_body(exc.title or "APPLICATION_ERROR", str(exc)),
    )


@app.exception_handler(ApplicationError)
async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
    """Map ApplicationError to appropriate HTTP status codes based on code."""
    status_map = {
        "PERMISSION_DENIED": 403,
        "NOT_FOUND": 404,
        "CONFLICT": 409,
        "DUPLICATE_DATA": 409,
        "VALIDATION_ERROR": 422,
    }
    status_code = status_map.get(exc.code, 422)
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import traceback as _tb

    logger.exception("unhandled_error", error=str(exc))

    if not settings.debug:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Внутрішня помилка сервера",
                },
            },
        )

    # Debug mode: return rich error info
    exc_type = type(exc).__name__
    exc_tb = _tb.format_exc()

    debug_info: dict = {
        "exc_type": exc_type,
        "message": str(exc),
        "traceback": exc_tb,
    }

    # Extract SQL details from SQLAlchemy errors
    try:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            stmt = getattr(exc, "statement", None)
            params = getattr(exc, "params", None)
            orig = getattr(exc, "orig", None)
            if stmt:
                debug_info["sql"] = str(stmt)
            if params:
                debug_info["sql_params"] = str(params)
            if orig:
                debug_info["db_error"] = str(orig)
    except Exception:
        logger.exception("suppressed_error")

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутрішня помилка сервера",
                "debug": debug_info,
            },
        },
    )


# ── Catch-all Website Handler (Dynamic DB Pages) ────────────────────────
@app.get("/{path:path}", include_in_schema=False)
async def website_catch_all(request: Request):
    # 1. Serve root-level static files (replaces StaticFiles mount at "/")
    from fastapi.responses import FileResponse

    from grunt.config import settings
    from grunt.site.manager import site_manager
    from grunt.website.router import render_page_by_route

    req_path = request.url.path.lstrip("/")
    if req_path:  # ignore "/" itself
        candidate = main_public_dir / req_path
        if candidate.is_file():
            return FileResponse(str(candidate))

    # 2. Try server-side website pages
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)

    async with maker() as session:
        response = await render_page_by_route(request, session)
        if response:
            return response

    # 3. No server-side page found — fall back to SPA so vue-router handles
    #    the path (covers /403, /app/*, and any other frontend routes).
    from fastapi.responses import HTMLResponse

    from grunt.website import website_registry

    env = website_registry.get_env("grunt")
    if env is not None:
        try:
            template = env.get_template("_spa.html")
            html = await template.render_async(
                request=request, title="Ґрунт", dev_mode=settings.debug
            )
            return HTMLResponse(content=html)
        except Exception as _exc:
            logger.warning("website.spa_fallback.error", path=request.url.path, error=str(_exc))

    raise HTTPException(status_code=404, detail="Сторінку не знайдено")
