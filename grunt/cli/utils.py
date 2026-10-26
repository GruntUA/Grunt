from contextlib import asynccontextmanager

import click

lazy from grunt.document.registry import document_registry
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.site.manager import current_site, site_manager


class AliasedGroup(click.Group):
    """A group that also accepts old command names; aliases stay out of --help."""

    def __init__(self, *args, aliases: dict[str, str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases = aliases or {}

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return super().get_command(ctx, self.aliases.get(cmd_name, cmd_name))


def resolve_site(site: str | None) -> str:
    """The given site, else the active one (currentsite.txt), else the first one."""
    if site is not None:
        return site
    try:
        return site_manager.get_active_site()
    except ValueError:
        sites = site_manager.get_sites()
        if not sites:
            click.echo("Error: site not found.", err=True)
            raise SystemExit(1) from None
        return sites[0]


@asynccontextmanager
async def _site_session(site: str | None):
    """Async context manager: initialise site, load DocType registry, yield session."""

    target_site = resolve_site(site)
    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        async with maker() as session:
            # Hydrate every DocType (core + Studio) from the DB - reads
            # only. Re-parsing core JSON is `grunt migrate`'s job, not this.
            await doctype_registry.load_all(session)
            document_registry.index_core_controllers()
            yield session, eng
    finally:
        current_site.reset(token)
