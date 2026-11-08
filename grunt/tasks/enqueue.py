"""``grunt.enqueue`` - send a background task once the transaction commits.

A task usually reads what the request has just written - the saved document, a
new import, a log row. Sent with ``task.kiq()`` mid-transaction, a worker can
pick it up before the commit and find nothing (or the old row), and a rollback
can't take it back. ``enqueue`` waits for the commit
(:func:`grunt.db.commit.on_commit`); without a transaction it sends at once.

Sending is best-effort, like the rest of after-commit work: an unreachable
broker is logged, not raised into a request that has already committed. A task
that must report a broker failure to the user, or that depends on nothing the
transaction wrote, calls ``.kiq()`` directly.
"""

from typing import Any

from grunt.db.commit import on_commit


def enqueue(task: Any, /, *args: Any, **kwargs: Any) -> None:
    """Send *task* (a TaskIQ task, or one of its kickers) with *args*/*kwargs*
    after the current transaction commits."""

    async def send() -> None:
        await task.kiq(*args, **kwargs)

    on_commit(send)


__all__ = ["enqueue"]
