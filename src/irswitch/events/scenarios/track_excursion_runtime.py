"""ScenarioEngine publisher for the native Track Excursion feature source.

The detector still owns holds and evidence. This module is the only path that
may enqueue TRACK_EXCURSION speech. Causes stay unknown; candidates are logged.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from irswitch.events.envelope import EventEnvelope
from irswitch.events.scenarios.engine import (
    ActionEffect,
    ActionFn,
    EpisodeMemory,
    GuardFn,
    ScenarioDefinition,
    ScenarioEngine,
    ScenarioFrame,
    ScenarioTrace,
)
from irswitch.events.scenarios.loader import load_scenario_definition
from irswitch.events.scenarios.model import (
    GuardDecision,
    GuardResult,
    ScenarioBeat,
    ScenarioTransition,
)
from irswitch.events.scenarios.track_excursion import SCENARIO_ID, _scope
from irswitch.overlay.models import RaceState

logger = logging.getLogger(__name__)

DEFINITION_PATH = Path(__file__).with_name("data") / "track_excursion_v1.json"
_BEAT_KEYS = (
    "offtrack",
    "stopped",
    "track_rejoined",
    "motion_restored",
    "tow_started_race",
    "pit_return_observed",
    "pace_loss_sustained",
    "normal_running_resumed",
)
_CAUSE_CANDIDATES = (
    "loss_of_control",
    "slide",
    "spin",
    "contact_vehicle",
    "contact_barrier",
    "braking_overshoot",
    "avoidance_maneuver",
    "control_regained",
    "damage",
    "reset_to_pits",
)


def _pending(frame: ScenarioFrame) -> tuple[str, ...]:
    raw = frame.observations.get("pending_beats")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(item) for item in raw if item)


def _flag_guard(beat_id: str, reason_hit: str, reason_miss: str) -> GuardFn:
    def guard(
        frame: ScenarioFrame,
        _memory: EpisodeMemory,
        _definition: ScenarioDefinition,
        _transition: ScenarioTransition,
    ) -> GuardResult:
        if beat_id in _pending(frame):
            return GuardResult(GuardDecision.MATCH, 1.0, reason_hit, (beat_id,))
        return GuardResult(GuardDecision.NO_MATCH, 1.0, reason_miss, (beat_id,))

    return guard


def _emit_action(beat_id: str) -> ActionFn:
    def action(
        frame: ScenarioFrame,
        memory: EpisodeMemory,
        definition: ScenarioDefinition,
        transition: ScenarioTransition,
    ) -> ActionEffect:
        spec = next(item for item in definition.emissions.values() if item.beat_id == beat_id)
        metrics: dict[str, object] = {
            "beatId": beat_id,
            "parentStoryId": memory.episode_id,
            "episodeId": memory.episode_id,
            "cause": "unknown",
            "damage": "unknown",
            "reason": transition.reason,
        }
        extra = frame.observations.get("feature_metrics")
        if isinstance(extra, Mapping):
            metrics.update({str(key): extra[key] for key in extra})
        return ActionEffect(
            beats=(
                ScenarioBeat(
                    definition.scenario_id,
                    definition.scenario_version,
                    memory.episode_id,
                    memory.episode_id,
                    spec.beat_id,
                    spec.event_type,
                    spec.phase,
                    spec.priority or 90,
                    1.0,
                    transition.reason,
                    metrics,
                ),
            )
        )

    return action


def excursion_handlers() -> tuple[dict[str, GuardFn], dict[str, ActionFn]]:
    guards = {
        "excursion_offtrack_ready": _flag_guard("offtrack", "offtrack_ready", "offtrack_absent"),
        "excursion_stopped_ready": _flag_guard("stopped", "stopped_ready", "stopped_absent"),
        "excursion_rejoined_ready": _flag_guard(
            "track_rejoined", "rejoined_ready", "rejoined_absent"
        ),
        "excursion_motion_ready": _flag_guard("motion_restored", "motion_ready", "motion_absent"),
        "excursion_tow_ready": _flag_guard("tow_started_race", "tow_ready", "tow_absent"),
        "excursion_pit_ready": _flag_guard("pit_return_observed", "pit_ready", "pit_absent"),
        "excursion_pace_loss_ready": _flag_guard(
            "pace_loss_sustained", "pace_loss_ready", "pace_loss_absent"
        ),
        "excursion_pace_ok_ready": _flag_guard(
            "normal_running_resumed", "pace_ok_ready", "pace_ok_absent"
        ),
    }
    actions = {
        "emit_excursion_offtrack": _emit_action("offtrack"),
        "emit_excursion_stopped": _emit_action("stopped"),
        "emit_excursion_rejoined": _emit_action("track_rejoined"),
        "emit_excursion_motion": _emit_action("motion_restored"),
        "emit_excursion_tow": _emit_action("tow_started_race"),
        "emit_excursion_pit": _emit_action("pit_return_observed"),
        "emit_excursion_pace_loss": _emit_action("pace_loss_sustained"),
        "emit_excursion_pace_ok": _emit_action("normal_running_resumed"),
    }
    return guards, actions


def load_track_excursion_engine() -> ScenarioEngine:
    definition = load_scenario_definition(DEFINITION_PATH)
    guards, actions = excursion_handlers()
    return ScenarioEngine(definition, guards=guards, actions=actions)


class TrackExcursionEngine:
    """Gate detector envelopes through ScenarioEngine. Fail-soft: publish nothing."""

    def __init__(self) -> None:
        self._engine: ScenarioEngine | None = None
        self._pending_traces: list[dict[str, object]] = []
        self.reset()

    def reset(self) -> None:
        try:
            self._engine = load_track_excursion_engine()
        except Exception:
            logger.warning("Track excursion ScenarioEngine failed to load", exc_info=True)
            self._engine = None
        self._pending_traces = []

    def publish(
        self, detected: list[EventEnvelope], state: RaceState, now: float
    ) -> list[EventEnvelope]:
        if self._engine is None or self._engine.disabled:
            self.reset()
        if self._engine is None:
            return []
        scope = _scope(state)
        if scope is None:
            return []
        pending = [
            str(event.metrics.get("beatId"))
            for event in detected
            if event.metrics.get("beatId") in _BEAT_KEYS
        ]
        if "offtrack" in pending and self._engine.memory.state != "IDLE":
            self.reset()
            if self._engine is None:
                return []
        metrics = dict(detected[0].metrics) if detected else {}
        frame = ScenarioFrame(
            now=now,
            scope=scope,
            mode=str(state.overlay_mode or ""),
            connected=bool(state.connected),
            observations={
                "pending_beats": pending,
                "feature_metrics": metrics,
                "cause": "unknown",
                "cause_candidates": _CAUSE_CANDIDATES,
            },
        )
        before = len(self._engine.traces)
        beats = self._engine.tick(frame)
        traces = self._engine.traces[before:]
        allowed = {beat.beat_id for beat in beats}
        published = [event for event in detected if event.metrics.get("beatId") in allowed]
        self._note_traces(traces)
        self._log_tick(pending, allowed, traces, now)
        return published

    def drain_traces(self) -> list[dict[str, object]]:
        rows = self._pending_traces
        self._pending_traces = []
        return rows

    def _note_traces(self, traces: tuple[ScenarioTrace, ...]) -> None:
        for item in traces:
            self._pending_traces.append(
                {
                    "action": "engine_transition",
                    "scenarioId": SCENARIO_ID,
                    "at": item.at,
                    "transitionId": item.transition_id,
                    "from": item.state,
                    "to": item.target,
                    "reason": item.reason,
                    "parentStoryId": item.episode_id,
                    "cause": "unknown",
                }
            )

    def _log_tick(
        self,
        pending: list[str],
        allowed: set[str],
        traces: tuple[ScenarioTrace, ...],
        now: float,
    ) -> None:
        dropped = [beat for beat in pending if beat not in allowed]
        if dropped:
            logger.info(
                "track_excursion engine unmatched beats=%s allowed=%s cause=unknown at=%.3f",
                dropped,
                sorted(allowed),
                now,
            )
        if "offtrack" in allowed:
            logger.info(
                "track_excursion engine opened cause=unknown candidates=%s",
                ",".join(_CAUSE_CANDIDATES),
            )
        for item in traces:
            logger.info(
                "track_excursion engine %s->%s reason=%s cause=unknown",
                item.state,
                item.target,
                item.reason,
            )
