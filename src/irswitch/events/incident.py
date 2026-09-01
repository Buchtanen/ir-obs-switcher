"""Incident count edge with configurable minimum delta."""

from __future__ import annotations

from irswitch.iracing.trk_loc import OFF_TRACK
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings, RaceObserverSettings


def classify_incident_branch(state: RaceState) -> str:
    """v1 spoken kinds: OffTrack around the tick → off_track, else unknown.

    Nearby cars are never a spoken kind (metric only). No contact_object.
    """
    if state.player_track_surface == OFF_TRACK:
        return "off_track"
    return "unknown"


def nearby_car_metrics(state: RaceState) -> dict[str, object]:
    """Closest ahead/behind opponent as metrics. Empty when none. Never a kind."""
    candidates: list[OpponentInfo] = []
    if state.opponent_ahead is not None:
        candidates.append(state.opponent_ahead)
    if state.opponent_behind is not None:
        candidates.append(state.opponent_behind)
    if not candidates:
        return {}

    def _gap_key(opp: OpponentInfo) -> float:
        if opp.gap is None:
            return 10_000.0
        return abs(float(opp.gap))

    best = min(candidates, key=_gap_key)
    out: dict[str, object] = {"nearbyCarIdx": best.car_idx}
    if best.gap is not None:
        out["nearbyGap"] = best.gap
    return out


class IncidentEmitter:
    def __init__(
        self,
        events: EventSettings,
        priorities: EventPrioritySettings,
        race_observer: RaceObserverSettings | None = None,
    ) -> None:
        self._min_delta = events.incident_min_delta
        self._priorities = priorities
        self._race_observer = race_observer or RaceObserverSettings()
        self._last: int | None = None

    def apply_settings(self, settings: RaceObserverSettings) -> None:
        self._race_observer = settings

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.incidents is None:
            return []
        prev = self._last
        self._last = state.incidents
        if prev is None or state.incidents <= prev:
            return []
        delta = state.incidents - prev
        if delta < self._min_delta:
            return []
        data: dict[str, object] = {"value": delta, "total": state.incidents}
        if self._race_observer.incident_classify:
            data["branch"] = classify_incident_branch(state)
            data.update(nearby_car_metrics(state))
        return [
            CandidateEvent(
                name="incident",
                channel="alert",
                priority=self._priorities.incident,
                phase="trigger",
                data=data,
            )
        ]
