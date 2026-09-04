"""Kernel timing/identity tests; these do not claim an observation replay."""

from __future__ import annotations

from dataclasses import replace

import pytest

from irswitch.events.scenarios.engine import (
    ActionEffect,
    ScenarioEngine,
    ScenarioFrame,
)
from irswitch.events.scenarios.loader import parse_scenario_definition
from irswitch.events.scenarios.model import (
    EpisodeScope,
    GuardDecision,
    GuardResult,
    ScenarioBeat,
)


def _definition():
    return parse_scenario_definition(
        {
            "schemaVersion": 1,
            "scenarioId": "test_story",
            "scenarioVersion": 1,
            "scope": {"overlayModes": ["RACE"], "subject": "hero", "requiresConnected": True},
            "identity": {
                "fields": [
                    "subsession_id",
                    "session_num",
                    "run_epoch",
                    "player_car_idx",
                    "episode_sequence",
                ],
                "episodeIdTemplate": "scenario:{scenarioId}:session:{subsession_id}:{session_num}:run:{run_epoch}:hero:{player_car_idx}:episode:{episode_sequence}",
                "parentStoryId": "episode_id",
                "beatCorrelationTemplate": "{episode_id}:beat:{beat_id}",
            },
            "parameters": {},
            "observations": {
                "speed": {
                    "field": "RaceState.speed_mps",
                    "unit": "meters_per_second",
                    "maxAgeS": 0.5,
                    "missingPolicy": "unknown",
                }
            },
            "states": [
                {"id": "IDLE", "initial": True, "terminal": False, "meaning": "No episode"},
                {"id": "ACTIVE", "initial": False, "terminal": False, "meaning": "Off track"},
                {"id": "DONE", "initial": False, "terminal": True, "meaning": "Recovered"},
            ],
            "transitions": [
                {
                    "id": "start",
                    "order": 10,
                    "from": ["IDLE"],
                    "to": "ACTIVE",
                    "guard": "incident_count_rising",
                    "holdS": 0.2,
                    "actions": ["create_episode", "emit_incident_if_narratable"],
                    "reason": "start_confirmed",
                },
                {
                    "id": "close",
                    "order": 20,
                    "from": ["ACTIVE"],
                    "to": "DONE",
                    "guard": "on_track_motion_held",
                    "holdS": 0.6,
                    "actions": ["emit_back_under_way"],
                    "reason": "recovery_confirmed",
                },
            ],
            "emissions": {
                "root": {
                    "beatId": "root",
                    "eventType": "INCIDENT",
                    "phase": "RESULT",
                    "channel": "alert",
                    "priority": 80,
                },
                "recovery": {
                    "beatId": "recovery",
                    "eventType": "BACK_UNDER_WAY",
                    "phase": "RESULT",
                    "channel": "commentary_only",
                    "priority": 68,
                },
            },
        }
    )


def _frame(
    now: float,
    *,
    trigger: object = False,
    moving: object = False,
    run: int = 0,
    connected: bool = True,
):
    return ScenarioFrame(
        now=now,
        mode="RACE",
        connected=connected,
        scope=EpisodeScope("test_story", "session", 0, run, 7),
        observations={"trigger": trigger, "moving": moving},
    )


def _guard(key):
    def check(frame, memory, definition, transition):
        value = frame.observations[key]
        decision = (
            GuardDecision.UNKNOWN
            if value is None
            else (GuardDecision.MATCH if value else GuardDecision.NO_MATCH)
        )
        return GuardResult(decision, 0.0 if value is None else 1.0, "test_guard", (key,))

    return check


def _action(emission):
    def emit(frame, memory, definition, transition):
        spec = definition.emissions[emission]
        return ActionEffect(
            beats=(
                ScenarioBeat(
                    scenario_id=definition.scenario_id,
                    scenario_version=definition.scenario_version,
                    episode_id=memory.episode_id,
                    parent_story_id=memory.episode_id,
                    beat_id=spec.beat_id,
                    event_type=spec.event_type,
                    phase=spec.phase,
                    priority=spec.priority,
                    confidence=1.0,
                    reason=transition.reason,
                    metrics={},
                ),
            )
        )

    return emit


def _engine(*, action_override=None, **kwargs):
    return ScenarioEngine(
        _definition(),
        guards={
            "incident_count_rising": _guard("trigger"),
            "on_track_motion_held": _guard("moving"),
        },
        actions={
            "emit_incident_if_narratable": action_override or _action("root"),
            "emit_back_under_way": _action("recovery"),
        },
        **kwargs,
    )


