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
    """Синхронізувати схему БД: system tables + DocType tables + fixtures.

    Запускати після:
    - Оновлення фреймворку (нові core DocTypes або зміни полів)
    - Додавання нових DocTypes через Studio
    - Встановлення нових додатків із DocTypes
    - Змін у fixture файлах (00_workspace.json тощо)
    """
    import asyncio  # noqa: PLC0415

    async def _run() -> None:
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.db.base import Base  # noqa: PLC0415
        from grunt.core.db.system_tables import GruntMetaDoctype  # noqa: PLC0415
        from grunt.core.metadata.compiler import SA_METADATA, sync_table  # noqa: PLC0415
        from grunt.core.metadata.doctype import DocType  # noqa: PLC0415
        from grunt.core.site.manager import site_manager  # noqa: PLC0415
        from grunt.core.startup import (  # noqa: PLC0415
            apply_doctype_overrides,
            load_core_doctypes,
            populate_system_doctypes,
            seed_app_workspaces,
            seed_grunt_workspace,
            seed_system_settings,
        )

        sites = [site] if site else site_manager.get_sites()
        if not sites:
            click.echo("Жодного сайту не знайдено.", err=True)
            raise SystemExit(1)

        for site_name in sites:
            click.echo(f"\n── Сайт: {site_name} ──")
            eng = site_manager.get_engine(site_name)
            maker = site_manager.get_session_maker(site_name)

            # 1. System ORM tables
            click.echo("  [1/4] System tables (Base.metadata)...")
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 2. Shared infrastructure tables (MultiLink junction, etc.)
            click.echo("  [2/4] Infrastructure tables (SA_METADATA)...")
            async with eng.begin() as conn:
                await conn.run_sync(SA_METADATA.create_all)

            # 3. DocType tables
            click.echo("  [3/4] DocType tables (sync_table)...")
            async with maker() as session:
                await load_core_doctypes(session)
                await apply_doctype_overrides(session, eng)
                await populate_system_doctypes(session, eng)

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

            click.echo(f"  Done: {synced} synced, {skipped} skipped (virtual).")

            # 4. Seed fixtures (skip on dry-run)
            if dry_run:
                click.echo("  [4/4] Seed fixtures — пропущено (dry-run).")
            else:
                click.echo("  [4/4] Seed fixtures...")
                async with maker() as session:
                    await seed_system_settings(session, eng)
                    await seed_grunt_workspace(session, eng)
                    await session.commit()

                async with maker() as session:
                    await seed_app_workspaces(session, site_name)
                    await session.commit()

                click.echo("  Fixtures applied.")

    asyncio.run(_run())
    click.echo("\nМіграцію завершено.")


@db_group.command("trim-tables")
@click.option("--doctype", "-d", default=None, help="Окремий DocType для обробки")
@click.option("--dry-run", is_flag=True, help="Тільки показати, що буде видалено")
@click.option("--quiet", "-q", is_flag=True, help="Не виводити інформацію")
@click.option("--site", default=None, help="Назва сайту")
def db_trim_tables(doctype: str | None, dry_run: bool, quiet: bool, site: str | None) -> None:
    """Видалити колонки з таблиць, яких немає в метаданих (DocType)."""
    import asyncio  # noqa: PLC0415
    from grunt.core.site.manager import site_manager  # noqa: PLC0415

    async def _run() -> None:
        from grunt.app import grunt
        from grunt.core.startup import load_core_doctypes
        from grunt.core.metadata.registry import doctype_registry

        sites = [site] if site else site_manager.get_sites()
        if not sites:
            click.echo("Жодного сайту не знайдено.", err=True)
            raise SystemExit(1)

        for site_name in sites:
            if not quiet:
                click.echo(f"\n── Сайт: {site_name} ──")
            eng = site_manager.get_engine(site_name)
            maker = site_manager.get_session_maker(site_name)
            
            async with maker() as session:
                # Eagerly load doctypes so we can iterate them
                await load_core_doctypes(session)
                
                # Fetch target Meta(s)
                grunt.session.set_context(session, eng)
                if doctype:
                    metas = [await grunt.get_meta(doctype)]
                else:
                    from grunt.core.document.meta import Meta
                    all_dts = await doctype_registry.list_all()
                    metas = [Meta(dt) for dt in all_dts]
                    
                # Trim them
                for m in metas:
                    await m.trim_table(engine=eng, dry_run=dry_run, quiet=quiet)

        if not quiet:
            click.echo("\nОчистку колонок завершено.")

    asyncio.run(_run())


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
