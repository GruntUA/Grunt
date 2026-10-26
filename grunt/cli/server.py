import subprocess

import click

# `grunt serve` (backend + worker + Vite) and `grunt init` live in grunt-cli:
# the dev supervisor runs the mise tasks of apps/grunt/mise.toml.


@click.command()
def worker():
    """Start the background job worker (TaskIQ).

    Tasks are registered by grunt.tasks.worker, inside the worker process itself
    (TaskIQ starts it as a separate process, so imports here are not visible to it).
    """
    click.echo("Starting the TaskIQ worker...")
    subprocess.run(["taskiq", "worker", "grunt.tasks.worker:broker", "--no-configure-logging"])
