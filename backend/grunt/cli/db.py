import asyncio
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import click


@click.group("db")
def db_group():
    """Команди управління базою даних."""
    pass


@db_group.command("migrate")
@click.option("--dry-run", is_flag=True, help="Показати SQL без виконання (для DocType таблиць)")
@click.option("--site", default=None, help="Назва сайту")
def db_migrate(dry_run: bool, site: str | None) -> None:
    """Синхронізувати схему БД: system tables (Alembic) + DocType tables (sync_table).

    Запускати після:
    - Оновлення фреймворку (нові core DocTypes або зміни полів)
    - Додавання нових DocTypes через Studio
    - Встановлення нових додатків із DocTypes
    """
    import asyncio  # noqa: PLC0415

    async def _run() -> None:
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.db.base import Base  # noqa: PLC0415
        from grunt.core.db.system_tables import GruntMetaDoctype  # noqa: PLC0415
        from grunt.core.metadata.compiler import SA_METADATA, sync_table  # noqa: PLC0415
        from grunt.core.metadata.doctype import DocType  # noqa: PLC0415
        from grunt.core.site.manager import site_manager  # noqa: PLC0415
        from grunt.core.startup import load_core_doctypes  # noqa: PLC0415

        sites = [site] if site else site_manager.get_sites()
        if not sites:
            click.echo("Жодного сайту не знайдено.", err=True)
            raise SystemExit(1)

        for site_name in sites:
            click.echo(f"\n── Сайт: {site_name} ──")
            eng = site_manager.get_engine(site_name)
            maker = site_manager.get_session_maker(site_name)

            # 1. System ORM tables
            click.echo("  [1/3] System tables (Base.metadata)...")
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 2. Shared infrastructure tables (MultiLink junction, etc.)
            click.echo("  [2/3] Infrastructure tables (SA_METADATA)...")
            async with eng.begin() as conn:
                await conn.run_sync(SA_METADATA.create_all)

            # 3. DocType tables
            click.echo("  [3/3] DocType tables (sync_table)...")
            async with maker() as session:
                # Load core doctype definitions into registry
                await load_core_doctypes(session)
                # Load user-created doctype definitions
                result = await session.execute(select(GruntMetaDoctype))
                rows = result.scalars().all()

                synced = 0
                skipped = 0
                for row in rows:
                    try:
                        dt = DocType.model_validate(row.data)
                        if dt.is_virtual:
                            skipped += 1
                            continue
                        if dry_run:
                            click.echo(f"    [dry-run] would sync: {dt.name}")
                        else:
                            await sync_table(dt, eng, session=session)
                            click.echo(f"    synced: {dt.name}")
                        synced += 1
                    except Exception as e:  # noqa: BLE001
                        click.echo(f"    [error] {row.name}: {e}", err=True)

                await session.commit()

            click.echo(
                f"  Done: {synced} synced, {skipped} skipped (virtual)."
            )

    asyncio.run(_run())
    click.echo("\nМіграцію завершено.")


@db_group.command("backup")
@click.option(
    "--output",
    "-o",
    default=None,
    help="Файл для резервної копії (за замовчуванням: grunt_backup_<timestamp>.sql)",
)
@click.option("--site", default=None, help="Назва сайту")
def db_backup(output, site):
    """Створити резервну копію бази даних (pg_dump або sqlite3)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"grunt_backup_{timestamp}.sql"
    out_path = output or default_name

    async def _run():
        from grunt.config import settings  # noqa: PLC0415

        db_url: str = settings.database_url

        if db_url.startswith("postgresql"):
            if shutil.which("pg_dump") is None:
                click.echo("Помилка: pg_dump не знайдено.", err=True)
                raise SystemExit(1)
            # Extract connection params from URL
            result = subprocess.run(
                ["pg_dump", db_url, "--file", out_path],
                capture_output=False,
            )
            if result.returncode == 0:
                click.echo(f"Резервна копія збережена: {out_path}")
            raise SystemExit(result.returncode)

        elif db_url.startswith("sqlite"):
            # sqlite:///path/to/db.sqlite3
            db_file = db_url.replace("sqlite:///", "").replace("sqlite://", "")
            if not Path(db_file).exists():
                click.echo(f"Помилка: файл БД не знайдено: {db_file}", err=True)
                raise SystemExit(1)
            if shutil.which("sqlite3") is not None:
                result = subprocess.run(
                    ["sqlite3", db_file, f".output {out_path}", ".dump", ".quit"],
                    capture_output=False,
                )
                if result.returncode == 0:
                    click.echo(f"Резервна копія збережена: {out_path}")
                raise SystemExit(result.returncode)
            else:
                # Fallback: file copy
                shutil.copy2(db_file, out_path)
                click.echo(f"Файл БД скопійовано: {out_path}")
        else:
            click.echo(f"Непідтримуваний тип БД: {db_url}", err=True)
            raise SystemExit(1)

    asyncio.run(_run())