def test_hold_boundaries_and_distinct_correlations() -> None:
    engine = _engine()
    assert engine.tick(_frame(0.0, trigger=True)) == ()
    assert engine.tick(_frame(0.199, trigger=True)) == ()
    root = engine.tick(_frame(0.2, trigger=True))
    assert len(root) == 1
    assert engine.tick(_frame(1.0, moving=True)) == ()
    assert engine.tick(_frame(1.599, moving=True)) == ()
    closure = engine.tick(_frame(1.6, moving=True))
    assert len(closure) == 1
    assert root[0].parent_story_id == closure[0].parent_story_id
    assert root[0].correlation_id != closure[0].correlation_id


def test_unknown_breaks_hold_without_inventing_closure() -> None:
    engine = _engine()
    engine.tick(_frame(0.0, trigger=True))
    engine.tick(_frame(0.2, trigger=True))
    engine.tick(_frame(1.0, moving=True))
    assert engine.tick(_frame(1.5, moving=None)) == ()
    assert engine.tick(_frame(1.6, moving=True)) == ()
    assert engine.tick(_frame(2.19, moving=True)) == ()
    assert len(engine.tick(_frame(2.2, moving=True))) == 1


def test_scope_change_precedes_clock_rewind_and_resets_episode() -> None:
    engine = _engine()
    engine.tick(_frame(10.0, trigger=True))
    engine.tick(_frame(10.3, trigger=True))
    assert engine.tick(_frame(0.0, moving=True, run=1)) == ()
    assert engine.tick(_frame(1.0, moving=True, run=1)) == ()
    assert engine.memory.state == "IDLE"
    assert engine.memory.episode_id == ""


def test_duplicate_and_out_of_order_frames_do_not_advance_or_emit() -> None:
    engine = _engine()
    engine.tick(_frame(0.0, trigger=True))
    assert len(engine.tick(_frame(0.2, trigger=True))) == 1
    before = engine.memory
    assert engine.tick(_frame(0.2, moving=True)) == ()
    assert engine.tick(_frame(0.1, moving=True)) == ()
    assert engine.memory == before


def test_error_rolls_back_whole_tick_and_disables_only_this_engine() -> None:
    def fail(*args):
        raise RuntimeError("action failed")

    engine = _engine(action_override=fail)
    other = _engine()
    for item in (engine, other):
        item.tick(_frame(0.0, trigger=True))
    assert engine.tick(_frame(0.2, trigger=True)) == ()
    assert engine.disabled
    assert engine.memory.state == "IDLE"
    assert engine.traces[-1].reason == "scenario_execution_failed"
    assert len(other.tick(_frame(0.2, trigger=True))) == 1
    assert engine.tick(_frame(5.0, trigger=True)) == ()


def test_engine_refuses_unbound_guards_or_actions() -> None:
    with pytest.raises(ValueError, match="unbound"):
        ScenarioEngine(_definition(), guards={}, actions={})


def test_disconnect_and_unknown_mode_never_satisfy_recovery_hold() -> None:
    engine = _engine()
    engine.tick(_frame(0.0, trigger=True))
    engine.tick(_frame(0.2, trigger=True))
    engine.tick(_frame(1.0, moving=True))
    assert engine.tick(_frame(1.5, moving=True, connected=False)) == ()
    assert engine.tick(replace(_frame(1.6, moving=True), mode="GENERIC")) == ()
    assert engine.tick(_frame(1.8, moving=True)) == ()


def test_trace_memory_is_bounded_and_output_is_deterministic() -> None:
    def replay():
        engine = _engine(max_trace_records=2)
        output = []
        for run in range(10):
            for frame in (
                _frame(0, trigger=True, run=run),
                _frame(0.3, trigger=True, run=run),
                _frame(1, moving=True, run=run),
                _frame(2, moving=True, run=run),
            ):
                output.extend(beat.to_dict() for beat in engine.tick(frame))
        assert len(engine.traces) <= 2
        return output

    assert replay() == replay()


def test_long_disconnect_invalidates_without_recovery_even_on_reconnect() -> None:
    engine = _engine()
    engine.tick(_frame(0, trigger=True))
    root = engine.tick(_frame(0.2, trigger=True))[0]
    engine.tick(_frame(1, connected=False))
    assert engine.tick(_frame(3, moving=True)) == ()
    assert engine.tick(_frame(4, moving=True)) == ()
    assert engine.memory.state == "IDLE"
    engine.tick(_frame(5, trigger=True))
    next_root = engine.tick(_frame(5.3, trigger=True))[0]
    assert next_root.episode_id != root.episode_id


