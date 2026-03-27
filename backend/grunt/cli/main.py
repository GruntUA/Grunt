
import asyncio
import click
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path


@click.group()
def cli():
    """Ґрунт CLI — інструмент управління фреймворком."""
    pass


# ── Shared helpers ────────────────────────────────────────────────────────────


@asynccontextmanager
async def _site_session(site: str | None):
    """Async context manager: initialise site, load DocType registry, yield session."""
    from grunt.core.site.manager import site_manager, current_site  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.startup import load_core_doctypes  # noqa: PLC0415

    target_site = site or (site_manager.get_sites() or [None])[0]
    if target_site is None:
        click.echo("Помилка: сайт не знайдено.", err=True)
        raise SystemExit(1)

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        async with maker() as session:
            await doctype_registry.load_all(session)
            await load_core_doctypes(session, eng)
            yield session, eng
    finally:
        current_site.reset(token)


# ── Top-level commands ────────────────────────────────────────────────────────


@cli.command()
def init():
    """Ініціалізація проєкту (створення .env, БД та адміна)."""
    click.echo("Ініціалізація Ґрунт...")
    click.echo("Готово.")


@cli.command()
@click.option("--port", default=8000, help="Порт для API")
@click.option("--reload", is_flag=True, help="Режим перезавантаження")
def serve(port, reload):
    """Запуск сервера FastAPI."""
    click.echo(f"Запуск сервера на порту {port}...")
    cmd = ["uvicorn", "grunt.main:app", "--port", str(port)]
    if reload:
        cmd.append("--reload")
    subprocess.run(cmd)


@cli.command()
def worker():
    """Запуск воркера фонових завдань (TaskIQ)."""
    click.echo("Запуск воркера TaskIQ...")
    from grunt.core.tasks.registry import discover_tasks  # noqa: PLC0415

    apps_dir = Path("grunt_apps")
    discover_tasks(apps_dir)
    subprocess.run(["taskiq", "worker", "grunt.core.tasks.broker:broker"])


# ── User management group ─────────────────────────────────────────────────────


@cli.group("users")
def users_group():
    """Керування користувачами."""
    pass


@users_group.command("create")
@click.option("--email", prompt="Email")
@click.option("--password", prompt="Пароль", hide_input=True, confirmation_prompt=True)
@click.option("--full-name", prompt="Повне ім'я")
@click.option("--site", default=None, help="Назва сайту")
def users_create(email, password, full_name, site):
    """Створити нового користувача."""

    async def _run():
        from grunt.core.auth.service import create_user, get_user_by_email  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            if await get_user_by_email(email, session) is not None:
                click.echo(f"Помилка: користувач '{email}' вже існує.", err=True)
                raise SystemExit(1)
            user = await create_user(email, password, full_name, session)
            await session.commit()

        label = "superadmin" if user.is_superadmin else "user"
        click.echo(f"Створено {label}: {user.email} ({user.full_name})")

    asyncio.run(_run())


@users_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def users_list(site):
    """Показати список всіх користувачів."""

    async def _run():
        from grunt.core.auth.service import list_users  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            users = await list_users(session)

        if not users:
            click.echo("Користувачів немає.")
            return

        click.echo(f"{'Email':<35} {'Ім\'я':<25} {'Ролі':<20} Суперадмін")
        click.echo("-" * 90)
        for u in users:
            roles = ", ".join(u.roles) or "—"
            superadmin = "так" if u.is_superadmin else ""
            click.echo(f"{u.email:<35} {u.full_name:<25} {roles:<20} {superadmin}")

    asyncio.run(_run())


@users_group.command("set-password")
@click.argument("email")
@click.option("--password", prompt="Новий пароль", hide_input=True, confirmation_prompt=True)
@click.option("--site", default=None, help="Назва сайту")
def users_set_password(email, password, site):
    """Змінити пароль користувача."""

    async def _run():
        from grunt.core.auth.service import get_user_by_email, hash_password, _user_table  # noqa: PLC0415
        from sqlalchemy import update  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            user = await get_user_by_email(email, session)
            if user is None:
                click.echo(f"Помилка: користувача '{email}' не знайдено.", err=True)
                raise SystemExit(1)

            table = _user_table()
            await session.execute(
                update(table)
                .where(table.c.id == user.id)
                .values(hashed_password=hash_password(password))
            )
            await session.commit()

        click.echo(f"Пароль змінено для {email}.")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
