"""Per-minisector reference times for practice/quali delta analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SegmentReferenceTracker:
    """Best segment time per timing point (player session reference)."""

    _best_segments: dict[str, float] = field(default_factory=dict)

    def reset(self) -> None:
        self._best_segments.clear()

    def compare_segment(self, timing_point_id: str, segment_time: float | None) -> float | None:
        """Return delta vs best segment (negative = gain). Updates best when faster."""
        if segment_time is None or segment_time <= 0:
            return None
        prev = self._best_segments.get(timing_point_id)
        if prev is None:
            self._best_segments[timing_point_id] = segment_time
            return None
        delta = segment_time - prev
        if segment_time < prev:
            self._best_segments[timing_point_id] = segment_time
        return delta

    def best_segment(self, timing_point_id: str) -> float | None:
        return self._best_segments.get(timing_point_id)

    def projected_lap_from_segments(
        self, segment_sum: float, segments_seen: int, total: int
    ) -> float | None:
        """Scale partial segment sum to full lap when at least one segment exists."""
        if segments_seen < 1 or total < 1 or segment_sum <= 0:
            return None
        return segment_sum * (total / segments_seen)
