"""Normalized RaceState input replay harness for Event Engine scenarios.

This module replays JSON fixtures of ``{t, race, bio?}`` ticks through
``EventEngine.tick`` and ``EventManagerV2.submit/tick``, collecting published
V4 ``(monotonic_t, eventType, phase)`` tuples. It is distinct from
``overlay/replay.py``, which replays bus JSONL WS envelopes.

Fixture format (``tests/fixtures/replay_input/*.json``)::

    {
      "name": "scenario label",
      "mode": "RACE",
      "time_tolerance_ms": 0,
      "flags": {
        "event_engine": {"v2_payload": true, "overtake_classifier": true},
        "battle": {"hunting": {"activation_delay": 0.0}}
      },
      "expected": [
        {"eventType": "LAP_COMPLETE", "phase": "RESULT"},
        {"eventType": "HUNTING", "phase": "ENTER"}
      ],
      "ticks": [
        {"t": 0.0, "race": {"connected": true, "lap_completed": 10}},
        {"t": 1.0, "race": {"connected": true, "lap_completed": 11}, "bio": {"connected": true, "bpm": 120}}
      ]
    }

``race`` values are partial ``RaceState`` dicts (only fields needed per scenario).
``bio`` is an optional partial ``BioState`` dict. ``flags`` merges into
``OverlaySettings`` (nested keys supported). ``expected`` is optional metadata
for tests; the harness itself only replays ticks and records outputs.

Monotonic ``now`` for each tick equals the fixture ``t`` field (deterministic).
Per-tick emitter failures are logged and skipped (fail-soft).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, TypeVar, cast

from irswitch.events.engine import EventEngine
from irswitch.events.envelope import EventEnvelope
from irswitch.events.hr_pressure import HrPressureEmitter
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.events.pit_story import PitStoryEmitter
from irswitch.events.practice import PracticeEmitter
from irswitch.events.quali import QualiEmitter
from irswitch.overlay.models import BioState, RaceState
from irswitch.overlay.replay import _bio_from_dict, _race_from_dict
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.timing.reference import SegmentReferenceTracker
from irswitch.race.timing.store import TimingRecord, TimingStore

logger = logging.getLogger(__name__)

ReplayEvent = tuple[float, str, str]

_D = TypeVar("_D")


@dataclass
class ReplayResult:
    """Collected replay output and fixture metadata."""

    name: str
    mode: str
    events: list[ReplayEvent]
    time_tolerance_ms: int = 0

    def event_sequence(self) -> list[tuple[str, str]]:
        return [(event_type, phase) for _, event_type, phase in self.events]


@dataclass
class ReplayInputRunner:
    """Drive EventEngine + EventManagerV2 from normalized input fixtures."""

    overlay: OverlaySettings | None = None
    session_id: str = "replay:0:0"

    def __post_init__(self) -> None:
        self._overlay = self.overlay or OverlaySettings()
        self._timing_store = TimingStore()
        self._segment_ref = SegmentReferenceTracker()
        self._engine: EventEngine | None = None
        self._manager: EventManagerV2 | None = None
        self._build_pipeline()

    def reset_session(self, *, session_id: str | None = None) -> None:
        """Reset emitters and manager state between scenarios."""
        if session_id is not None:
            self.session_id = session_id
        self._timing_store.reset()
        self._segment_ref.reset()
        self._build_pipeline()

    def run_fixture(self, fixture: dict[str, Any]) -> ReplayResult:
        """Replay an in-memory fixture dict."""
        overlay = _overlay_from_fixture_flags(self._overlay, fixture.get("flags"))
        self._overlay = overlay
        self._build_pipeline()
        assert self._engine is not None and self._manager is not None

        mode = str(fixture.get("mode") or "RACE")
        tolerance = int(fixture.get("time_tolerance_ms") or 0)
        ticks = fixture.get("ticks") or []
        events: list[ReplayEvent] = []

        for tick in ticks:
            now = float(tick.get("t", 0.0))
            race_raw = tick.get("race") or {}
            bio_raw = tick.get("bio")
            state = _race_from_dict(race_raw)
            if "overlay_mode" not in race_raw:
                state = replace(state, overlay_mode=mode)
            bio = _bio_from_dict(bio_raw) if bio_raw else None
            self._ingest_timing_rows(tick.get("timing"))

            try:
                events.extend(self._tick_once(state, now, bio=bio, mode=mode))
            except Exception:
                logger.warning("Replay tick failed at t=%s", now, exc_info=True)
        return ReplayResult(
            name=str(fixture.get("name") or ""),
            mode=mode,
            events=events,
            time_tolerance_ms=tolerance,
        )

    def run_path(self, path: str | Path) -> ReplayResult:
        fixture = load_fixture(path)
        return self.run_fixture(fixture)

    def _build_pipeline(self) -> None:
        overlay = _overlay_with_v2(self._overlay)
        self._engine = EventEngine(overlay)
        self._register_optional_emitters(overlay)
        self._manager = EventManagerV2(overlay.events, session_id=self.session_id)
        self._manager.set_session_id(self.session_id)

    def _register_optional_emitters(self, overlay: OverlaySettings) -> None:
        assert self._engine is not None
        pri = overlay.events.priorities
        if overlay.event_engine.practice:
            self._engine.register(
                PracticeEmitter(
                    self._timing_store,
                    self._segment_ref,
                    overlay.events,
                    pri,
                )
            )
        if overlay.event_engine.quali_projection:
            self._engine.register(
                QualiEmitter(
                    self._timing_store,
                    self._segment_ref,
                    overlay.events,
                    pri,
                )
            )
        if overlay.event_engine.pit_story:
            self._engine.register(PitStoryEmitter(pri))
        if overlay.event_engine.hr_pressure:
            self._engine.register(HrPressureEmitter(pri))

    def _ingest_timing_rows(self, rows: Any) -> None:
        if not rows:
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            point = str(row.get("timing_point_id") or row.get("timingPointId") or "")
            if not point:
                continue
            segment_time = row.get("segment_time", row.get("segmentTime"))
            record = TimingRecord(
                car_id=str(row.get("car_id") or row.get("carId") or "player"),
                lap_number=int(row.get("lap_number") or row.get("lapNumber") or 1),
                timing_point_id=point,
                crossing_timestamp=float(row.get("crossing_timestamp") or row.get("t") or 0.0),
                segment_time=float(segment_time) if segment_time is not None else None,
                valid_at_crossing=bool(row.get("valid_at_crossing", row.get("valid", True))),
            )
            self._timing_store.append_record(record)

    def _tick_once(
        self,
        state: RaceState,
        now: float,
        *,
        bio: BioState | None,
        mode: str,
    ) -> list[ReplayEvent]:
        assert self._engine is not None and self._manager is not None
        out: list[ReplayEvent] = []
        sid = _session_id_from_state(state) or self.session_id
        self._manager.set_session_id(sid)
        self._manager.update_pit_state(bool(state.on_pit_road), now)

        try:
            candidates = self._engine.tick(state, now, bio)
        except Exception:
            logger.warning("EventEngine.tick failed at t=%s", now, exc_info=True)
            candidates = []

        for candidate in candidates:
            try:
                _, envelopes = self._manager.submit(candidate, now, mode=mode)
                out.extend(_envelopes_to_replay_events(now, envelopes))
            except Exception:
                logger.warning(
                    "EventManagerV2.submit failed for %s at t=%s",
                    candidate.name,
                    now,
                    exc_info=True,
                )

        try:
            for _, envelopes in self._manager.tick(now, mode=mode):
                out.extend(_envelopes_to_replay_events(now, envelopes))
        except Exception:
            logger.warning("EventManagerV2.tick failed at t=%s", now, exc_info=True)
        return out


def run_scenario(
    path: str | Path,
    overlay_settings: OverlaySettings | None = None,
) -> ReplayResult:
    """Load a fixture file and replay it."""
    runner = ReplayInputRunner(overlay=overlay_settings)
    return runner.run_path(path)


def load_fixture(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return cast(dict[str, Any], json.load(handle))


def reset_session(runner: ReplayInputRunner, *, session_id: str = "replay:0:0") -> None:
    """Public helper to reset runner state between scenarios."""
    runner.reset_session(session_id=session_id)


def assert_expected_sequence(
    result: ReplayResult,
    expected: list[dict[str, str]],
    *,
    time_tolerance_ms: int | None = None,
) -> None:
    """Assert ``expected`` is a subsequence of ``(eventType, phase)`` tuples."""
    tolerance = result.time_tolerance_ms if time_tolerance_ms is None else time_tolerance_ms
    actual = result.event_sequence()
    expected_pairs = [(row["eventType"], row["phase"]) for row in expected]
    if not _is_subsequence(expected_pairs, actual):
        raise AssertionError(
            f"expected subsequence {expected_pairs!r} not found in actual {actual!r} "
            f"(tolerance_ms={tolerance})"
        )


def _is_subsequence(needle: list[tuple[str, str]], haystack: list[tuple[str, str]]) -> bool:
    if not needle:
        return True
    idx = 0
    for pair in haystack:
        if pair == needle[idx]:
            idx += 1
            if idx == len(needle):
                return True
    return False


def _envelopes_to_replay_events(now: float, envelopes: list[EventEnvelope]) -> list[ReplayEvent]:
    return [(now, env.event_type, env.phase) for env in envelopes]


def _session_id_from_state(state: RaceState) -> str:
    sid = state.subsession_id or "unknown"
    num = state.session_num if state.session_num is not None else 0
    return f"{sid}:{num}"


def _overlay_with_v2(overlay: OverlaySettings) -> OverlaySettings:
    """Replay always drives the V4 manager path."""
    ee = overlay.event_engine
    if ee.v2_payload:
        return overlay
    return replace(overlay, event_engine=replace(ee, v2_payload=True))


def _overlay_from_fixture_flags(
    base: OverlaySettings,
    flags: dict[str, Any] | None,
) -> OverlaySettings:
    if not flags:
        return _overlay_with_v2(base)
    merged = dict(flags)
    ee = merged.get("event_engine")
    if isinstance(ee, dict):
        ee = dict(ee)
        ee.setdefault("v2_payload", True)
        merged["event_engine"] = ee
    else:
        merged["event_engine"] = {"v2_payload": True}
    return _overlay_with_v2(_merge_dataclass(base, merged))


def _merge_dataclass(instance: _D, overrides: dict[str, Any]) -> _D:
    if not overrides:
        return instance
    if not is_dataclass(instance):
        return instance
    updates: dict[str, Any] = {}
    type_hints = {f.name: f for f in fields(instance)}
    for key, value in overrides.items():
        if key not in type_hints:
            continue
        current = getattr(instance, key)
        if is_dataclass(current) and isinstance(value, dict):
            updates[key] = _merge_dataclass(current, value)
        else:
            updates[key] = value
    if not updates:
        return instance
    return cast(_D, replace(cast(Any, instance), **updates))
