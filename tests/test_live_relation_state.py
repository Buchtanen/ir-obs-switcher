"""Relation source validity and exact accepted lifecycle identity regressions."""

from dataclasses import replace

import pytest

from irswitch.events.battle import BattleEmitter
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import HuntingSettings


def _emitter() -> BattleEmitter:
    cfg = HuntingSettings(activation_delay=0.0, exit_delay=0.0)
    return BattleEmitter(cfg, cfg)


def _state() -> RaceState:
    return RaceState(
        connected=True,
        player_car_idx=5,
        position=7,
        class_position=5,
        opponent_ahead=OpponentInfo(0, position=6, class_position=4, display_name="Front"),
        opponent_behind=OpponentInfo(20, position=8, class_position=6, display_name="Rear"),
        gap_ahead=2.0,
        gap_behind=1.5,
        closing_rate_ahead=0.3,
        closing_rate_behind=0.3,
    )


@pytest.mark.parametrize("gap", [-38.0, float("nan"), float("inf"), -float("inf"), True])
@pytest.mark.parametrize("side", ["ahead", "behind"])
def test_invalid_gap_cannot_enter_relation(side: str, gap: float) -> None:
    events = _emitter().tick(replace(_state(), **{f"gap_{side}": gap}), 1.0)
    rejected = "hunting" if side == "ahead" else "hunted"
    assert not any(e.data["state"] in {rejected, "battle_for_position"} for e in events)


@pytest.mark.parametrize("closing", [float("nan"), float("inf"), -float("inf"), True])
def test_invalid_closing_rate_cannot_enter_relation(closing: float) -> None:
    events = _emitter().tick(replace(_state(), closing_rate_ahead=closing), 1.0)
    assert not any(e.data["state"] in {"hunting", "battle_for_position"} for e in events)


@pytest.mark.parametrize(
    "side,position", [("ahead", 5), ("ahead", 6), ("behind", 5), ("behind", 4)]
)
def test_class_order_must_agree_with_direction(side: str, position: int) -> None:
    state = _state()
    target = getattr(state, f"opponent_{side}")
    state = replace(state, **{f"opponent_{side}": replace(target, class_position=position)})
    rejected = "hunting" if side == "ahead" else "hunted"
    assert not any(
        e.data["state"] in {rejected, "battle_for_position"} for e in _emitter().tick(state, 1.0)
    )


def _submit(manager: EventManagerV2, events: list[CandidateEvent], now: float):
    return [env for candidate in events for env in manager.submit(candidate, now)[1]]


@pytest.mark.parametrize("reason", ["pit", "finished", "stale", "lost_targets"])
def test_abort_reuses_enter_identity_and_clears_final_state(reason: str) -> None:
    emitter, manager = _emitter(), EventManagerV2(session_id="s:0")
    entered = _submit(manager, emitter.tick(_state(), 1.0), 1.0)
    identities = {e.correlation_id for e in entered if e.phase == "ENTER"}
    assert len(identities) == 3
    state = {
        "pit": replace(_state(), on_pit_road=True),
        "finished": replace(_state(), session_finished=True),
        "stale": replace(_state(), data_quality="stale"),
        "lost_targets": replace(_state(), opponent_ahead=None, opponent_behind=None),
    }[reason]
    exited = _submit(manager, emitter.tick(state, 2.0), 2.0)
    assert len(exited) == 3
    assert all(e.phase == "EXIT" for e in exited)
    assert {e.correlation_id for e in exited} == identities
    assert manager.active_stories_v4() == []
    assert _submit(manager, emitter.tick(state, 3.0), 3.0) == []


def test_target_change_exits_old_composite_and_preserves_old_target_name() -> None:
    emitter, manager = _emitter(), EventManagerV2(session_id="s:0")
    first = _submit(manager, emitter.tick(_state(), 1.0), 1.0)
    previous = {e.event_type: e for e in first if e.phase == "ENTER"}
    swapped = replace(
        _state(), opponent_ahead=OpponentInfo(11, position=6, class_position=4, display_name="New")
    )
    candidates = emitter.tick(swapped, 2.0)
    old = next(e for e in candidates if e.phase == "exit" and e.data["state"] == "hunting")
    assert old.data["targetName"] == "Front"
    assert old.data["targetCarIdx"] == 0
    emitted = _submit(manager, candidates, 2.0)
    exits = [e for e in emitted if e.phase == "EXIT"]
    assert len(exits) == 2
    for event in exits:
        assert event.correlation_id == previous[event.event_type].correlation_id
    assert len(manager.active_stories_v4()) == 3
    assert previous["HUNTING"].correlation_id not in {
        e["correlationId"] for e in manager.active_stories_v4()
    }


def _candidate(phase: str, **data: object) -> CandidateEvent:
    return CandidateEvent(
        name="battle", channel="battle", priority=20, phase=phase, data={"state": "hunting", **data}
    )


def test_partial_update_and_exit_preserve_enter_identity_once() -> None:
    manager = EventManagerV2(session_id="s:0")
    _, entered = manager.submit(
        _candidate("enter", heroCarIdx=5, targetCarIdx=0, relationEpoch=9, gap=2.0), 1.0
    )
    identity = entered[0].correlation_id
    assert identity == "battle:front:5:0:9"
    _, updated = manager.submit(_candidate("update", gap=1.8), 2.0)
    assert updated[0].correlation_id == identity
    assert updated[0].target.car_id == "0"
    _, exited = manager.submit(_candidate("exit", reason="resolved"), 3.0)
    assert len(exited) == 1
    assert exited[0].correlation_id == identity
    assert exited[0].metrics["relationEpoch"] == 9
    assert manager.active_stories_v4() == []
    assert manager.submit(_candidate("exit", targetCarIdx=0, relationEpoch=9), 4.0) == (None, [])
    assert manager.unmatched_exits == 1


def test_late_old_exit_does_not_remove_new_target_in_same_slot() -> None:
    manager = EventManagerV2(session_id="s:0")
    manager.submit(_candidate("enter", targetCarIdx=17, relationEpoch=1), 1.0)
    _, replaced = manager.submit(_candidate("enter", targetCarIdx=18, relationEpoch=2), 2.0)
    assert [e.phase for e in replaced] == ["EXIT", "ENTER", "ACTIVE"]
    assert len(manager.active_stories_v4()) == 1
    assert manager.submit(_candidate("exit", targetCarIdx=17, relationEpoch=1), 3.0) == (None, [])
    assert manager.active_stories_v4()[0]["target"]["carId"] == "18"
    assert manager.unmatched_exits == 1
    assert manager.decisions.latest(1)[0]["reason"] == "unmatched_exit"


def test_run_epoch_namespace_is_shared_by_events_and_active_snapshot() -> None:
    manager = EventManagerV2(session_id="s:0")
    manager.set_run_epoch(2)
    _, entered = manager.submit(_candidate("enter", targetCarIdx=17, relationEpoch=1), 1.0)
    identity = entered[0].correlation_id
    assert identity == "run:2:battle:front:player:17:1"
    assert {e.correlation_id for e in entered} == {identity}
    assert manager.active_stories_v4()[0]["correlationId"] == identity
    assert manager.active_stories_v4()[0]["metrics"]["runEpoch"] == 2
    _, exited = manager.submit(_candidate("exit"), 2.0)
    assert exited[0].correlation_id == identity
    assert exited[0].metrics["runEpoch"] == 2
    assert manager.active_stories_v4() == []
