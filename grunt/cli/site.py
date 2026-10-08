"""CLI commands for Grunt site management.

Usage:
    grunt site list
    grunt site create <name> [--db-url URL] [--admin-email EMAIL]
    grunt site delete <name> [--yes]
    grunt site info <name>
    grunt site use <name>
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import click


def _get_sites_dir() -> Path:
    """Locate the bench's sites/ directory by walking up from cwd."""
    cwd = Path.cwd()
    check = cwd
    for _ in range(5):
        if (check / "apps").is_dir() and (check / "sites").is_dir():
            return (check / "sites").resolve()
        if check == check.parent:
            break
        check = check.parent
    # Fallback: create sites/ next to cwd
    return (cwd.parent.parent / "sites").resolve()


def _site_path(name: str) -> Path:
    return _get_sites_dir() / name


def _is_valid_site(path: Path) -> bool:
    return path.is_dir() and (path / "grunt.site").exists()


def _write_currentsite(sites_dir: Path, name: str) -> None:
    (sites_dir / "currentsite.txt").write_text(name)


# Group


@click.group("site")
def site_group():
    """Manage Grunt sites."""
    pass


# list


@site_group.command("list")
def site_list():
    """Show all sites in the bench."""
    sites_dir = _get_sites_dir()
    if not sites_dir.exists():
        click.echo("The sites/ directory was not found.")
        return

    current = ""
    currentsite_file = sites_dir / "currentsite.txt"
    if currentsite_file.exists():
        current = currentsite_file.read_text().strip()

    sites = [
        d.name
        for d in sorted(sites_dir.iterdir())
        if d.is_dir() and not d.name.startswith(".") and (d / "grunt.site").exists()
    ]

    if not sites:
        click.echo("No sites found. Create one: grunt site create <name>")
        return

    click.echo(f"{'Site':<30} {'DB':<50} {'Active'}")
    click.echo("─" * 90)
    for name in sites:
        env_path = sites_dir / name / ".env"
        db_url = ""
        if env_path.exists():
            import dotenv

            env = dotenv.dotenv_values(env_path)
            db_url = env.get("DATABASE_URL", "sqlite (default)")

        marker = "◀ active" if name == current else ""
        click.echo(f"{name:<30} {db_url:<50} {marker}")


# info


@site_group.command("info")
@click.argument("name")
def site_info(name: str):
    """Show the site configuration."""
    site_path = _site_path(name)
    if not _is_valid_site(site_path):
        click.echo(f"Site '{name}' not found.", err=True)
        raise SystemExit(1)

    sites_dir = _get_sites_dir()
    current = ""
    currentsite_file = sites_dir / "currentsite.txt"
    if currentsite_file.exists():
        current = currentsite_file.read_text().strip()

    click.echo(f"\n{'═' * 50}")
    click.echo(f"  Site: {name}{'  ← active' if name == current else ''}")
    click.echo(f"{'═' * 50}")
    click.echo(f"  Path:    {site_path}")

    env_path = site_path / ".env"
    if env_path.exists():
        import dotenv

        env = dotenv.dotenv_values(env_path)
        click.echo(f"\n  .env ({env_path}):")
        for key, val in sorted(env.items()):
            # Mask secrets
            if any(s in key.upper() for s in ("SECRET", "PASSWORD", "KEY")):
                val = "***"
            click.echo(f"    {key}={val}")
    else:
        click.echo("  .env: not found")

    db_path = site_path / "grunt.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size // 1024
        click.echo(f"\n  grunt.db: {size_kb} KB")

    click.echo("")


# create


@site_group.command("create")
@click.argument("name")
@click.option(
    "--db-url",
    default=None,
    help="Database URL (default: sqlite+aiosqlite:///./grunt.db)",
)
@click.option(
    "--admin-email",
    default="admin@example.com",
    show_default=True,
    help="Site administrator email",
)
@click.option(
    "--admin-password",
    default=None,
    help="Administrator password (default: generated)",
)
@click.option(
    "--no-migrate",
    is_flag=True,
    help="Do not run the migration automatically",
)
def site_create(
    name: str,
    db_url: str | None,
    admin_email: str,
    admin_password: str | None,
    no_migrate: bool,
) -> None:
    """Create a new site."""
    import re
    import secrets

    if not re.match(r"^[a-zA-Z0-9._-]+$", name):
        click.echo(
            "Error: the site name may contain only letters, digits, '.', '-', '_'.", err=True
        )
        raise SystemExit(1)

    sites_dir = _get_sites_dir()
    site_path = sites_dir / name

    if site_path.exists():
        click.echo(f"Error: site '{name}' already exists.", err=True)
        raise SystemExit(1)

    # Create directory structure
    site_path.mkdir(parents=True, exist_ok=True)
    (site_path / "grunt.site").write_text(f"site={name}\n")

    # Generate secret key
    secret_key = secrets.token_hex(32)
    password = admin_password or secrets.token_urlsafe(12)

    # Write .env
    resolved_db_url = db_url or "sqlite+aiosqlite:///./grunt.db"
    env_content = (
        f"DATABASE_URL={resolved_db_url}\n"
        f"SECRET_KEY={secret_key}\n"
        f"ADMIN_EMAIL={admin_email}\n"
        f"SITE_NAME={name}\n"
    )
    (site_path / ".env").write_text(env_content)

    click.echo(f"✓ Site '{name}' created: {site_path}")
    click.echo(f"  DB:    {resolved_db_url}")
    click.echo(f"  Admin: {admin_email}")

    # Set as current site if it's the first one
    existing = [
        d.name
        for d in sites_dir.iterdir()
        if d.is_dir() and d.name != name and (d / "grunt.site").exists()
    ]
    currentsite_file = sites_dir / "currentsite.txt"
    if not existing or not currentsite_file.exists():
        _write_currentsite(sites_dir, name)
        click.echo("  ◀ Set as the active site")

    if no_migrate:
        click.echo("\nHint: run 'grunt migrate' to initialize the schema.")
        click.echo(f"Admin password: {password}")
        return

    # Run migrate
    click.echo("\nRunning migration...")
    _run_migrate_for_site(name)

    # Create admin user
    click.echo(f"\nCreating administrator ({admin_email})...")
    asyncio.run(_create_admin(name, admin_email, password))

    click.echo(f"\n{'─' * 50}")
    click.echo(f"  Site '{name}' is ready!")
    click.echo("  URL:      http://localhost:8000")
    click.echo(f"  Admin:    {admin_email}")
    click.echo(f"  Password: {password}")
    click.echo(f"{'─' * 50}")


