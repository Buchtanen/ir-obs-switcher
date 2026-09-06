"""Shared local-LLM gate: live polish preempts prepared generate."""

from __future__ import annotations

import threading
from collections.abc import Callable


class LlmPriorityLane:
    """One GPU/Ollama queue. Live event polish always owns the lane.

    Prepared filler may start only while no live polish is reserved (queued or
    in-flight). The first live reservation preempts prepared work.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live = 0
        self._on_preempt: Callable[[], None] | None = None
        self._on_idle: Callable[[], None] | None = None

    def set_hooks(
        self,
        *,
        on_preempt: Callable[[], None] | None = None,
        on_idle: Callable[[], None] | None = None,
    ) -> None:
        self._on_preempt = on_preempt
        self._on_idle = on_idle

    @property
    def live_count(self) -> int:
        with self._lock:
            return self._live

    def allow_prepared(self) -> bool:
        with self._lock:
            return self._live == 0

    def request_live(self) -> None:
        """Reserve the lane for one live (non-prepared) polish."""
        first = False
        with self._lock:
            self._live += 1
            first = self._live == 1
        if first:
            hook = self._on_preempt
            if hook is not None:
                hook()

    def release_live(self) -> None:
        idle = False
        with self._lock:
            if self._live > 0:
                self._live -= 1
            idle = self._live == 0
        if idle:
            hook = self._on_idle
            if hook is not None:
                hook()
