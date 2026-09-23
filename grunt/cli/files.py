import asyncio

import click

from grunt.cli.utils import _site_session


@click.group("files")
def files_group():
    """Файли: обслуговування сховища."""
    pass


@files_group.command("thumbnails")
@click.option("--site", default=None, help="Назва сайту")
@click.option("--limit", default=500, show_default=True, help="Максимум мініатюр за запуск")
def files_thumbnails(site: str | None, limit: int):
    """Створити мініатюри (картинки, PDF) для файлів, завантажених без них."""

    async def _run():
        from grunt.app import grunt
        from grunt.storage.doctypes.File.file import generate_missing_thumbnails

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            made = await generate_missing_thumbnails(limit)
            await session.commit()
        click.echo(f"Створено мініатюр: {made}")

    asyncio.run(_run())
