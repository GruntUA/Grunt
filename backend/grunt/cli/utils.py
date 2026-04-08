from __future__ import annotations

from contextlib import asynccontextmanager

import click


@asynccontextmanager
async def _site_session(site: str | None):
    """Async context manager: initialise site, load DocType registry, yield session."""
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.site.manager import current_site, site_manager  # noqa: PLC0415
    from grunt.core.startup import load_core_doctypes  # noqa: PLC0415

    target_site = site or (site_manager.get_sites() or [None])[0]
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
            yield session, eng
    finally:
        current_site.reset(token)
