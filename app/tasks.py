import asyncio
import logging

log = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task | None:
    """Creates a strongly-referenced task; logs and removes it when done."""
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        log.error("Background task spawn failed (no running event loop)")
        coro.close()
        return None

    _tasks.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task):
    _tasks.discard(task)
    if not task.cancelled() and task.exception():
        log.error("Background task failed: %r", task.exception())


async def cancel_all():
    """Cancels every tracked task and waits for them to finish."""
    if not _tasks:
        return
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
