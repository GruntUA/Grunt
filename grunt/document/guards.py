"""Write guards - app code that may veto changing or deleting a document.

``doc_events`` handlers are best-effort (an exception is logged, the save goes
on), so an app that must *forbid* a write registers a guard instead::

    write_guards = ["esign.guards.protect_signed"]

``guard(action, doctype, existing, changes, user)`` is awaited before the
write, after the permission and workflow checks: *action* is "update" or
"delete", *existing* the stored document, *changes* the submitted fields
(``{}`` for a delete). A guard rejects with ``grunt.throw`` - the message goes
back to the client as the save error. The system user (fixtures, imports,
migrations) is never guarded.
"""

import inspect
from collections.abc import Callable
from typing import Any

from grunt.errors import ApplicationError
lazy from grunt.auth.doctypes.User.user import SYSTEM_USER, User

_GUARDS: list[Callable[..., Any]] = []


def register_write_guard(fn: Callable[..., Any]) -> None:
    if fn not in _GUARDS:
        _GUARDS.append(fn)


async def check_write(
    action: str, doctype: str, existing: dict[str, Any], changes: dict[str, Any], user: User
) -> None:
    if not _GUARDS or user.email == SYSTEM_USER.email:
        return
    try:
        for guard in _GUARDS:
            result = guard(action, doctype, existing, changes, user)
            if inspect.isawaitable(result):
                await result
    except ApplicationError as e:
        raise e.to_api_error() from e
