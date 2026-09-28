"""App loader — discover installed apps and wire their resources into the
running framework.

Two entry points:

* :func:`load_core` — the framework's own resources ("app zero"): core
  controller index, built-in importers/exporters, per-DocType client scripts,
  and :mod:`grunt.core_hooks`. Called once at :mod:`grunt.main` import.
* :func:`load_external_apps` — every app under ``bench/apps/*`` that is
  installed on at least one site. Called from the ASGI lifespan (it needs the
  DB — to know which apps are installed — and the ``FastAPI`` instance — to
  mount routers, static files and pages).

Both funnel each app's ``hooks.py`` through :data:`HOOK_CONSUMERS`
(:mod:`grunt.apps.consumers`), so recognising a new hook key is a one-line
consumer registration, not a change here.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext, _resolve
from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from fastapi import FastAPI


CORE_APP = "grunt"
_GRUNT_PKG = Path(__file__).resolve().parent.parent  # grunt/apps/loader.py -> grunt/

# Name of the app whose www/ pages mount at the site root (set by the first
# loaded app whose hooks.py declares `is_primary_web_app = True`) instead of
# under `/{app_name}/...`. See `load_app`.
_primary_web_app: str | None = None


def primary_web_app() -> str | None:
    """Name of the app whose www/ pages are mounted at the site root, if any."""
    return _primary_web_app


# ─────────────────────────────────────────────────────────────────────────────
# App zero
# ─────────────────────────────────────────────────────────────────────────────


def load_core(fastapi_app: FastAPI | None = None) -> None:
    """Wire the framework's own hooks and resources.

    Synchronous by design: it runs at :mod:`grunt.main` import time (before
    any event loop), and every core consumer is synchronous. ``core_hooks``
    must not grow an ``on_startup`` — that belongs in the lifespan.
    """
    from grunt.document.registry import document_registry

    document_registry.index_core_controllers()

    from grunt.io import register_exporter, register_importer
    from grunt.io.exporters.csv import CsvExporter
    from grunt.io.exporters.xlsx import XlsxExporter
    from grunt.io.importers.csv import CsvImporter
    from grunt.io.importers.xlsx import XlsxImporter

    register_exporter(XlsxExporter())
    register_exporter(CsvExporter())
    register_importer(CsvImporter())
    register_importer(XlsxImporter())

    _load_core_client_scripts()

    from grunt import core_hooks

    ctx = LoadContext(app_name=CORE_APP, app_dir=_GRUNT_PKG, fastapi_app=fastapi_app)
    _apply_hooks_module(core_hooks, ctx)


def _load_core_client_scripts() -> None:
    from grunt.scripting.file_scripts import (
        _load_doctype_dir_scripts,
        register_client_script_dir,
    )
    from grunt.startup.doctypes import _find_doctype_dirs

    for doctypes_dir in _find_doctype_dirs():
        register_client_script_dir(CORE_APP, doctypes_dir)
        for dt_dir in sorted(doctypes_dir.iterdir()):
            if dt_dir.is_dir() and not dt_dir.name.startswith((".", "_")):
                _load_doctype_dir_scripts(dt_dir, CORE_APP)


# ─────────────────────────────────────────────────────────────────────────────
# External apps
# ─────────────────────────────────────────────────────────────────────────────


async def load_external_apps(
    fastapi_app: FastAPI | None,
    *,
    bench_dir: Path,
    installed_apps: set[str],
) -> None:
    """Load every app under ``bench_dir/apps`` that is installed somewhere.

    An app present on disk but installed on no site stays dormant — its hooks,
    controllers and startup tasks must not run (they would act on sites that
    never opted in).
    """
    ext_apps_dir = bench_dir / "apps"
    if not ext_apps_dir.is_dir():
        return

    _ensure_on_syspath(ext_apps_dir)

    for app_dir in sorted(ext_apps_dir.iterdir()):
        if not _is_loadable_app(app_dir, installed_apps):
            continue
        # Put the app dir itself on sys.path so `import {app}` resolves the
        # inner package (apps/{app}/{app}/) rather than treating apps/{app}/
        # as a namespace package.
        _ensure_on_syspath(app_dir)
        await load_app(fastapi_app, app_dir)


def _is_loadable_app(app_dir: Path, installed_apps: set[str]) -> bool:
    return (
        app_dir.is_dir()
        and app_dir.name != CORE_APP
        and app_dir.name in installed_apps
        and not app_dir.name.startswith((".", "_"))
    )


async def load_app(fastapi_app: FastAPI | None, app_dir: Path) -> None:
    """Load one app directory: file scripts, controllers, hooks, routers,
    static assets and pages."""
    global _primary_web_app

    ctx = LoadContext(app_name=app_dir.name, app_dir=app_dir, fastapi_app=fastapi_app)

    from grunt.document.registry import document_registry
    from grunt.scripting.file_scripts import discover_file_scripts as _discover_scripts

    _discover_scripts(app_dir.parent, app_filter=ctx.app_name)
    document_registry.index_external_app_controllers(app_dir)

    wants_root = False
    for hooks_mod in _iter_hooks_modules(app_dir):
        _apply_hooks_module(hooks_mod, ctx)
        await _run_on_startup(hooks_mod, ctx)
        if getattr(hooks_mod, "is_primary_web_app", False):
            wants_root = True

    is_main_app = False
    if wants_root:
        if _primary_web_app is None:
            _primary_web_app = ctx.app_name
            is_main_app = True
        elif _primary_web_app == ctx.app_name:
            is_main_app = True
        else:
            log.warning("apps.primary_web_app.conflict", app=ctx.app_name, holder=_primary_web_app)

    _include_app_routers(ctx)
    _mount_app_static(ctx)
    _register_app_pages(ctx, is_main_app=is_main_app)


async def reload_app(app_name: str, fastapi_app: FastAPI | None = None) -> None:
    """Dev helper: re-import an app's ``hooks.py`` modules and re-run consumers.

    Handlers that append to registries may double-register; most framework
    registries de-dupe by name/fieldname, but treat this as a convenience for
    iterating on hooks, not a replacement for a restart.
    """
    from grunt.site.manager import site_manager

    app_dir = site_manager.bench_dir / "apps" / app_name
    if not app_dir.is_dir():
        log.warning("apps.reload.not_found", app=app_name)
        return

    ctx = LoadContext(app_name=app_name, app_dir=app_dir, fastapi_app=fastapi_app)
    for hooks_mod in _iter_hooks_modules(app_dir):
        reloaded = importlib.reload(sys.modules[hooks_mod.__name__])
        _apply_hooks_module(reloaded, ctx)
        await _run_on_startup(reloaded, ctx)
        log.info("apps.reloaded", module=reloaded.__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_on_syspath(path: Path) -> None:
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _hooks_import_path(app_name: str, module_name: str) -> str:
    # Same-name layout (apps/car_ua/car_ua/hooks.py): the app dir is on
    # sys.path, so the importable prefix is just the module name.
    if module_name == app_name:
        return f"{module_name}.hooks"
    return f"{app_name}.{module_name}.hooks"


def _iter_hooks_modules(app_dir: Path) -> Iterator[ModuleType]:
    for hooks_file in app_dir.glob("*/hooks.py"):
        import_path = _hooks_import_path(app_dir.name, hooks_file.parent.name)
        try:
            mod = importlib.import_module(import_path)
        except Exception as e:  # noqa: BLE001 - one bad app must not break the rest
            log.warning("hooks.load_error", module=import_path, error=str(e))
            continue
        log.info("hooks.loaded", module=import_path)
        yield mod


def _apply_hooks_module(mod: object, ctx: LoadContext) -> None:
    """Run every registered consumer whose key the module defines.

    All consumers are synchronous (registry mutations). Anything that needs
    to *await* at load time is a discrete step — see :func:`_run_on_startup`.
    """
    for key, hook_consumer in HOOK_CONSUMERS.items():
        if not hasattr(mod, key):
            continue
        try:
            hook_consumer.apply(getattr(mod, key), ctx)
        except Exception:
            log.exception("apps.consumer_error", app=ctx.app_name, hook_key=key)


async def _run_on_startup(mod: object, ctx: LoadContext) -> None:
    """Await each ``on_startup`` handler an app declares — best-effort, isolated."""
    for path in getattr(mod, "on_startup", ()):
        try:
            result = _resolve(path)()
            if inspect.isawaitable(result):
                await result
            log.info("apps.on_startup.called", app=ctx.app_name, handler=path)
        except Exception as e:  # noqa: BLE001 - one bad handler must not stop the rest
            log.warning("apps.on_startup.error", app=ctx.app_name, handler=path, error=str(e))


def _include_app_routers(ctx: LoadContext) -> None:
    if ctx.fastapi_app is None:
        return
    for routes_file in ctx.app_dir.glob("*/routes.py"):
        module_name = routes_file.parent.name
        import_path = (
            f"{module_name}.routes"
            if module_name == ctx.app_name
            else f"{ctx.app_name}.{module_name}.routes"
        )
        try:
            mod = importlib.import_module(import_path)
        except Exception as e:  # noqa: BLE001
            log.warning("app_router.load_error", path=import_path, error=str(e))
            continue
        if hasattr(mod, "router"):
            ctx.fastapi_app.include_router(mod.router, prefix=f"/api/v1/app/{ctx.app_name}")
            log.info("app_router.registered", app=ctx.app_name, module=module_name)


def _mount_app_static(ctx: LoadContext) -> None:
    if ctx.fastapi_app is None:
        return
    public_dir = ctx.app_dir / "public"
    if not public_dir.is_dir():
        return
    from fastapi.staticfiles import StaticFiles

    ctx.fastapi_app.mount(
        f"/assets/{ctx.app_name}",
        StaticFiles(directory=str(public_dir)),
        name=f"assets_{ctx.app_name}",
    )
    _move_before_catch_all(ctx.fastapi_app)
    log.info("www.assets.mounted", app=ctx.app_name)


def _move_before_catch_all(fastapi_app: FastAPI) -> None:
    """Re-slot the route just added so it precedes the website catch-all.

    External apps load at lifespan startup, after grunt.startup.website has
    already registered ``/{path:path}`` — appended routes would sit behind it
    and never match (static files came back as the SPA shell; pages were only
    reached via the catch-all's own non-committing session).
    """
    routes = fastapi_app.router.routes
    catch_all = next(
        (i for i, r in enumerate(routes) if getattr(r, "path", None) == "/{path:path}"), None
    )
    if catch_all is not None and catch_all < len(routes) - 1:
        routes.insert(catch_all, routes.pop())


def _register_app_pages(ctx: LoadContext, *, is_main_app: bool = False) -> None:
    if ctx.fastapi_app is None:
        return
    from grunt.website import make_website_handler, website_registry

    for page in website_registry.discover_app(ctx.app_dir, ctx.app_name, is_main_app=is_main_app):
        ctx.fastapi_app.add_api_route(
            page.url_pattern,
            make_website_handler(page),
            methods=["GET", "POST"],
            include_in_schema=False,
            tags=["www"],
        )
        _move_before_catch_all(ctx.fastapi_app)
