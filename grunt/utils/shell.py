"""Interactive shell for ``grunt shell``.

The CLI runs ``start_shell()`` in the bench's venv. The process boots like the
web server and the task worker (sites, DocType registry, installed apps with
their controllers and hooks), so documents behave in the shell as they do in
the running site. Code runs as the system user.

Objects in the REPL::

    session, engine     the site's AsyncSession / AsyncEngine
    run(coro)           run a coroutine, e.g. run(grunt.get_doc("User", "a@b"))
    get_doc(dt, name), get_list(dt, filters, fields, limit),
    save_doc(dt, data), delete_doc(dt, name)
    commit()            commit the session (changes are not committed otherwise)

Piped input works too: ``echo 'print(get_list("User"))' | grunt shell``.
"""

from __future__ import annotations

import asyncio
import code
import sys
from typing import Any


async def _bootstrap(site: str | None) -> tuple[str, Any, Any, Any]:
    import grunt.main  # noqa: F401 - wires the framework's own hooks (load_core)
    from grunt.site.manager import current_site, site_manager
    from grunt.startup.lifespan import boot

    await boot(None)
    sites = site_manager.get_sites()
    target = site or site_manager.get_active_site() or (sites[0] if sites else None)
    if target is None or target not in sites:
        print(f"Site not found: {target}", file=sys.stderr)
        sys.exit(1)
    current_site.set(target)
    session = site_manager.get_session_maker(target)()
    return target, session, site_manager.get_engine(target), current_site


def start_shell(site: str | None = None) -> None:
    """Boot the site and start a REPL."""
    import grunt

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    target, session, engine, _ = loop.run_until_complete(_bootstrap(site))

    def run(coro: Any) -> Any:
        async def _in_context() -> Any:
            async with grunt.system_context(session, engine):
                return await coro

        return loop.run_until_complete(_in_context())

    def save_doc(doctype: str, data: dict) -> dict:
        if data.get("name"):
            return run(grunt.save_doc(doctype, data["name"], data))
        return run(grunt.new_doc(doctype, data))

    namespace: dict[str, Any] = {
        "grunt": grunt,
        "session": session,
        "engine": engine,
        "asyncio": asyncio,
        "run": run,
        "commit": lambda: loop.run_until_complete(session.commit()),
        "get_doc": lambda doctype, name=None: run(grunt.get_doc(doctype, name)),
        "get_list": lambda doctype, filters=None, fields=None, limit=20: run(
            grunt.get_list(doctype, filters=filters, fields=fields, limit=limit)
        ),
        "save_doc": save_doc,
        "delete_doc": lambda doctype, name: run(grunt.delete_doc(doctype, name)),
    }
    banner = (
        f"Grunt shell - site {target}, Python {sys.version.split()[0]}\n"
        "run(coro), get_doc, get_list, save_doc, delete_doc, commit(); Ctrl+D to quit"
    )
    try:
        if sys.stdin.isatty():
            code.interact(banner=banner, local=namespace, exitmsg="")
        else:
            exec(compile(sys.stdin.read(), "<stdin>", "exec"), namespace)  # noqa: S102
    finally:
        loop.run_until_complete(session.close())
        loop.close()
