from __future__ import annotations

from contextlib import asynccontextmanager

import click


@asynccontextmanager
async def _site_session(site: str | None):
    """Async context manager: initialise site, load DocType registry, yield session."""
    from grunt.document.registry import document_registry
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import current_site, site_manager

    _sites = site_manager.get_sites()
    target_site: str | None = site
    if target_site is None:
        # The active site (currentsite.txt), not just whichever directory lists first.
        try:
            target_site = site_manager.get_active_site()
        except ValueError:
            target_site = _sites[0] if _sites else None
    if target_site is None:
        click.echo("Error: site not found.", err=True)
        raise SystemExit(1)

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        async with maker() as session:
            # Hydrate every DocType (core + Studio) from the DB — reads
            # only. Re-parsing core JSON is `grunt db migrate`'s job, not this.
            await doctype_registry.load_all(session)
            document_registry.index_core_controllers()
            yield session, eng
    finally:
        current_site.reset(token)
