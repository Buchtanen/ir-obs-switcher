from irswitch.commentary.consumer import CommentaryConsumer
from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.battle import BattleEmitter
from irswitch.events.envelope import make_envelope
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.settings import CommentarySettings, HuntingSettings


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


def test_commentary_prefers_composite_and_accounts_for_parent_enters() -> None:
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    consumer = CommentaryConsumer(
        AsyncEventFanout().subscribe("commentary"),
        CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()),
        lambda: (settings, "en"),
    )
    front = make_envelope(event_type="HUNTING", phase="ENTER", priority=20)
    rear = make_envelope(event_type="HUNTED", phase="ENTER", priority=20)
    composite = make_envelope(
        event_type="BATTLE_FOR_POSITION",
        phase="ENTER",
        priority=30,
        metrics={"frontTargetCarIdx": 10, "rearTargetCarIdx": 20},
    )
    latest = {
        "race": {
            "opponent_ahead": {"car_idx": 10},
            "opponent_behind": {"car_idx": 20},
        }
    }

    selected = consumer._prefer_two_front([front, rear, composite], latest, 10.0)

    assert selected == [composite]
    reasons = [decision["reason"] for decision in consumer.director.decisions()]
    assert reasons == ["covered_by_two_front", "covered_by_two_front"]


def test_two_front_graph_update_is_reachable_and_all_slots_bind() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["two_front_battle"]
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=graph, settings=settings, sink=NullTtsSink())

    def event(phase: str, at_ms: int):
        return make_envelope(
            event_type="BATTLE_FOR_POSITION",
            phase=phase,
            priority=72,
            monotonic_ms=at_ms,
            correlation_id="battle:two-front:5:10:20:1:1",
            metrics={
                "newPosition": 7,
                "frontTargetName": "Rossi",
                "frontTargetPosition": 6,
                "frontGap": 0.7,
                "rearTargetName": "Berg",
                "rearGap": 0.5,
            },
        )

    entered = event("ENTER", 10_000)
    bound = slot_bindings(entered, "unknown")
    assert all(bound.get(slot.name) is not None for slot in node.slots)
    assert director.observe([entered], None, 10.0) is not None

    updated = event("UPDATE", 30_000)
    spoken = director.observe([updated], None, 30.0)
    assert spoken is not None
    assert spoken.node_id == "two_front_battle"
