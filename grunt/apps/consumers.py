"""Hook-key consumers - the registry that maps a name in an app's ``hooks.py``
to the code that acts on it.

An app's ``hooks.py`` is just a module with well-known module-level names
(``doc_events``, ``scheduler_events``, ``io_exporters``, ...). For each name
that a hooks module defines, :func:`grunt.apps.loader._apply_hooks_module`
looks it up here and calls the registered consumer. Adding a new kind of hook
means registering one consumer with :func:`consumer` - never editing the app
loader's control flow.

The framework itself ("app zero", :mod:`grunt.core_hooks`) is loaded through
this exact path.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from grunt import log
from grunt.actions import load_app_doc_actions
from grunt.document.registry import document_registry
from grunt.document.tree import register_tree_title_resolver
from grunt.hooks import register_doc_events, register_doctype_overrides
from grunt.io import register_exporter, register_importer
from grunt.tasks.scheduler import register_scheduler_events
from grunt.website import website_registry
from grunt.website.block_types import register_block_type

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from pathlib import Path

    from fastapi import FastAPI


@dataclass(frozen=True, slots=True)
class LoadContext:
    """Everything a consumer might need about the app being loaded.

    ``app_dir`` is the *outer* app directory (``bench/apps/<name>`` for an
    external app, the ``grunt/`` package dir for app zero). ``fastapi_app`` is
    ``None`` when loading happens before the ASGI app exists (e.g. app zero at
    import time).
    """

    app_name: str
    app_dir: Path
    fastapi_app: FastAPI | None = None


ConsumerFn = Callable[[Any, "LoadContext"], "Awaitable[None] | None"]


@dataclass(frozen=True, slots=True)
class HookConsumer:
    key: str
    apply: ConsumerFn


# hook-key -> consumer. Insertion order is the order consumers run for a
# module, so keep registration order meaningful (registry mutations before
# anything that reads the registry).
HOOK_CONSUMERS: dict[str, HookConsumer] = {}


def consumer(key: str) -> Callable[[ConsumerFn], ConsumerFn]:
    """Register the consumer for a hooks.py module-level name."""

    def decorator(fn: ConsumerFn) -> ConsumerFn:
        HOOK_CONSUMERS[key] = HookConsumer(key, fn)
        return fn

    return decorator


def _resolve(path: str) -> Any:
    module_path, attr = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), attr)


# Consumers - one per recognised hooks.py name. Keep imports lazy so importing
# this module stays cheap and cycle-free.


@consumer("doc_events")
def _doc_events(value: dict, ctx: LoadContext) -> None:
    register_doc_events(value)


@consumer("doctype_overrides")
def _doctype_overrides(value: dict, ctx: LoadContext) -> None:
    register_doctype_overrides(value)


@consumer("override_doctype_class")
def _override_doctype_class(value: dict, ctx: LoadContext) -> None:
    document_registry.register_overrides(value)


@consumer("scheduler_events")
def _scheduler_events(value: dict, ctx: LoadContext) -> None:
    register_scheduler_events(value)


@consumer("io_exporters")
def _io_exporters(value: list, ctx: LoadContext) -> None:
    for exp in value:
        register_exporter(exp)
        log.info("io.exporter.registered", id=exp.id, app=ctx.app_name)


@consumer("io_importers")
def _io_importers(value: list, ctx: LoadContext) -> None:
    for imp in value:
        register_importer(imp)
        log.info("io.importer.registered", id=imp.id, app=ctx.app_name)


@consumer("website_block_types")
def _website_block_types(value: list[dict], ctx: LoadContext) -> None:
    website_registry.add_template_source("grunt", ctx.app_dir / "www")
    for bt in value:
        register_block_type(bt["name"], bt["template"], bt.get("fields"))
        log.info("website.block_type.registered", name=bt["name"], app=ctx.app_name)


@consumer("tree_title_resolvers")
def _tree_title_resolvers(value: dict[str, str], ctx: LoadContext) -> None:
    for doctype, path in value.items():
        try:
            register_tree_title_resolver(doctype, _resolve(path))
            log.debug("tree.title_resolver.registered", doctype=doctype, app=ctx.app_name)
        except Exception as e:
            log.warning("tree.title_resolver.error", doctype=doctype, handler=path, error=str(e))


@consumer("doc_actions")
def _doc_actions(value: list[str], ctx: LoadContext) -> None:
    load_app_doc_actions(list(value), app=ctx.app_name)


@consumer("mcp_tools")
def _mcp_tools(value: list[str], ctx: LoadContext) -> None:
    # Each path names a function decorated with ``@mcp_tool`` - importing it registers it.
    for path in value:
        try:
            _resolve(path)
            log.debug("mcp.tool.loaded", handler=path, app=ctx.app_name)
        except Exception as e:
            log.warning("mcp.tool.error", handler=path, app=ctx.app_name, error=str(e))
