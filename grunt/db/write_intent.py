"""SQLite transaction mode: ``BEGIN IMMEDIATE`` for work that is going to write.

A plain (deferred) ``BEGIN`` starts as a reader. When it later writes and
another process committed in between, SQLite in WAL mode cannot upgrade the
stale snapshot and fails *immediately* with "database is locked" - the 30 s
``busy_timeout`` never gets a chance. With two processes writing (web server +
task worker) this is routine. ``BEGIN IMMEDIATE`` takes the write lock up
front, so a competing writer simply waits for it.

Reads keep the deferred ``BEGIN`` - under WAL they never block each other.
Which work intends to write:

* HTTP requests other than GET/HEAD/OPTIONS (``SiteContextMiddleware``);
* everything in the task worker (``grunt.tasks.worker`` sets the process
  default) - so a task must not hold a transaction open across slow network
  I/O (SMTP, IMAP): commit before it.

PostgreSQL ignores all of this.
"""

from __future__ import annotations

from contextvars import ContextVar

_write_intent: ContextVar[bool | None] = ContextVar("sqlite_write_intent", default=None)
_process_default = False

READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def set_write_intent(value: bool) -> None:
    """Mark the current context (request, task) as going to write - or not."""
    _write_intent.set(value)


def set_process_default(value: bool) -> None:
    """Default for contexts that never called :func:`set_write_intent`."""
    global _process_default
    _process_default = value


def begin_statement() -> str:
    intent = _write_intent.get()
    return "BEGIN IMMEDIATE" if (_process_default if intent is None else intent) else "BEGIN"
