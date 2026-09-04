"""ASGI lifespan — everything that happens on server startup and shutdown.

Kept out of :mod:`grunt.main` so the entry point stays a thin assembly of
``FastAPI(...)`` + middleware + route wiring. The startup sequence:

1. configure logging, load validators
2. bring every site up (system tables, core DocTypes, field overrides)
3. load external apps installed on at least one site
4. optional Sentry, then the task broker and the scheduler
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

from grunt.apps import load_external_apps
from grunt.config import settings
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import current_site, site_manager
from grunt.tasks.broker import broker
from grunt.tasks.scheduler import start_scheduler, stop_scheduler

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()


def _configure() -> None:
    from grunt.logging_config import configure_logging
    from grunt.startup import load_validators

    configure_logging(
        bench_dir=site_manager.bench_dir,
        site_names=site_manager.get_sites(),
        log_level=settings.log_level,
        log_to_file=settings.log_to_file,
        debug=settings.debug,
    )
    logger.info("grunt.startup", version="0.1.0")
    load_validators()


async def _bring_up_sites() -> None:
    from grunt.startup import apply_doctype_overrides, load_core_doctypes

    sites = site_manager.get_sites()
    if not sites:
        logger.warning("grunt.startup.no_sites")

    for site in sites:
        token = current_site.set(site)
        try:
            logger.info("grunt.site.startup", site=site)
            eng = site_manager.get_engine(site)
            maker = site_manager.get_session_maker(site)

            # Full-text search index table (DDL, not Alembic).
            from grunt.search.service import search_index_service

            await search_index_service.ensure_table(eng)

            async with maker() as session:
                # Core DocType definitions into the registry — no table sync
                # (that is `grunt migrate`).
                await load_core_doctypes(session)
                # Names of user-created DocTypes, for lazy loading.
                await doctype_registry.prefetch_names(session)
                # In-memory field extensions from app hooks — no table sync.
                await apply_doctype_overrides(session, eng)
                await session.commit()
        except Exception as e:
            logger.error("grunt.site.startup_error", site=site, error=str(e))
        finally:
            current_site.reset(token)


def _init_observability() -> None:
    if not settings.sentry_dsn:
        return
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    _configure()
    await _bring_up_sites()

    # Only apps installed on at least one site are loaded — an app present in
    # apps/ but installed nowhere stays dormant (its hooks, controllers and
    # startup tasks must not act on sites that never opted in).
    await load_external_apps(
        app,
        bench_dir=site_manager.bench_dir,
        installed_apps=site_manager.get_all_installed_apps(),
    )

    _init_observability()
    await broker.startup()
    await start_scheduler()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    await stop_scheduler()
    await broker.shutdown()
    for eng in site_manager.engines.values():
        await eng.dispose()
    logger.info("grunt.shutdown")
