import click

lazy from grunt.utils.shell import start_shell


@click.command("shell")
@click.option("--site", default=None, help="Site name (default: the active site)")
def shell(site: str | None) -> None:
    """Interactive Python REPL inside a site.

    \b
    Available objects:
      grunt, session, engine     the framework and an open DB session
      run(coro)                  run a coroutine in the system context
      get_doc / get_list / save_doc / delete_doc, commit()
    """
    start_shell(site=site)
