"""In-memory registry of document actions.

Mirrors ``grunt.metadata.field`` / ``grunt.website.block_types``: apps register
at import time and resolution happens at schema-serve / call time. Registering a
key also adds it to the dynamic-options registry so ``DocTypeAction.action``'s
Select dropdown reflects the live set.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from grunt import log
from grunt.metadata.dynamic_options import register_option

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


DOC_ACTION_SOURCE = "grunt.doc_action"

# key -> DocAction
_REGISTRY: dict[str, DocAction] = {}


@dataclass(slots=True)
class DocAction:
    """A code-registered document action.

    ``doctypes`` lists the DocTypes this action may be bound to. ``["*"]`` (or
    an empty list) means "any DocType".
    """

    key: str
    label: str
    handler: Callable[..., Awaitable[Any] | Any]
    doctypes: list[str] = field(default_factory=list)
    icon: str | None = None
    group: str = ""
    variant: str = "outline"
    confirm: str | None = None
    roles: list[str] = field(default_factory=list)
    module: str = ""
    # Input fields to prompt for before running - each a ``DialogField``-shaped
    # dict (``fieldname``, ``label``, ``fieldtype``, ``required``, ``default``,
    # ``options``, ``description``). The toolbar opens a form dialog and passes
    # the collected values to the handler as ``args``. Empty = run immediately.
    fields: list[dict] = field(default_factory=list)

    def matches(self, doctype: str | None) -> bool:
        if not doctype or not self.doctypes or "*" in self.doctypes:
            return True
        return doctype in self.doctypes

    async def run(self, doc: dict, *, args: dict) -> Any:
        result = self.handler(doc, args=args)
        if inspect.isawaitable(result):
            return await result
        return result


def register_doc_action(action: DocAction) -> None:
    """Register (or replace) *action* by key and expose its key to the dropdown."""
    if action.key in _REGISTRY:
        log.warning("doc_action.override", key=action.key, module=action.module)
    _REGISTRY[action.key] = action
    register_option(DOC_ACTION_SOURCE, action.key)
    log.debug("doc_action.registered", key=action.key, doctypes=action.doctypes)


def get_doc_action(key: str) -> DocAction | None:
    return _REGISTRY.get(key)


def actions_for_doctype(doctype: str | None) -> list[DocAction]:
    """Every registered action bind-able on *doctype* (registration order)."""
    return [a for a in _REGISTRY.values() if a.matches(doctype)]


def doc_action(
    key: str,
    *,
    label: str,
    doctypes: list[str] | None = None,
    icon: str | None = None,
    group: str = "",
    variant: str = "outline",
    confirm: str | None = None,
    roles: list[str] | None = None,
    fields: list[dict] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register the wrapped function as a document action.

    Example::

        @doc_action(
            "recalc_depreciation",
            label="Перерахувати амортизацію",
            doctypes=["Актив"],
            icon="calculator",
            confirm="Перерахувати за поточний період?",
        )
        async def recalc_depreciation(doc: dict, *, args: dict) -> dict:
            ...
            return {"message": "Готово", "refresh": True}
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        register_doc_action(
            DocAction(
                key=key,
                label=label,
                handler=fn,
                doctypes=list(doctypes or []),
                icon=icon,
                group=group,
                variant=variant,
                confirm=confirm,
                roles=list(roles or []),
                fields=list(fields or []),
                module=getattr(fn, "__module__", ""),
            )
        )
        return fn

    return decorator
