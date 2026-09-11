from importlib.metadata import entry_points

import click

from grunt.cli.app import app_group
from grunt.cli.db import db_group, db_migrate
from grunt.cli.doctype import doctype_group
from grunt.cli.fields import fields_group
from grunt.cli.i18n import i18n_group
from grunt.cli.lint import lint
from grunt.cli.server import init, serve, worker
from grunt.cli.site import site_group
from grunt.cli.skills import skills_group
from grunt.cli.test import test
from grunt.cli.ui import ui_group
from grunt.cli.update import update_group
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
        except Exception as exc:
            click.echo(f"[warn] grunt.commands plugin '{ep.name}' failed to load: {exc}", err=True)


# Register built-in commands
cli.add_command(init)
cli.add_command(serve)
cli.add_command(test)
cli.add_command(worker)
cli.add_command(update_group)
cli.add_command(users_group)
cli.add_command(db_group)
cli.add_command(app_group)
cli.add_command(doctype_group)
cli.add_command(fields_group)
cli.add_command(i18n_group)
cli.add_command(site_group)
cli.add_command(db_migrate, name="migrate")
cli.add_command(lint)
cli.add_command(ui_group)
cli.add_command(skills_group)

# Load dynamic plugins
_load_plugins()
