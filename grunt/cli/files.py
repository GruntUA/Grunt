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


@files_group.command("gc")
@click.option("--site", default=None, help="Site name")
@click.option(
    "--grace", default=3600, show_default=True, help="Keep unreferenced blobs younger than this (s)"
)
def files_gc(site: str | None, grace: int):
    """Delete stored files no File record (nor the trash) refers to."""

    async def _run():
        import grunt
        from grunt.storage.gc import collect_garbage

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            report = await collect_garbage(grace)
        click.echo(
            f"Freed {report['freed_blobs']} file(s), {report['freed_bytes'] / 1048576:.1f} MB; "
            f"abandoned uploads removed: {report['tmp_removed']}"
        )

    asyncio.run(_run())


@files_group.command("verify")
@click.option("--site", default=None, help="Site name")
@click.option("--rehash", is_flag=True, help="Also re-hash every stored file (slow)")
def files_verify(site: str | None, rehash: bool):
    """Check File records against the stored files."""

    async def _run():
        import grunt
        from grunt.storage.gc import verify

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            report = await verify(rehash)
        labels = {
            "missing": "File records without a stored file",
            "unreferenced": "Stored files without a File record (freed by `grunt files gc`)",
            "corrupt": "Stored files whose content no longer matches their hash",
        }
        for kind, label in labels.items():
            items = report[kind]
            click.echo(f"{label}: {len(items)}")
            for item in items[:20]:
                click.echo(f"  {item}")
        if report["missing"] or report["corrupt"]:
            raise SystemExit(1)

    asyncio.run(_run())
