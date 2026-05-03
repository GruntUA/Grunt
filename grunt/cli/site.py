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


# ── Group ────────────────────────────────────────────────────────────────────


@click.group("site")
def site_group():
    """Управління сайтами Ґрунт."""
    pass


# ── list ─────────────────────────────────────────────────────────────────────


@site_group.command("list")
def site_list():
    """Показати всі сайти у bench."""
    sites_dir = _get_sites_dir()
    if not sites_dir.exists():
        click.echo("Директорія sites/ не знайдена.")
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
        click.echo("Сайтів не знайдено. Створіть: grunt site create <name>")
        return

    click.echo(f"{'Сайт':<30} {'DB':<50} {'Active'}")
    click.echo("─" * 90)
    for name in sites:
        env_path = sites_dir / name / ".env"
        db_url = ""
        if env_path.exists():
            import dotenv  # noqa: PLC0415

            env = dotenv.dotenv_values(env_path)
            db_url = env.get("DATABASE_URL", "sqlite (default)")

        marker = "◀ active" if name == current else ""
        click.echo(f"{name:<30} {db_url:<50} {marker}")


# ── info ─────────────────────────────────────────────────────────────────────


@site_group.command("info")
@click.argument("name")
def site_info(name: str):
    """Показати конфігурацію сайту."""
    site_path = _site_path(name)
    if not _is_valid_site(site_path):
        click.echo(f"Сайт '{name}' не знайдено.", err=True)
        raise SystemExit(1)

    sites_dir = _get_sites_dir()
    current = ""
    currentsite_file = sites_dir / "currentsite.txt"
    if currentsite_file.exists():
        current = currentsite_file.read_text().strip()

    click.echo(f"\n{'═' * 50}")
    click.echo(f"  Сайт: {name}{'  ← active' if name == current else ''}")
    click.echo(f"{'═' * 50}")
    click.echo(f"  Шлях:    {site_path}")

    env_path = site_path / ".env"
    if env_path.exists():
        import dotenv  # noqa: PLC0415

        env = dotenv.dotenv_values(env_path)
        click.echo(f"\n  .env ({env_path}):")
        for key, val in sorted(env.items()):
            # Mask secrets
            if any(s in key.upper() for s in ("SECRET", "PASSWORD", "KEY")):
                val = "***"
            click.echo(f"    {key}={val}")
    else:
        click.echo("  .env: не знайдено")

    db_path = site_path / "grunt.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size // 1024
        click.echo(f"\n  grunt.db: {size_kb} KB")

    click.echo("")


# ── create ───────────────────────────────────────────────────────────────────


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
    help="Email адміністратора сайту",
)
@click.option(
    "--admin-password",
    default=None,
    help="Пароль адміністратора (за замовчуванням: генерується)",
)
@click.option(
    "--no-migrate",
    is_flag=True,
    help="Не запускати міграцію автоматично",
)
def site_create(
    name: str,
    db_url: str | None,
    admin_email: str,
    admin_password: str | None,
    no_migrate: bool,
) -> None:
    """Створити новий сайт."""
    import re  # noqa: PLC0415
    import secrets  # noqa: PLC0415

    if not re.match(r"^[a-zA-Z0-9._-]+$", name):
        click.echo("Помилка: назва сайту може містити лише літери, цифри, '.', '-', '_'.", err=True)
        raise SystemExit(1)

    sites_dir = _get_sites_dir()
    site_path = sites_dir / name

    if site_path.exists():
        click.echo(f"Помилка: сайт '{name}' вже існує.", err=True)
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

    click.echo(f"✓ Сайт '{name}' створено: {site_path}")
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
        click.echo("  ◀ Встановлено як активний сайт")

    if no_migrate:
        click.echo("\nПідказка: запустіть 'grunt db migrate' для ініціалізації схеми.")
        click.echo(f"Пароль адміна: {password}")
        return

    # Run migrate
    click.echo("\nЗапуск міграції...")
    _run_migrate_for_site(name)

    # Create admin user
    click.echo(f"\nСтворення адміністратора ({admin_email})...")
    asyncio.run(_create_admin(name, admin_email, password))

    click.echo(f"\n{'─' * 50}")
    click.echo(f"  Сайт '{name}' готовий!")
    click.echo("  URL:      http://localhost:8000")
    click.echo(f"  Admin:    {admin_email}")
    click.echo(f"  Password: {password}")
    click.echo(f"{'─' * 50}")


