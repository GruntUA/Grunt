import asyncio

import click

from grunt.cli.utils import _site_session


@click.group("users")
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
        from grunt.auth.doctypes.User.user import create_user, get_user_by_email

        name_parts = full_name.strip().split()
        first_name = name_parts[0] if name_parts else full_name.strip()
        if len(name_parts) == 1:
            # User DocType requires last_name; fallback to first_name for single-token names.
            last_name = first_name
            middle_name = None
        elif len(name_parts) == 2:
            last_name = name_parts[1]
            middle_name = None
        else:
            last_name = name_parts[-1]
            middle_name = " ".join(name_parts[1:-1])

        async with _site_session(site) as (session, _eng):
            if await get_user_by_email(email, session) is not None:
                click.echo(f"Помилка: користувач '{email}' вже існує.", err=True)
                raise SystemExit(1)
            user = await create_user(
                email,
                password,
                first_name,
                last_name,
                middle_name,
                session,
            )
            await session.commit()

        label = "superadmin" if user.is_superadmin else "user"
        click.echo(f"Створено {label}: {user.email} ({user.full_name})")

    asyncio.run(_run())


@users_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def users_list(site):
    """Показати список всіх користувачів."""

    async def _run():
        from grunt.auth.doctypes.User.user import list_users

        async with _site_session(site) as (session, _eng):
            users = await list_users(session)

        if not users:
            click.echo("Користувачів немає.")
            return

        click.echo(f"{'Email':<35} {"Ім'я":<25} {'Ролі':<20} Суперадмін")
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
        import grunt
        from grunt.app import grunt as grunt_app
        from grunt.auth.doctypes.User.user import (
            get_user_by_email,
            hash_password,
        )

        async with _site_session(site) as (session, eng):
            user = await get_user_by_email(email, session)
            if user is None:
                click.echo(f"Помилка: користувача '{email}' не знайдено.", err=True)
                raise SystemExit(1)

            async with grunt_app.system_context(session, eng):
                await grunt.db.set_value(
                    "User", user.id, {"hashed_password": hash_password(password)}
                )
                await session.commit()

        click.echo(f"Пароль змінено для {email}.")

    asyncio.run(_run())
