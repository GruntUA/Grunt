"""Ґрунт CLI — головна точка входу."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="Ґрунт")
def cli() -> None:
    """⚡ Ґрунт — metadata-driven application framework"""


from grunt.cli.commands.serve import serve      # noqa: E402
from grunt.cli.commands.db import db            # noqa: E402
from grunt.cli.commands.doctype import doctype  # noqa: E402
from grunt.cli.commands.init import init        # noqa: E402
from grunt.cli.commands.auth import auth        # noqa: E402

cli.add_command(serve)
cli.add_command(db)
cli.add_command(doctype)
cli.add_command(init)
cli.add_command(auth)

from grunt.cli.commands.app import app          # noqa: E402

cli.add_command(app)
