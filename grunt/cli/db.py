import asyncio
from contextlib import suppress

import click


@click.group("db")
def db_group():
    """Database management commands."""
    pass


@db_group.command("migrate")
@click.option(
    "--dry-run", is_flag=True, help="Show the SQL without running it (for DocType tables)"
)
@click.option("--site", default=None, help="Site name")
@click.option("--no-alembic", is_flag=True, help="Skip the Alembic schema-history migrations")
def db_migrate(dry_run: bool, site: str | None, no_alembic: bool) -> None:
    """Sync the database schema: Alembic migrations + system tables + DocType tables + fixtures.

    Run it after:
    - A framework update (new Alembic migrations, core DocTypes or field changes)
    - Adding new DocTypes in Studio
    - Installing new apps with DocTypes
    - Changes to fixture files (00_workspace.json etc.)
    """
    import asyncio

    async def _run() -> list[str]:
        from taskiq import InMemoryBroker

        from grunt.db.base import metadata
        from grunt.metadata.compiler import SA_METADATA, sync_table
        from grunt.metadata.registry import doctype_registry
        from grunt.site.manager import current_site, site_manager
        from grunt.startup import (
            apply_doctype_overrides,
            load_core_doctypes,
            load_core_fixtures,
            populate_system_doctypes,
            seed_grunt_workspace,
            seed_system_settings,
            sync_installed_apps,
        )
        from grunt.tasks.broker import broker

        broker_started = False
        failed: list[str] = []

        try:
            await broker.startup()
            broker_started = True

            sites = [site] if site else site_manager.get_sites()
            if not sites:
                click.echo("No sites found.", err=True)
                raise SystemExit(1)

            for site_name in sites:
                click.echo(f"\n── Site: {site_name} ──")
                token = current_site.set(site_name)
                try:
                    eng = site_manager.get_engine(site_name)
                    maker = site_manager.get_session_maker(site_name)

                    # 1. System ORM tables
                    click.echo("  [1/5] System tables (metadata.create_all)...")
                    async with eng.begin() as conn:
                        await conn.run_sync(metadata.create_all)

                    # 2. Shared infrastructure tables (MultiLink junction, etc.)
                    click.echo("  [2/5] Infrastructure tables (SA_METADATA)...")
                    async with eng.begin() as conn:
                        await conn.run_sync(SA_METADATA.create_all)

                    # 3. Alembic history - schema patches on top of create_all.
                    #    Fresh site -> stamp head; existing -> upgrade. Not
                    #    offline-previewable, so --dry-run skips it.
                    if no_alembic or dry_run:
                        why = "--no-alembic" if no_alembic else "dry-run"
                        click.echo(f"  [3/5] Alembic: skipped ({why}).")
                    else:
                        from grunt.db.alembic_utils import sync_site

                        db_url = site_manager.get_database_url(site_name)
                        outcome = await asyncio.to_thread(sync_site, db_url)
                        click.echo(f"  [3/5] Alembic — {outcome}.")

                    # 4. DocType tables
                    click.echo("  [4/5] DocType tables (sync_table)...")
                    async with maker() as session:
                        await load_core_doctypes(session, sync_db=True)
                        await apply_doctype_overrides(session, eng, sync_db=True)
                        # Hydrate Studio-created DocTypes too - list_all()'s
                        # lazy branch only fires once _known_names is populated.
                        await doctype_registry.load_all(session)
                        await populate_system_doctypes(session, eng)

                        all_dts = await doctype_registry.list_all()

                        synced = 0
                        skipped = 0
                        for dt in all_dts:
                            try:
                                if dt.is_virtual:
                                    skipped += 1
                                    continue
                                if dry_run:
                                    click.echo(f"    [dry-run] would sync: {dt.name}")
                                else:
                                    await sync_table(dt, eng, session=session)
                                    click.echo(f"    synced: {dt.name}")
                                synced += 1
                            except Exception as e:
                                failed.append(f"{site_name}: {dt.name}")
                                click.echo(f"    [error] {dt.name}: {e}", err=True)

                        await session.commit()

                    click.echo(f"  Done: {synced} synced, {skipped} skipped (virtual).")

                    # 4. Seed fixtures (skip on dry-run)
                    if dry_run:
                        click.echo("  [5/5] Seed fixtures: skipped (dry-run).")
                    else:
                        click.echo("  [5/5] Seed fixtures...")
                        async with maker() as session:
                            await seed_system_settings(session, eng)
                            await load_core_fixtures(session, eng)
                            await seed_grunt_workspace(session, eng)
                            await session.commit()

                        async with maker() as session:
                            await sync_installed_apps(session, site_name)
                            await session.commit()

                        click.echo("  Fixtures applied.")

                    # 5. Trigger hot-reload for running servers
                    reload_file = site_manager.sites_dir / site_name / ".reload_meta"
                    reload_file.touch()
                    click.echo("  Hot-reload triggered.")
                finally:
                    current_site.reset(token)
        finally:
            if broker_started:
                if isinstance(broker, InMemoryBroker):
                    with suppress(Exception):
                        await broker.wait_all()
                with suppress(Exception):
                    await broker.shutdown()

            for eng in list(site_manager.engines.values()):
                with suppress(Exception):
                    await eng.dispose()

            site_manager.engines.clear()
            site_manager.session_makers.clear()

        return failed

    failed = asyncio.run(_run())
    if failed:
        click.echo(f"\nMigration finished with errors ({len(failed)}):", err=True)
        for item in failed:
            click.echo(f"  {item}", err=True)
        raise SystemExit(1)
    click.echo("\nMigration complete.")


