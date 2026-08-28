"""Bounded system metric history (10s avg / 60s max)."""

from __future__ import annotations

from collections import deque


class MetricHistory:
    def __init__(self, keep_seconds: float = 60.0) -> None:
        self.keep_seconds = keep_seconds
        self._samples: deque[tuple[float, float]] = deque()

    def add(self, timestamp: float, value: float | None) -> None:
        if value is None:
            return
        self._samples.append((timestamp, float(value)))
        cutoff = timestamp - self.keep_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def average(self, window_s: float, now: float) -> float | None:
        cutoff = now - window_s
        values = [v for t, v in self._samples if t >= cutoff]
        if not values:
            return None
        return sum(values) / len(values)

    def maximum(self, window_s: float, now: float) -> float | None:
        cutoff = now - window_s
        values = [v for t, v in self._samples if t >= cutoff]
        if not values:
            return None
        return max(values)
