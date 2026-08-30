"""English mock lines and in-car / pit-entry speech mapping."""

from __future__ import annotations

import random

from irswitch.commentary.bridge import merge_speech_envelopes, speech_envelope_from_race_event
from irswitch.commentary.director import CommentaryDirector, choose_filled_line
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.in_car import InCarDetector
from irswitch.commentary.tts import NullTtsSink
from irswitch.commentary.validator import fill_slots, leftover_slots, validate_utterance
from irswitch.events.envelope import make_envelope
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import RaceEvent
from irswitch.overlay.settings import CommentarySettings


def test_mock_english_nodes_are_filled_and_valid() -> None:
    graph = load_sequence_graph()
    for node_id in ("in_car", "lap_complete", "pit_entry", "back_on_track"):
        node = graph.nodes[node_id]
        lines = node.variant_bucket("en", "unknown")
        assert len(lines) >= (6 if node_id == "in_car" else 3), node_id
        for line in lines:
            assert validate_utterance(line, node) == []
            bound = fill_slots(line, {slot.name: slot.example for slot in node.slots})
            assert not leftover_slots(bound)


def test_cs_has_authored_viewer_content() -> None:
    graph = load_sequence_graph()
    assert graph.nodes["in_car"].variant_bucket("cs", "unknown")
    assert graph.nodes["in_car"].variant_bucket("cs", "unknown") != graph.nodes[
        "in_car"
    ].variant_bucket("en", "unknown")


def test_choose_filled_line_is_deterministic_with_seed() -> None:
    texts = ("Alpha.", "Bravo.", "Charlie.")
    first = choose_filled_line(texts, {}, random.Random(7))
    second = choose_filled_line(texts, {}, random.Random(7))
    assert first == second
    assert first in texts


def test_in_car_fires_once_per_stint() -> None:
    detector = InCarDetector()
    empty = RaceState(connected=True)
    assert detector.tick(empty, 1.0) is None
    seated = RaceState(connected=True, player_car_idx=3, overlay_mode="RACE")
    first = detector.tick(seated, 2.0)
    assert first is not None
    assert first.event_type == "ENTER_CAR"
    assert detector.tick(seated, 3.0) is None
    detector.tick(RaceState(connected=False), 4.0)
    again = detector.tick(seated, 5.0)
    assert again is not None


def test_bridge_maps_pit_entry_not_car_entry() -> None:
    event = RaceEvent(
        name="pit_entry",
        channel="session",
        priority=50,
        phase="trigger",
        timestamp=1.0,
        data={"onPitRoad": True},
    )
    env = speech_envelope_from_race_event(event, now=1.0, mode="RACE")
    assert env is not None
    assert env.event_type == "PIT_ENTRY"


def test_in_car_still_fires_when_already_on_pit_road() -> None:
    """Garage sit is in-car, not pit entry."""
    detector = InCarDetector()
    seated_in_box = RaceState(
        connected=True,
        player_car_idx=1,
        on_pit_road=True,
        overlay_mode="RACE",
    )
    env = detector.tick(seated_in_box, 2.0)
    assert env is not None
    assert env.event_type == "ENTER_CAR"


def test_bridge_maps_pit_exit_and_ignores_unknown() -> None:
    exit_event = RaceEvent(
        name="pit_exit",
        channel="session",
        priority=50,
        phase="trigger",
        timestamp=1.0,
        data={"onPitRoad": False},
    )
    env = speech_envelope_from_race_event(exit_event, now=1.0, mode="RACE")
    assert env is not None
    assert env.event_type == "PIT_EXIT"
    ignored = speech_envelope_from_race_event(
        RaceEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            timestamp=1.0,
        ),
        now=1.0,
        mode="RACE",
    )
    assert ignored is None


def test_merge_adds_legacy_pit_when_v2_adapter_misses() -> None:
    race_event = RaceEvent(
        name="pit_entry",
        channel="session",
        priority=50,
        phase="trigger",
        timestamp=1.0,
        data={"onPitRoad": True},
    )
    merged = merge_speech_envelopes(race_event, [], now=1.0, mode="RACE")
    assert len(merged) == 1
    assert merged[0].event_type == "PIT_ENTRY"
    already = make_envelope(event_type="PIT_ENTRY", phase="ENTER")
    assert len(merge_speech_envelopes(race_event, [already], now=1.0, mode="RACE")) == 1


def test_emotion_bucket_has_authored_variants() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["lap_complete"]
    assert node.variant_bucket("en", "pushing")
    assert node.variant_bucket("en", "pushing") != node.variant_bucket("en", "unknown")


def test_director_speaks_in_car_from_czech_matrix() -> None:
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=load_sequence_graph(),
        settings=CommentarySettings(enabled=True, cooldown_s=0.1),
        sink=sink,
        language="cs",
        rng=random.Random(1),
    )
    spoken = director.observe([make_envelope(event_type="ENTER_CAR", phase="RESULT")], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "in_car"
    assert spoken.text in spoken.node.variant_bucket("cs", "unknown")


def test_director_maps_mock_events_to_expected_nodes() -> None:
    graph = load_sequence_graph()
    cases = (
        ("LAP_COMPLETE", "lap_complete"),
        ("PIT_ENTRY", "pit_entry"),
        ("PIT_EXIT", "back_on_track"),
        ("ENTER_CAR", "in_car"),
    )
    for event_type, node_id in cases:
        director = CommentaryDirector(
            graph=graph,
            settings=CommentarySettings(enabled=True, cooldown_s=0.1),
            sink=NullTtsSink(),
            language="en",
            rng=random.Random(2),
        )
        spoken = director.observe(
            [make_envelope(event_type=event_type, phase="RESULT")],
            None,
            10.0,
        )
        assert spoken is not None, event_type
        assert spoken.node_id == node_id
