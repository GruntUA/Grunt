"""
Grunt Interactive Shell.

Starts a Python REPL with grunt context pre-loaded:
  session     — AsyncSession for the active site
  engine      — AsyncEngine
  registry    — DocType registry
  run(coro)   — run a coroutine synchronously
  get_doc()   — convenience getter
  get_list()  — convenience lister
  save_doc()  — convenience create/update

Invoked by: grunt shell
"""

from __future__ import annotations

import asyncio
import code
import sys
from typing import Any

# ── Bootstrap ─────────────────────────────────────────────────────────────────


async def _bootstrap(site: str | None) -> dict:
    from grunt.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.site.manager import current_site, site_manager  # noqa: PLC0415
    from grunt.startup import load_core_doctypes  # noqa: PLC0415

    sites = site_manager.get_sites()
    target: str | None = site or (sites[0] if sites else None)
    if target is None:
        print("Помилка: сайт не знайдено.", file=sys.stderr)
        sys.exit(1)

    token = current_site.set(target)
    eng = site_manager.get_engine(target)
    maker = site_manager.get_session_maker(target)
    session_cm = maker()
    session = await session_cm.__aenter__()
    await doctype_registry.load_all(session)
    await load_core_doctypes(session)

    return {
        "session": session,
        "engine": eng,
        "registry": doctype_registry,
        "site": target,
        "_cm": session_cm,
        "_cv": current_site,
        "_token": token,
    }


# ── Convenience helpers ───────────────────────────────────────────────────────


def _make_helpers(loop: asyncio.AbstractEventLoop, session: Any, engine: Any) -> dict:
    def run(coro):
        """Run a coroutine synchronously."""
        return loop.run_until_complete(coro)

    async def _get_doc(doctype: str, name: str) -> dict:
        from grunt.app import grunt  # noqa: PLC0415

        async with grunt.system_context(session, engine):
            return await grunt.get_doc(doctype, name)

    async def _get_list(
        doctype: str,
        filters: dict | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
    ) -> list:
        from grunt.app import grunt  # noqa: PLC0415

        async with grunt.system_context(session, engine):
            return await grunt.get_list(
                doctype,
                filters=filters or {},
                fields=fields,
                limit=limit,
            )

    async def _save_doc(doctype: str, data: dict) -> dict:
        from grunt.app import grunt  # noqa: PLC0415

        async with grunt.system_context(session, engine):
            doc_id = data.get("id") or data.get("name")
            if doc_id:
                return await grunt.save_doc(doctype, doc_id, data)
            return await grunt.new_doc(doctype, data)

    async def _delete_doc(doctype: str, name: str) -> None:
        from grunt.app import grunt  # noqa: PLC0415

        async with grunt.system_context(session, engine):
            await grunt.delete_doc(doctype, name)

    def get_doc(doctype: str, name: str) -> dict:
        """Get a document by DocType and name/id."""
        return run(_get_doc(doctype, name))

    def get_list(
        doctype: str,
        filters: dict | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
    ) -> list:
        """List documents. Optionally filter and select fields."""
        return run(_get_list(doctype, filters, fields, limit))

    def save_doc(doctype: str, data: dict) -> dict:
        """Create or update a document (set 'id' field to update)."""
        return run(_save_doc(doctype, data))

    def delete_doc(doctype: str, name: str) -> None:
        """Delete a document by DocType and name/id."""
        run(_delete_doc(doctype, name))

    return {
        "run": run,
        "get_doc": get_doc,
        "get_list": get_list,
        "save_doc": save_doc,
        "delete_doc": delete_doc,
    }


# ── REPL ──────────────────────────────────────────────────────────────────────


def start_shell(site: str | None = None) -> None:
    """Bootstrap grunt context and start an interactive REPL."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    ctx = loop.run_until_complete(_bootstrap(site))
    helpers = _make_helpers(loop, ctx["session"], ctx["engine"])

    banner = _make_banner(ctx["site"])
    local_vars: dict[str, Any] = {
        "session": ctx["session"],
        "engine": ctx["engine"],
        "registry": ctx["registry"],
        "asyncio": asyncio,
        **helpers,
    }

    try:
        _start_repl(local_vars, banner)
    finally:
        loop.run_until_complete(ctx["_cm"].__aexit__(None, None, None))
        ctx["_cv"].reset(ctx["_token"])
        loop.close()


def _start_repl(local_vars: dict, banner: str) -> None:
    """Try IPython first, fall back to stdlib code.interact."""
    try:
        import IPython  # noqa: PLC0415
        from traitlets.config import Config  # noqa: PLC0415

        cfg = Config()
        cfg.InteractiveShell.autoawait = True  # allow `await` at top level
        IPython.start_ipython(argv=[], user_ns=local_vars, config=cfg, display_banner=False)
        print(banner)
    except ImportError:
        code.interact(banner=banner, local=local_vars, exitmsg="")


def _make_banner(site: str) -> str:
    return f"""
  ⚡ Ґрунт Interactive Shell  ─────────────────────────────────────────────
  Site     : {site}
  Python   : {sys.version.split()[0]}

  Об'єкти:
    session            AsyncSession (поточний сайт)
    engine             AsyncEngine
    registry           DocType Registry
    run(coro)          виконати async coroutine синхронно

  Зручні функції:
    get_doc(doctype, name)                        → dict
    get_list(doctype, filters, fields, limit)     → list[dict]
    save_doc(doctype, data)                       → dict  (create або update)
    delete_doc(doctype, name)                     → None

  Приклади:
    >>> get_list("User", limit=5)
    >>> get_doc("User", "admin@example.com")
    >>> save_doc("ToDo", {{"title": "Test task", "status": "Open"}})
    >>> run(registry.get("MyDocType"))

  Ctrl+D / exit() для виходу
  ─────────────────────────────────────────────────────────────────────────
"""
