"""Named asyncio task registry with replace and cancel support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Track background tasks by name; support replace and clean cancel."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def spawn(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
        *,
        replace: bool = True,
    ) -> asyncio.Task[Any]:
        """
        Create and track a named task.

        If a non-done task with the same name exists:
        - replace=True: cancel it and spawn the new one
        - replace=False: close the new coro and return the existing task
        """
        existing = self._tasks.get(name)
        if existing is not None and not existing.done():
            if not replace:
                coro.close()
                return existing
            existing.cancel()

        task = asyncio.create_task(coro, name=name)
        self._tasks[name] = task
        task.add_done_callback(self._make_done_callback(name))
        return task

    def _make_done_callback(self, name: str):
        def _on_done(task: asyncio.Task[Any]) -> None:
            if self._tasks.get(name) is task:
                self._tasks.pop(name, None)
            # Retrieve exception to avoid "exception was never retrieved"
            if not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    logger.debug("Background task %r finished with error: %s", name, exc)

        return _on_done

    def cancel(self, name: str) -> None:
        """Cancel a single tracked task by name (no-op if missing/done)."""
        task = self._tasks.get(name)
        if task is not None and not task.done():
            task.cancel()

    async def cancel_all(self) -> None:
        """Cancel all tracked tasks and wait until they finish."""
        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def __contains__(self, name: str) -> bool:
        return name in self._tasks

    def __len__(self) -> int:
        return len(self._tasks)
