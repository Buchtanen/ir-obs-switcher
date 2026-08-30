"""S1/S2(/S3) split callouts for Practice and Quali (not Race).

HUD emits every valid sector crossing as ``sector_split``. Commentary speak is
gated separately (``commentary.sector_speak``) via notability annotations and
``SectorBestEmitter`` for session-best improvements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing.store import TimingStore

_TIMING_MODES = frozenset({"PRACTICE", "QUALIFYING"})

# Match PracticeEmitter gain threshold: smaller improvements stay quiet for speak.
NOTABLE_GAIN_S = 0.05


def is_sector_point_id(point_id: str) -> bool:
    if len(point_id) < 2 or point_id[0] != "S":
        return False
    return point_id[1:].isdigit()


@dataclass(frozen=True)
class SectorEval:
    """Result of comparing one sector segment to the session best."""

    delta: float | None
    is_best: bool
    notable: bool
    is_improvement: bool


@dataclass
class SectorBestTracker:
    """Per-sector session bests for notability / SECTOR_BEST.

    Independent of practice/quali ``SegmentReferenceTracker`` so minisector
    math does not fight sector-speak guardrails.
    """

    _best_segments: dict[str, float] = field(default_factory=dict)

    def reset(self) -> None:
        self._best_segments.clear()

    def evaluate(self, timing_point_id: str, segment_time: float) -> SectorEval:
        """Update best when faster or first; return delta / notability flags."""
        if segment_time <= 0:
            return SectorEval(delta=None, is_best=False, notable=False, is_improvement=False)
        prev = self._best_segments.get(timing_point_id)
        if prev is None:
            self._best_segments[timing_point_id] = segment_time
            return SectorEval(delta=None, is_best=True, notable=False, is_improvement=False)
        delta = segment_time - prev
        is_improvement = segment_time < prev
        if is_improvement:
            self._best_segments[timing_point_id] = segment_time
        notable = delta <= -NOTABLE_GAIN_S
        return SectorEval(
            delta=delta,
            is_best=is_improvement,
            notable=notable,
            is_improvement=is_improvement,
        )


def _sector_data(
    *,
    timing_point_id: str,
    segment_time: float,
    lap: int | None,
    eval_: SectorEval | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "sector": timing_point_id,
        "timingPointId": timing_point_id,
        "segmentTime": segment_time,
        "lap": lap,
        "notable": bool(eval_ and eval_.notable),
        "isBest": bool(eval_ and eval_.is_best),
    }
    if eval_ is not None and eval_.delta is not None:
        data["delta"] = round(eval_.delta, 3)
    return data


class SectorSplitEmitter:
    """Absolute sector times for the HUD; annotates notability for commentary."""

    def __init__(
        self,
        store: TimingStore,
        events: EventSettings,
        priorities: EventPrioritySettings,
        tracker: SectorBestTracker | None = None,
    ) -> None:
        self._store = store
        self._events = events
        self._priorities = priorities
        self._cursor = 0
        # Own tracker when none shared — annotations must not depend on SECTOR_BEST.
        self._tracker = tracker if tracker is not None else SectorBestTracker()

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.session_finished:
            return []
        if state.overlay_mode not in _TIMING_MODES:
            return []
        pending = [
            r
            for r in self._store.records_since(self._cursor)
            if r.car_id == "player" and r.valid_at_crossing
        ]
        self._cursor = self._store.append_count
        out: list[CandidateEvent] = []
        for record in pending:
            if not is_sector_point_id(record.timing_point_id) or record.segment_time is None:
                continue
            eval_ = self._tracker.evaluate(record.timing_point_id, record.segment_time)
            out.append(
                CandidateEvent(
                    name="sector_split",
                    channel="timing",
                    priority=self._priorities.gain_found,
                    phase="trigger",
                    data=_sector_data(
                        timing_point_id=record.timing_point_id,
                        segment_time=record.segment_time,
                        lap=record.lap_number,
                        eval_=eval_,
                    ),
                    duration=self._events.lap_duration,
                    cooldown=self._events.lap_cooldown,
                )
            )
        return out


class SectorBestEmitter:
    """Session-best sector improvement → ``sector_best`` (catalog ``SECTOR_BEST``).

    Uses a **separate** tracker from ``SectorSplitEmitter`` so registration order
    cannot swallow improvements (both see the same crossing stream).
    """

    def __init__(
        self,
        store: TimingStore,
        events: EventSettings,
        priorities: EventPrioritySettings,
        tracker: SectorBestTracker | None = None,
    ) -> None:
        self._store = store
        self._events = events
        self._priorities = priorities
        self._tracker = tracker if tracker is not None else SectorBestTracker()
        self._cursor = 0

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.session_finished:
            return []
        if state.overlay_mode not in _TIMING_MODES:
            return []
        pending = [
            r
            for r in self._store.records_since(self._cursor)
            if r.car_id == "player" and r.valid_at_crossing
        ]
        self._cursor = self._store.append_count
        out: list[CandidateEvent] = []
        for record in pending:
            if not is_sector_point_id(record.timing_point_id) or record.segment_time is None:
                continue
            eval_ = self._tracker.evaluate(record.timing_point_id, record.segment_time)
            if not eval_.is_improvement:
                continue
            out.append(
                CandidateEvent(
                    name="sector_best",
                    channel="timing",
                    priority=self._priorities.personal_best,
                    phase="trigger",
                    data=_sector_data(
                        timing_point_id=record.timing_point_id,
                        segment_time=record.segment_time,
                        lap=record.lap_number,
                        eval_=eval_,
                    ),
                    duration=self._events.lap_duration,
                    cooldown=self._events.lap_cooldown,
                )
            )
        return out
