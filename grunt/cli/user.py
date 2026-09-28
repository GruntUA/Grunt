import asyncio

import click

from grunt.cli.utils import _site_session


@click.group("users")
def users_group():
    """Manage users."""
    pass


@users_group.command("create")
@click.option("--email", prompt="Email")
@click.option("--password", prompt="Password", hide_input=True, confirmation_prompt=True)
@click.option("--full-name", prompt="Full name")
@click.option("--site", default=None, help="Site name")
def users_create(email, password, full_name, site):
    """Create a new user."""

    async def _run():
        from grunt.app import grunt
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
            async with grunt.context(session, _eng):
                if await get_user_by_email(email) is not None:
                    click.echo(f"Error: user '{email}' already exists.", err=True)
                    raise SystemExit(1)
                user = await create_user(email, password, first_name, last_name, middle_name)
            await session.commit()

        label = "administrator" if "System Manager" in (user.roles or []) else "user"
        click.echo(f"Created {label}: {user.email} ({user.full_name})")

    asyncio.run(_run())


@users_group.command("list")
@click.option("--site", default=None, help="Site name")
def users_list(site):
    """List all users."""

    async def _run():
        from grunt.app import grunt
        from grunt.auth.doctypes.User.user import list_users

        async with (
            _site_session(site) as (session, _eng),
            grunt.context(session, _eng),
        ):
            users = await list_users()

        if not users:
            click.echo("No users.")
            return

        click.echo(f"{'Email':<35} {'Name':<25} Roles")
        click.echo("-" * 90)
        for u in users:
            roles = ", ".join(u.roles) or "—"
            click.echo(f"{u.email:<35} {u.full_name:<25} {roles}")

    asyncio.run(_run())


@users_group.command("set-password")
@click.argument("email")
@click.option("--password", prompt="New password", hide_input=True, confirmation_prompt=True)
@click.option("--site", default=None, help="Site name")
def users_set_password(email, password, site):
    """Change a user's password."""

    async def _run():
        from grunt.app import grunt
        from grunt.auth.doctypes.User.user import (
            get_user_by_email,
            hash_password,
        )

        async with (
            _site_session(site) as (session, eng),
            grunt.context(session, eng),
        ):
            user = await get_user_by_email(email)
            if user is None:
                click.echo(f"Error: user '{email}' not found.", err=True)
                raise SystemExit(1)

            await grunt.db.set_value(
                "User", user.id, {"hashed_password": await hash_password(password)}
            )
            await session.commit()

        click.echo(f"Password changed for {email}.")

    asyncio.run(_run())
