"""ASGI lifespan — everything that happens on server startup and shutdown.

Kept out of :mod:`grunt.main` so the entry point stays a thin assembly of
``FastAPI(...)`` + middleware + route wiring. The startup sequence:

1. configure logging, load validators
2. bring every site up (search index table, DocType *names* only — full
   definitions and schema sync are `grunt db migrate`'s job, not boot's)
3. load external apps installed on at least one site
4. optional Sentry, then the task broker and the scheduler
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from grunt.apps import load_external_apps
from grunt.config import settings
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import current_site, site_manager
from grunt.tasks.broker import broker
from grunt.tasks.scheduler import start_scheduler, stop_scheduler

if TYPE_CHECKING:
    from fastapi import FastAPI


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
    log.info("grunt.startup", version="0.1.0")
    load_validators()


async def _bring_up_sites() -> None:
    sites = site_manager.get_sites()
    if not sites:
        log.warning("grunt.startup.no_sites")

    for site in sites:
        token = current_site.set(site)
        try:
            log.info("grunt.site.startup", site=site)
            eng = site_manager.get_engine(site)
            maker = site_manager.get_session_maker(site)

            # Full-text search index table (DDL, not Alembic).
            from grunt.search.service import search_index_service

            await search_index_service.ensure_table(eng)

            async with maker() as session:
                # Only names — for both core and user-created DocTypes. Full
                # definitions load lazily on first `doctype_registry.get()`.
                # All schema/definition merging (core JSON -> DB) happens
                # exclusively via `grunt db migrate`, never at boot.
                await doctype_registry.prefetch_names(session)
                await session.commit()
        except Exception as e:
            log.error("grunt.site.startup_error", site=site, error=str(e))
        finally:
            current_site.reset(token)


async def _seed_supported_languages() -> None:
    """Widen the i18n language negotiator from active ``geo.Language`` rows.

    Best-effort and union across sites — the accepted-language set is a single
    process-global. ``en``/``uk`` stay supported even if the table is empty or
    absent (fresh install).
    """
    from grunt.app import grunt
    from grunt.i18n import translation_service

    codes: set[str] = set()
    for site in site_manager.get_sites():
        token = current_site.set(site)
        try:
            maker = site_manager.get_session_maker(site)
            async with maker() as session, grunt.context(session):
                rows = await grunt.db.get_all(
                    "Language", filters={"is_active": True}, fields=["code"], limit=None
                )
            codes.update(r["code"] for r in rows if r.get("code"))
        except Exception as e:  # noqa: BLE001 - table may not exist yet
            log.debug("i18n.seed_languages_skipped", site=site, error=str(e))
        finally:
            current_site.reset(token)

    if codes:
        translation_service.set_supported(codes)


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
        log.info("sentry.initialized", environment=settings.sentry_environment)
    except ImportError:
        log.warning("sentry.not_installed", hint="pip install sentry-sdk[fastapi]")


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

    await _seed_supported_languages()
    _init_observability()
    await broker.startup()
    await start_scheduler()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    await stop_scheduler()
    await broker.shutdown()
    from grunt.app import grunt as grunt_app

    await grunt_app.query_cache.aclose()
    for eng in site_manager.engines.values():
        await eng.dispose()
    log.info("grunt.shutdown")
