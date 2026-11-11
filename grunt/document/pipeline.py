"""Extension points of the document write pipeline (:mod:`grunt.document.mixins.lifecycle`).

The pipeline stores documents; the subsystems above it - workflow, the website,
outgoing webhooks, the activity feed, realtime - take part in a write through a
:class:`WriteExtension` instead of being imported by it.

The framework's own extensions live in :mod:`grunt.core_pipeline`, imported by
path before the first write (:func:`extensions`), so none can be left out by an
import order. The workflow guard is a security check: without it registered a
write is refused, never let through.
"""

import importlib
from collections.abc import Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from typing import Any

_CORE = "grunt.core_pipeline"
# Extensions a write must not run without.
REQUIRED = frozenset({"workflow"})

_extensions: list[WriteExtension] = []
_core_loaded = False


class UpdateScope:
    """What an extension carries through one update (see :meth:`WriteExtension.begin_update`)."""

    def active(self) -> AbstractContextManager[Any]:
        """Entered around the hooks and the store write."""
        return nullcontext()

    async def finish(self, result: dict[str, Any], user: str, session: Any) -> None:
        """After the update is stored and the pipeline's context is reset."""


class WriteExtension:
    """One subsystem's part in a write. Override what it needs; the defaults do nothing."""

    name = ""

    async def prepare_insert(
        self, dt: Any, data: dict[str, Any], row: dict[str, Any], user: str
    ) -> None:
        """Adjust the new *row* built from the submitted *data* (may refuse with an error)."""

    async def before_store(self, dt: Any, row: dict[str, Any], session: Any) -> None:
        """Last changes to *row* after the hooks, right before it is stored."""

    async def begin_update(
        self, doctype: str, existing: dict[str, Any], data: dict[str, Any], user: str
    ) -> UpdateScope | None:
        """Check an update of *existing* with the changes *data* (may refuse, may
        change *data*); a scope to carry through it, or ``None``."""
        return None

    async def check_delete(self, doctype: str, existing: dict[str, Any], user: str) -> None:
        """Refuse deleting *existing* with an error, or return."""

    async def after_write(
        self, event: str, session: Any, doctype: str, row: dict[str, Any]
    ) -> None:
        """After ``after_insert`` / ``after_update`` / ``after_delete`` is stored."""

    async def changes_recorded(
        self,
        *,
        session: Any,
        engine: Any,
        doctype: str,
        doc_id: str,
        dt: Any,
        changed_fields: list[str],
        user: str,
    ) -> None:
        """After an update's version is recorded - the fields it changed."""

    async def doc_progress(self, doctype: str, doc_id: str, payload: dict[str, Any]) -> None:
        """A long-running document reports progress (an import)."""


def register(extension: WriteExtension) -> None:
    """Add (or replace, by name) an extension."""
    _extensions[:] = [e for e in _extensions if e.name != extension.name] + [extension]


def extensions() -> list[WriteExtension]:
    """The registered extensions - the framework's loaded first; refuses to hand
    out a pipeline without a :data:`REQUIRED` one."""
    global _core_loaded
    if not _core_loaded:
        importlib.import_module(_CORE)
        _core_loaded = True
    missing = REQUIRED - {e.name for e in _extensions}
    if missing:
        raise RuntimeError(f"grunt: write pipeline extensions missing: {sorted(missing)}")
    return list(_extensions)


class UpdateScopes:
    """The scopes of every extension for one update, entered and finished together."""

    def __init__(self, scopes: list[UpdateScope]) -> None:
        self._scopes = scopes

    @contextmanager
    def active(self) -> Iterator[None]:
        with ExitStack() as stack:
            for scope in self._scopes:
                stack.enter_context(scope.active())
            yield

    async def finish(self, result: dict[str, Any], user: str, session: Any) -> None:
        for scope in self._scopes:
            await scope.finish(result, user, session)


async def prepare_insert(dt: Any, data: dict[str, Any], row: dict[str, Any], user: str) -> None:
    for extension in extensions():
        await extension.prepare_insert(dt, data, row, user)


async def before_store(dt: Any, row: dict[str, Any], session: Any) -> None:
    for extension in extensions():
        await extension.before_store(dt, row, session)


async def begin_update(
    doctype: str, existing: dict[str, Any], data: dict[str, Any], user: str
) -> UpdateScopes:
    scopes = []
    for extension in extensions():
        scope = await extension.begin_update(doctype, existing, data, user)
        if scope is not None:
            scopes.append(scope)
    return UpdateScopes(scopes)


async def check_delete(doctype: str, existing: dict[str, Any], user: str) -> None:
    for extension in extensions():
        await extension.check_delete(doctype, existing, user)


async def after_write(event: str, session: Any, doctype: str, row: dict[str, Any]) -> None:
    for extension in extensions():
        await extension.after_write(event, session, doctype, row)


async def changes_recorded(**kwargs: Any) -> None:
    for extension in extensions():
        await extension.changes_recorded(**kwargs)


async def doc_progress(doctype: str, doc_id: str, payload: dict[str, Any]) -> None:
    for extension in extensions():
        await extension.doc_progress(doctype, doc_id, payload)