@db_group.command("trim-tables")
@click.option("--doctype", "-d", default=None, help="Specific DocType to process")
@click.option("--dry-run", is_flag=True, help="Only show what would be removed")
@click.option("--quiet", "-q", is_flag=True, help="Do not print information")
@click.option("--site", default=None, help="Site name")
def db_trim_tables(doctype: str | None, dry_run: bool, quiet: bool, site: str | None) -> None:
    """Drop table columns that are not in the metadata (DocType)."""
    import asyncio

    from grunt.site.manager import current_site, site_manager

    async def _run() -> None:
        import grunt
        from grunt.metadata.registry import doctype_registry

        sites = [site] if site else site_manager.get_sites()
        if not sites:
            click.echo("No sites found.", err=True)
            raise SystemExit(1)

        for site_name in sites:
            if not quiet:
                click.echo(f"\n── Site: {site_name} ──")
            token = current_site.set(site_name)
            try:
                eng = site_manager.get_engine(site_name)
                maker = site_manager.get_session_maker(site_name)

                async with maker() as session:
                    # Hydrate every DocType (core + Studio) from the DB so we
                    # can iterate them - reads only, no schema/JSON merge here.
                    await doctype_registry.load_all(session)

                    async with grunt.system_context(session, eng):
                        from grunt.document.meta import Meta

                        all_metas = [
                            Meta(dt)
                            for dt in await doctype_registry.list_all()
                            if not dt.is_virtual
                        ]
                        if doctype:
                            target_meta = await grunt.get_meta(doctype)
                            if target_meta is None:
                                click.echo(f"DocType '{doctype}' not found.", err=True)
                                raise SystemExit(1)
                            metas = [target_meta]
                        else:
                            metas = all_metas

                # Several DocTypes may share a table (table_name) - a column is kept
                # while any of them still defines it.
                shared: dict[str, set[str]] = {}
                for m in all_metas:
                    shared.setdefault(m.table_name, set()).update(m.get_valid_columns())

                # Trim only after the session is closed: its transaction (BEGIN
                # IMMEDIATE) would lock out trim_table's own connection.
                for m in metas:
                    await m.trim_table(
                        engine=eng,
                        dry_run=dry_run,
                        quiet=quiet,
                        keep=shared.get(m.table_name, ()),
                    )
            finally:
                current_site.reset(token)

        if not quiet:
            click.echo("\nColumn cleanup complete.")

    asyncio.run(_run())


def _resolve_site(site: str | None) -> str:
    from grunt.site.manager import site_manager

    return site or site_manager.get_active_site()


@db_group.command("backup")
@click.option("--site", default=None, help="Site name")
@click.option("--no-database", is_flag=True, help="Without the database")
@click.option("--no-files", is_flag=True, help="Without uploaded files")
@click.option("--no-config", is_flag=True, help="Without the site .env")
def db_backup(site: str | None, no_database: bool, no_files: bool, no_config: bool):
    """Back up the site to sites/<site>/backups/ (database, files, .env)."""
    from grunt.backups import BackupError, create_backup

    try:
        backup = asyncio.run(
            create_backup(
                _resolve_site(site),
                with_database=not no_database,
                with_files=not no_files,
                with_config=not no_config,
            )
        )
    except BackupError as e:
        raise click.ClickException(str(e)) from e
    for kind, path in sorted(backup.files.items()):
        click.echo(f"{kind:9} {path}")


@db_group.command("backups")
@click.option("--site", default=None, help="Site name")
def db_backups(site: str | None):
    """Show the site's backups (newest first)."""
    from grunt.backups import list_backups
    from grunt.monitoring.health import human_size

    for backup in list_backups(_resolve_site(site)):
        kinds = ", ".join(sorted(backup.files))
        click.echo(f"{backup.id}  {human_size(backup.size()):>10}  {kinds}")


@db_group.command("restore")
@click.argument("backup_id")
@click.option("--site", default=None, help="Site name")
@click.option("--with-files", is_flag=True, help="Restore uploaded files too")
@click.option("--yes", is_flag=True, help="Do not ask for confirmation")
def db_restore(backup_id: str, site: str | None, with_files: bool, yes: bool):
    """Restore the site from a backup (ID from `grunt db backups`).

    Stop the server and worker before restoring. The current database (and files with
    --with-files) are moved to backups/pre-restore-<time>/, so the restore
    can be rolled back.
    """
    from grunt.backups import BackupError, get_backup, restore_backup

    target = _resolve_site(site)
    backup = get_backup(target, backup_id)
    if backup is None:
        raise click.ClickException(f"Backup {backup_id} does not exist; see `grunt db backups`")
    if not yes:
        click.confirm(
            f"Replace the database{' and files' if with_files else ''} of site {target} "
            f"with backup {backup_id}? The server and worker must be stopped.",
            abort=True,
        )
    try:
        aside = restore_backup(target, backup, with_files=with_files)
    except BackupError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"Restored from {backup_id}. Previous state: {aside}")
