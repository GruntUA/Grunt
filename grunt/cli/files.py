import asyncio

import click

from grunt.cli.utils import _site_session


@click.group("files")
def files_group():
    """Files: storage maintenance."""
    pass


@files_group.command("thumbnails")
@click.option("--site", default=None, help="Site name")
@click.option("--limit", default=500, show_default=True, help="Maximum thumbnails per run")
def files_thumbnails(site: str | None, limit: int):
    """Create thumbnails (images, PDF) for files uploaded without them."""

    async def _run():
        import grunt
        from grunt.storage.doctypes.File.file import generate_missing_thumbnails

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            made = await generate_missing_thumbnails(limit)
            await session.commit()
        click.echo(f"Thumbnails created: {made}")

    asyncio.run(_run())