def _run_migrate_for_site(site_name: str) -> None:
    """Run DB migration for a single site (reuses migrate logic inline)."""

    async def _migrate() -> None:
        from grunt.metadata.compiler import SA_METADATA, sync_table
        from grunt.metadata.registry import doctype_registry
        from grunt.site.manager import current_site, site_manager
        from grunt.startup import (
            apply_doctype_overrides,
            load_core_doctypes,
            seed_grunt_workspace,
            seed_system_settings,
            sync_installed_apps,
        )

        token = current_site.set(site_name)
        try:
            eng = site_manager.get_engine(site_name)
            maker = site_manager.get_session_maker(site_name)

            async with eng.begin() as conn:
                await conn.run_sync(SA_METADATA.create_all)

            async with maker() as session:
                # New site: seed core DocTypes into the DocType table so the
                # server can lazy-load them without ever touching the JSON
                # files again (sync_db=True - same as `grunt migrate`).
                await load_core_doctypes(session, sync_db=True)
                await apply_doctype_overrides(session, eng, sync_db=True)
                await doctype_registry.load_all(session)

                for dt in await doctype_registry.list_all():
                    if not dt.is_virtual:
                        await sync_table(dt, eng, session=session)

                await session.commit()

            async with maker() as session:
                await seed_system_settings(session, eng)
                await seed_grunt_workspace(session, eng)
                await session.commit()

            async with maker() as session:
                await sync_installed_apps(session, site_name)
                await session.commit()
        finally:
            current_site.reset(token)

    asyncio.run(_migrate())
    click.echo("  ✓ Migration complete")


async def _create_admin(site_name: str, email: str, password: str) -> None:
    import grunt
    from grunt.auth.doctypes.User.user import create_user, get_user_by_email
    from grunt.site.manager import current_site, site_manager

    token = current_site.set(site_name)
    try:
        maker = site_manager.get_session_maker(site_name)
        async with maker() as session:
            try:
                async with grunt.context(session):
                    if await get_user_by_email(email) is not None:
                        click.echo("  [info] Admin already exists, skipping")
                        return
                    await create_user(email, password, "Administrator", "", None)
                await session.commit()
                click.echo("  ✓ Administrator created")
            except Exception as e:
                click.echo(f"  [warn] Failed to create admin: {e}", err=True)
    finally:
        current_site.reset(token)


# delete


@site_group.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Do not ask for confirmation")
def site_delete(name: str, yes: bool) -> None:
    """Delete a site and all its data."""
    site_path = _site_path(name)
    if not _is_valid_site(site_path):
        click.echo(f"Site '{name}' not found.", err=True)
        raise SystemExit(1)

    if not yes:
        click.echo(f"⚠ This deletes all data of site '{name}': {site_path}")
        if not click.confirm("Continue?"):
            click.echo("Cancelled.")
            return

    shutil.rmtree(site_path)
    click.echo(f"✓ Site '{name}' deleted.")

    # Update currentsite.txt if needed
    sites_dir = _get_sites_dir()
    currentsite_file = sites_dir / "currentsite.txt"
    if currentsite_file.exists() and currentsite_file.read_text().strip() == name:
        remaining = [
            d.name
            for d in sites_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".") and (d / "grunt.site").exists()
        ]
        if remaining:
            _write_currentsite(sites_dir, remaining[0])
            click.echo(f"  Active site changed to: {remaining[0]}")
        else:
            currentsite_file.unlink(missing_ok=True)


# use


@site_group.command("use")
@click.argument("name")
def site_use(name: str) -> None:
    """Set the active site (the CLI default)."""
    site_path = _site_path(name)
    if not _is_valid_site(site_path):
        click.echo(f"Site '{name}' not found.", err=True)
        raise SystemExit(1)

    sites_dir = _get_sites_dir()
    _write_currentsite(sites_dir, name)
    click.echo(f"✓ Active site: {name}")
