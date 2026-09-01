from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.battle import BattleEmitter
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.settings import HuntingSettings


def _state(*, front: int = 10, rear: int = 20) -> RaceState:
    return RaceState(
        connected=True,
        player_car_idx=5,
        position=7,
        overlay_mode="RACE",
        opponent_ahead=OpponentInfo(front, position=6, display_name="Rossi"),
        opponent_behind=OpponentInfo(rear, position=8, display_name="Berg"),
        gap_ahead=0.7,
        gap_behind=0.5,
        closing_rate_ahead=0.4,
        closing_rate_behind=0.3,
    )


def _emitter() -> BattleEmitter:
    settings = HuntingSettings(activation_delay=0.0)
    return BattleEmitter(settings, settings)


def test_two_front_parents_are_ordered_before_complete_composite() -> None:
    emitter = _emitter()
    events = emitter.tick(_state(), 10.0)
    assert [event.data["state"] for event in events] == [
        "hunting",
        "hunted",
        "battle_for_position",
    ]
    composite = events[-1].data
    assert composite["frontTargetCarIdx"] == 10
    assert composite["frontTargetName"] == "Rossi"
    assert composite["frontGap"] == 0.7
    assert composite["rearTargetCarIdx"] == 20
    assert composite["rearTargetName"] == "Berg"
    assert composite["rearGap"] == 0.5
    assert composite["frontRelationEpoch"] == 1
    assert composite["rearRelationEpoch"] == 1


def test_manager_keeps_both_parents_and_composite_active() -> None:
    emitter = _emitter()
    manager = EventManagerV2(session_id="s:0")
    accepted = []
    for candidate in emitter.tick(_state(), 10.0):
        _, envelopes = manager.submit(candidate, 10.0, mode="RACE")
        accepted.extend(envelopes)
    enters = [event for event in accepted if event.phase == "ENTER"]
    assert [event.event_type for event in enters] == [
        "HUNTING",
        "HUNTED",
        "BATTLE_FOR_POSITION",
    ]
    assert len(manager.active_stories_v4()) == 3
    assert len({event.correlation_id for event in enters}) == 3


def test_front_target_swap_exits_composite_and_preserves_rear_identity() -> None:
    emitter = _emitter()
    emitter.tick(_state(), 10.0)
    events = emitter.tick(_state(front=11), 11.0)
    states = [(event.data["state"], event.phase) for event in events]
    assert ("hunting", "exit") in states
    assert ("battle_for_position", "exit") in states
    assert emitter.hunted.state == "ACTIVE"
    assert emitter.hunted.target_car_idx == 20
    assert emitter.hunted.relation_epoch == 1


def test_adapter_uses_relation_identity_for_parent_and_composite() -> None:
    emitter = _emitter()
    race_events = []
    manager = EventManagerV2(session_id="s:0")
    for candidate in emitter.tick(_state(), 10.0):
        race_event, _ = manager.submit(candidate, 10.0, mode="RACE")
        assert race_event is not None
        race_events.append(race_event)
    parent = battle_race_event_to_envelope(race_events[0], session_id="s:0", mode="RACE", now=10.0)
    composite = battle_race_event_to_envelope(
        race_events[-1], session_id="s:0", mode="RACE", now=10.0
    )
    assert parent is not None and parent.correlation_id == "battle:front:5:10:1"
    assert composite is not None
    assert composite.correlation_id == "battle:two-front:5:10:20:1:1"
