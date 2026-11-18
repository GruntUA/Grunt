"""cancel_and_wait: the target's cancellation ends there, the caller's does not."""

import asyncio

import pytest

from grunt.utils.aio import cancel_and_wait


async def _slow_cleanup(started: asyncio.Event) -> None:
    try:
        started.set()
        await asyncio.sleep(10)
    finally:
        await asyncio.sleep(0.05)  # yields while it cleans up


@pytest.mark.asyncio
async def test_target_cancellation_is_swallowed():
    started = asyncio.Event()
    task = asyncio.create_task(_slow_cleanup(started))
    await started.wait()
    assert await cancel_and_wait(task) is None
    assert task.cancelled()


@pytest.mark.asyncio
async def test_result_and_other_errors_pass_through():
    async def done() -> int:
        return 7

    task = asyncio.create_task(done())
    await asyncio.sleep(0)
    assert await cancel_and_wait(task) == 7

    async def boom() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            raise RuntimeError("cleanup failed")

    task = asyncio.create_task(boom())
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError):
        await cancel_and_wait(task)


@pytest.mark.asyncio
async def test_caller_cancellation_is_kept():
    started = asyncio.Event()
    target = asyncio.create_task(_slow_cleanup(started))
    await started.wait()
    stopper = asyncio.create_task(cancel_and_wait(target))
    await asyncio.sleep(0.01)  # stopper waits on the target's cleanup
    stopper.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stopper
    assert stopper.cancelled()
