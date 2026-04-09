from importlib.metadata import entry_points

import click

from grunt.cli.app import app_group, create_app
from grunt.cli.db import db_group
from grunt.cli.doctype import doctype_group
from grunt.cli.server import init, serve, worker
from grunt.cli.update import update
from grunt.cli.user import users_group


@click.group()
def cli():
    """Ґрунт CLI — інструмент управління фреймворком."""
    pass


def _load_plugins() -> None:
    """Discover and register CLI commands from installed Grunt apps.

    Apps declare their commands in pyproject.toml:

        [project.entry-points."grunt.commands"]
        myapp = "myapp.cli:cli"

    The registered group/command is added to the top-level ``cli`` group.
    """
    for ep in entry_points(group="grunt.commands"):
        try:
            cmd = ep.load()
            if isinstance(cmd, click.BaseCommand):  # type: ignore[arg-type]
                cli.add_command(cmd, name=ep.name)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"[warn] grunt.commands plugin '{ep.name}' failed to load: {exc}", err=True)


# Register built-in commands
cli.add_command(init)
cli.add_command(serve)
cli.add_command(worker)
cli.add_command(update)
cli.add_command(users_group)
cli.add_command(db_group)
cli.add_command(create_app)
cli.add_command(app_group)
cli.add_command(doctype_group)

# Load dynamic plugins
_load_plugins()