def _run_migrate_for_site(site_name: str) -> None:
    """Run DB migration for a single site (reuses db migrate logic inline)."""

    async def _migrate() -> None:
        from grunt.db.base import Base  # noqa: PLC0415
        from grunt.metadata.compiler import SA_METADATA, sync_table  # noqa: PLC0415
        from grunt.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.site.manager import site_manager  # noqa: PLC0415
        from grunt.startup import (  # noqa: PLC0415
            apply_doctype_overrides,
            load_core_doctypes,
            populate_system_doctypes,
            seed_app_workspaces,
            seed_grunt_workspace,
            seed_system_settings,
        )

        eng = site_manager.get_engine(site_name)
        maker = site_manager.get_session_maker(site_name)

        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with eng.begin() as conn:
            await conn.run_sync(SA_METADATA.create_all)

        async with maker() as session:
            await load_core_doctypes(session)
            await apply_doctype_overrides(session, eng)
            await populate_system_doctypes(session, eng)

            for dt in await doctype_registry.list_all():
                try:
                    if not dt.is_virtual:
                        await sync_table(dt, eng, session=session)
                except Exception as e:  # noqa: BLE001
                    click.echo(f"  [warn] {dt.name}: {e}", err=True)

            await session.commit()

        async with maker() as session:
            await seed_system_settings(session, eng)
            await seed_grunt_workspace(session, eng)
            await session.commit()

        async with maker() as session:
            await seed_app_workspaces(session, site_name)
            await session.commit()

    asyncio.run(_migrate())
    click.echo("  ✓ Міграцію завершено")


async def _create_admin(site_name: str, email: str, password: str) -> None:
    from grunt.auth.doctypes.User.User import create_user, get_user_by_email  # noqa: PLC0415
    from grunt.site.manager import current_site, site_manager  # noqa: PLC0415

    token = current_site.set(site_name)
    try:
        maker = site_manager.get_session_maker(site_name)
        async with maker() as session:
            try:
                if await get_user_by_email(email, session) is not None:
                    click.echo("  [info] Адмін вже існує — пропускаємо")
                    return
                await create_user(email, password, "Administrator", session)
                await session.commit()
                click.echo("  ✓ Адміністратора створено")
            except Exception as e:  # noqa: BLE001
                click.echo(f"  [warn] Помилка при створенні адміна: {e}", err=True)
    finally:
        current_site.reset(token)


# ── delete ───────────────────────────────────────────────────────────────────


@site_group.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Не запитувати підтвердження")
def site_delete(name: str, yes: bool) -> None:
    """Видалити сайт та всі його дані."""
    site_path = _site_path(name)
    if not _is_valid_site(site_path):
        click.echo(f"Сайт '{name}' не знайдено.", err=True)
        raise SystemExit(1)

    if not yes:
        click.echo(f"⚠ Це видалить всі дані сайту '{name}': {site_path}")
        if not click.confirm("Продовжити?"):
            click.echo("Скасовано.")
            return

    shutil.rmtree(site_path)
    click.echo(f"✓ Сайт '{name}' видалено.")

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
            click.echo(f"  Активний сайт змінено на: {remaining[0]}")
        else:
            currentsite_file.unlink(missing_ok=True)


# ── use ──────────────────────────────────────────────────────────────────────


@site_group.command("use")
@click.argument("name")
def site_use(name: str) -> None:
    """Встановити сайт як активний (за замовчуванням для CLI)."""
    site_path = _site_path(name)
    if not _is_valid_site(site_path):
        click.echo(f"Сайт '{name}' не знайдено.", err=True)
        raise SystemExit(1)

    sites_dir = _get_sites_dir()
    _write_currentsite(sites_dir, name)
    click.echo(f"✓ Активний сайт: {name}")
