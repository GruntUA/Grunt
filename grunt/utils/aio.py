"""Small asyncio helpers."""

import asyncio
from contextlib import suppress


async def cancel_and_wait[T](task: asyncio.Task[T]) -> T | None:
    """Cancel *task* and wait until it has stopped.

    Its ``CancelledError`` ends here; any other exception it dies with is raised.
    """
    task.cancel()
    with suppress(asyncio.CancelledError):
        return await task
    return None
