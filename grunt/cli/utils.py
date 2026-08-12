from __future__ import annotations

from contextlib import asynccontextmanager

import click


@asynccontextmanager
async def _site_session(site: str | None):
    """Async context manager: initialise site, load DocType registry, yield session."""
    from grunt.document.registry import document_registry
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import current_site, site_manager
    from grunt.startup import load_core_doctypes

    _sites = site_manager.get_sites()
    target_site: str | None = site or (_sites[0] if _sites else None)
    if target_site is None:
        click.echo("Помилка: сайт не знайдено.", err=True)
        raise SystemExit(1)

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        async with maker() as session:
            await doctype_registry.load_all(session)
            await load_core_doctypes(session, eng)
            document_registry.index_core_controllers()
            yield session, eng
    finally:
        current_site.reset(token)
