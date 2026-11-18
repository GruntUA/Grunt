"""Small asyncio helpers."""

import asyncio


async def cancel_and_wait[T](task: asyncio.Task[T]) -> T | None:
    """Cancel *task* and wait until it has stopped.

    Its ``CancelledError`` ends here; any other exception it dies with is raised.
    A cancellation of the caller itself while it waits is not swallowed.
    """
    task.cancel()
    caller = asyncio.current_task()
    cancelling = caller.cancelling() if caller else 0
    try:
        return await task
    except asyncio.CancelledError:
        if caller is not None and caller.cancelling() > cancelling:
            raise
        return None
