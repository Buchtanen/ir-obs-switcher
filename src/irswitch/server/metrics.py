"""Metrics collection for the service."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = None  # Lazy import to avoid circular dependency


@dataclass
class MetricsCollector:
    """Collects and tracks service metrics."""

    # Counters
    scene_switches_total: int = 0
    errors_total: defaultdict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    # Latency tracking
    scene_switch_latencies_ms: list[float] = field(default_factory=list)
    _max_latency_samples: int = 100  # Keep last 100 samples

    # Timestamps
    start_time: float = field(default_factory=time.monotonic)
    iracing_connected_ts: Optional[float] = None
    iracing_total_connected_time: float = 0.0  # Cumulative connected time in seconds
    obs_connected_ts: Optional[float] = None
    obs_total_connected_time: float = 0.0  # Cumulative connected time in seconds
    stream_started_ts: Optional[float] = None
    stream_total_time: float = 0.0  # Cumulative stream time in seconds

    def record_scene_switch(self, latency_ms: float) -> None:
        """Record a scene switch with latency."""
        self.scene_switches_total += 1
        self.scene_switch_latencies_ms.append(latency_ms)
        # Keep only last N samples
        if len(self.scene_switch_latencies_ms) > self._max_latency_samples:
            self.scene_switch_latencies_ms.pop(0)

    def record_error(self, error_type: str) -> None:
        """Record an error by type."""
        self.errors_total[error_type] += 1

    def set_iracing_connected(self, connected: bool) -> None:
        """Update iRacing connection state."""
        now = time.monotonic()
        if connected and self.iracing_connected_ts is None:
            # Starting new connection - begin tracking
            self.iracing_connected_ts = now
        elif not connected and self.iracing_connected_ts is not None:
            # Connection lost - add elapsed time to total
            elapsed = now - self.iracing_connected_ts
            self.iracing_total_connected_time += elapsed
            self.iracing_connected_ts = None

    def set_obs_connected(self, connected: bool) -> None:
        """Update OBS connection state."""
        now = time.monotonic()
        if connected and self.obs_connected_ts is None:
            # Starting new connection - begin tracking
            self.obs_connected_ts = now
        elif not connected and self.obs_connected_ts is not None:
            # Connection lost - add elapsed time to total
            elapsed = now - self.obs_connected_ts
            self.obs_total_connected_time += elapsed
            self.obs_connected_ts = None

    def get_uptime_seconds(self) -> float:
        """Get service uptime in seconds."""
        return time.monotonic() - self.start_time

    def get_iracing_connected_duration_seconds(
        self,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Get iRacing connection duration in seconds.

        Returns:
            Tuple of (cumulative_seconds, current_session_seconds)
        """
        now = time.monotonic()
        current_session = None
        if self.iracing_connected_ts is not None:
            current_session = now - self.iracing_connected_ts

        cumulative = self.iracing_total_connected_time
        if current_session is not None:
            cumulative += current_session

        if cumulative > 0:
            return (cumulative, current_session)
        else:
            return (None, None)

    def get_obs_connected_duration_seconds(
        self,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Get OBS connection duration in seconds.

        Returns:
            Tuple of (cumulative_seconds, current_session_seconds)
        """
        now = time.monotonic()
        current_session = None
        if self.obs_connected_ts is not None:
            current_session = now - self.obs_connected_ts

        cumulative = self.obs_total_connected_time
        if current_session is not None:
            cumulative += current_session

        if cumulative > 0:
            return (cumulative, current_session)
        else:
            return (None, None)

    def set_streaming(self, is_streaming: bool) -> None:
        """Update streaming state."""
        now = time.monotonic()
        if is_streaming and self.stream_started_ts is None:
            # Stream started - begin tracking
            self.stream_started_ts = now
        elif not is_streaming and self.stream_started_ts is not None:
            # Stream stopped - add elapsed time to total
            elapsed = now - self.stream_started_ts
            self.stream_total_time += elapsed
            self.stream_started_ts = None

    def get_stream_duration_seconds(self) -> tuple[Optional[float], Optional[float]]:
        """
        Get stream duration in seconds.

        Returns:
            Tuple of (cumulative_seconds, current_session_seconds)
        """
        now = time.monotonic()
        current_session = None
        if self.stream_started_ts is not None:
            current_session = now - self.stream_started_ts

        cumulative = self.stream_total_time
        if current_session is not None:
            cumulative += current_session

        if cumulative > 0:
            return (cumulative, current_session)
        else:
            return (None, None)

    def get_scene_switch_latency_avg_ms(self) -> Optional[float]:
        """Get average scene switch latency in milliseconds."""
        if not self.scene_switch_latencies_ms:
            return None
        return sum(self.scene_switch_latencies_ms) / len(self.scene_switch_latencies_ms)

    def to_dict(self, current_state: Optional[object] = None) -> dict:
        """
        Convert metrics to dictionary.

        Args:
            current_state: Optional SwitchState to include current state info
        """
        result = {
            "scene_switches_total": self.scene_switches_total,
            "uptime_seconds": self.get_uptime_seconds(),
            "errors_total": dict(self.errors_total),
        }

        # Latency
        avg_latency = self.get_scene_switch_latency_avg_ms()
        if avg_latency is not None:
            result["scene_switch_latency_avg_ms"] = avg_latency

        # Connection durations (cumulative and current session)
        iracing_cumulative, iracing_current = (
            self.get_iracing_connected_duration_seconds()
        )
        if iracing_cumulative is not None:
            result["iracing_connected_duration_seconds"] = iracing_cumulative
            result["iracing_connected_duration_current_session_seconds"] = (
                iracing_current
            )

        obs_cumulative, obs_current = self.get_obs_connected_duration_seconds()
        if obs_cumulative is not None:
            result["obs_connected_duration_seconds"] = obs_cumulative
            result["obs_connected_duration_current_session_seconds"] = obs_current

        # Stream duration (cumulative and current session)
        stream_cumulative, stream_current = self.get_stream_duration_seconds()
        if stream_cumulative is not None:
            result["stream_duration_seconds"] = stream_cumulative
            result["stream_duration_current_session_seconds"] = stream_current

        # Current state info
        if current_state is not None:
            try:
                result["current_state"] = {
                    "mode": (
                        current_state.mode.value
                        if hasattr(current_state, "mode")
                        else None
                    ),
                    "scene": (
                        current_state.current_scene
                        if hasattr(current_state, "current_scene")
                        else None
                    ),
                    "autoswitch": (
                        current_state.autoswitch
                        if hasattr(current_state, "autoswitch")
                        else None
                    ),
                }
            except Exception:
                pass

        return result


# Global metrics instance
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def reset_metrics() -> None:
    """Reset global metrics (for testing)."""
    global _metrics
    _metrics = None