def test_terminal_retention_releases_episode_without_reusing_identity() -> None:
    engine = _engine()
    definition = engine.definition
    engine.definition = replace(
        definition, document={**definition.document, "terminalPolicy": {"retainForS": 0.75}}
    )
    engine.tick(_frame(0, trigger=True))
    first = engine.tick(_frame(0.2, trigger=True))[0]
    engine.tick(_frame(1, moving=True))
    engine.tick(_frame(2, moving=True))
    assert engine.tick(_frame(2.5, trigger=True)) == ()
    assert engine.memory.state == "DONE"
    engine.tick(_frame(3, trigger=True))
    second = engine.tick(_frame(3.3, trigger=True))[0]
    assert second.episode_id != first.episode_id


def test_episode_clock_does_not_restart_when_state_changes() -> None:
    engine = _engine()
    close = replace(engine.definition.transitions[1], hold_s=0.0, after_s=1.0, clock="episode")
    engine.definition = replace(
        engine.definition, transitions=(engine.definition.transitions[0], close)
    )
    engine.tick(_frame(0, trigger=True))
    engine.tick(_frame(0.2, trigger=True))
    # Simulate a development state entry that must not postpone the episode deadline.
    engine._memory = replace(engine.memory, entered_at=0.9)
    assert engine.tick(_frame(1.19, moving=True)) == ()
    assert len(engine.tick(_frame(1.2, moving=True))) == 1


def test_within_window_is_inclusive_and_expired_hold_does_not_emit() -> None:
    engine = _engine()
    start = replace(engine.definition.transitions[0], within_s=0.25)
    engine.definition = replace(
        engine.definition, transitions=(start, engine.definition.transitions[1])
    )
    engine.tick(_frame(0, trigger=True))
    assert engine.tick(_frame(0.3, trigger=True)) == ()
    assert engine.memory.state == "IDLE"


def test_entire_chain_is_rolled_back_if_second_action_fails() -> None:
    def fail(*args):
        raise ValueError("no closure")

    definition = _definition()
    definition = replace(
        definition, transitions=tuple(replace(item, hold_s=0.0) for item in definition.transitions)
    )
    engine = ScenarioEngine(
        definition,
        guards={
            "incident_count_rising": _guard("trigger"),
            "on_track_motion_held": _guard("moving"),
        },
        actions={"emit_incident_if_narratable": _action("root"), "emit_back_under_way": fail},
    )
    assert engine.tick(_frame(0, trigger=True, moving=True)) == ()
    assert engine.memory.episode_id == ""
    assert engine.disabled
    assert not any(trace.transition_id for trace in engine.traces)


def test_action_cannot_publish_a_beat_from_another_episode() -> None:
    def wrong(frame, memory, definition, transition):
        effect = _action("root")(frame, memory, definition, transition)
        return ActionEffect(beats=(replace(effect.beats[0], parent_story_id="other"),))

    engine = _engine(action_override=wrong)
    engine.tick(_frame(0, trigger=True))
    assert engine.tick(_frame(0.2, trigger=True)) == ()
    assert engine.disabled


def test_capacity_violation_is_fail_soft() -> None:
    def large(*args):
        return ActionEffect(facts={"a": 1, "b": 2})

    engine = _engine(action_override=large, max_facts=1)
    engine.tick(_frame(0, trigger=True))
    assert engine.tick(_frame(0.2, trigger=True)) == ()
    assert engine.disabled


@pytest.mark.parametrize("scope_field", ["session_num", "player_car_idx"])
def test_session_and_hero_change_reset_before_observation(scope_field: str) -> None:
    engine = _engine()
    engine.tick(_frame(0, trigger=True))
    engine.tick(_frame(0.2, trigger=True))
    frame = _frame(1, moving=True)
    changed = replace(frame, scope=replace(frame.scope, **{scope_field: 8}))
    assert engine.tick(changed) == ()
    assert engine.memory.episode_id == ""


def test_return_to_prior_hero_never_reuses_episode_id() -> None:
    engine = _engine()
    engine.tick(_frame(0, trigger=True))
    first = engine.tick(_frame(0.2, trigger=True))[0]
    other = _frame(1, moving=True)
    engine.tick(replace(other, scope=replace(other.scope, player_car_idx=8)))
    engine.tick(_frame(2, trigger=True))
    second = engine.tick(_frame(2.3, trigger=True))[0]
    assert second.episode_id != first.episode_id
