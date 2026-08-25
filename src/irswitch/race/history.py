"""Closing-rate linear regression over a bounded gap history."""

from __future__ import annotations

from collections import deque


class GapHistory:
    """Rolling (t, gap) samples. Closing rate is -slope of gap vs time."""

    def __init__(self, window_seconds: float = 3.0, max_samples: int = 64) -> None:
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, float]] = deque(maxlen=max_samples)

    def clear(self) -> None:
        self._samples.clear()

    def add(self, timestamp: float, gap: float | None) -> None:
        if gap is None:
            return
        self._samples.append((timestamp, gap))
        cutoff = timestamp - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def closing_rate(self) -> float | None:
        if len(self._samples) < 2:
            return None
        n = len(self._samples)
        mean_t = sum(t for t, _ in self._samples) / n
        mean_g = sum(g for _, g in self._samples) / n
        var_t = sum((t - mean_t) ** 2 for t, _ in self._samples)
        if var_t <= 1e-9:
            return 0.0
        cov = sum((t - mean_t) * (g - mean_g) for t, g in self._samples)
        slope = cov / var_t  # dg/dt; negative means catching up
        return -slope
