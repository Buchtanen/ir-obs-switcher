"""Rolling HR baseline over a bounded time window."""

from __future__ import annotations

from collections import deque


class HeartRateHistory:
    def __init__(self, window_seconds: float = 300.0) -> None:
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, timestamp: float, bpm: int) -> None:
        self._samples.append((timestamp, bpm))
        cutoff = timestamp - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def baseline(self) -> float | None:
        if not self._samples:
            return None
        return sum(bpm for _, bpm in self._samples) / len(self._samples)
