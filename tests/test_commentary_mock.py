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

# Dense graph targets from commentary-extension-texts (#130 M0).
PRIORITY_DENSITY = 16
STANDARD_DENSITY = 12
PRIORITY_NODES = {
    "lap_complete",
    "personal_best",
    "hunting",
    "hunted",
    "side_by_side",
    "overtake",
    "position_gained",
    "position_lost",
    "rival_threat",
    "battle_won",
    "final_lap",
    "finish",
    "pit_entry",
    "back_on_track",
    "in_car",
    "pit_outcome",
}


def _expected_density(node_id: str) -> int:
    return PRIORITY_DENSITY if node_id in PRIORITY_NODES else STANDARD_DENSITY


def test_mock_english_nodes_are_filled_and_valid() -> None:
    graph = load_sequence_graph()
    for node_id in ("in_car", "lap_complete", "pit_entry", "back_on_track"):
        node = graph.nodes[node_id]
        lines = node.variant_bucket("en", "unknown")
        assert len(lines) == _expected_density(node_id), node_id
        examples = {slot.name: slot.example for slot in node.slots}
        for line in lines:
            assert validate_utterance(line, node) == []
            assert not leftover_slots(fill_slots(line, examples))


def test_cs_in_car_uses_authored_czech() -> None:
    graph = load_sequence_graph()
    cs = graph.nodes["in_car"].variant_bucket("cs", "unknown")
    en = graph.nodes["in_car"].variant_bucket("en", "unknown")
    assert cs
    assert en
    assert cs != en


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


def test_in_car_skips_after_session() -> None:
    detector = InCarDetector()
    env = detector.tick(
        RaceState(
            connected=True,
            player_car_idx=1,
            overlay_mode="RACE",
            session_finished=True,
        ),
        1.0,
    )
    assert env is None
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


def test_w1_emotion_buckets_are_authored_not_neutral_fallback() -> None:
    """W1 filled calm/focused/pushing/high on mock-4; unknown still uses neutral."""
    graph = load_sequence_graph()
    node = graph.nodes["lap_complete"]
    neutral = node.variant_bucket("en", "unknown")
    pushing = node.variant_bucket("en", "pushing")
    assert neutral
    assert pushing
    assert pushing != neutral
    for line in pushing:
        assert validate_utterance(line, node) == []


def test_w4_timing_nodes_english() -> None:
    graph = load_sequence_graph()
    expected = {
        "personal_best": ("neutral", "calm", "focused", "pushing", "high"),
        "gain_found": ("neutral", "calm", "focused"),
        "time_lost": ("neutral", "calm", "focused"),
        "target_locked": ("neutral", "calm", "focused"),
        "projected_lap": ("neutral", "focused", "pushing"),
        "hot_lap": ("neutral", "focused", "pushing", "high"),
        "position_attack": ("neutral", "focused", "pushing"),
        "clean_streak": ("neutral", "calm", "focused"),
        "rival_threat": ("neutral", "focused", "pushing"),
    }
    for node_id, emotions in expected.items():
        node = graph.nodes[node_id]
        examples = {slot.name: slot.example for slot in node.slots}
        for emotion in emotions:
            lines = node.variants["en"].get(emotion) or ()
            assert len(lines) == _expected_density(node_id), (node_id, emotion)
            for line in lines:
                assert validate_utterance(line, node) == []
                assert not leftover_slots(fill_slots(line, examples))


def test_w5_hr_and_invalid_lap_english() -> None:
    graph = load_sequence_graph()
    hr = graph.nodes["hr_pressure"]
    hr_examples = {slot.name: slot.example for slot in hr.slots}
    for _emotion, lines in (
        ("pushing", hr.variants["en"]["pushing"]),
        ("high", hr.variants["en"]["high"]),
    ):
        assert len(lines) == _expected_density("hr_pressure")
        for line in lines:
            assert validate_utterance(line, hr) == []
            assert not leftover_slots(fill_slots(line, hr_examples))
    node = graph.nodes["invalid_lap"]
    examples = {slot.name: slot.example for slot in node.slots}
    for emotion in ("neutral", "calm", "focused"):
        lines = node.variants["en"][emotion]
        assert len(lines) == _expected_density("invalid_lap")
        for line in lines:
            assert validate_utterance(line, node) == []
            assert not leftover_slots(fill_slots(line, examples))


def test_graph_has_no_unfilled_cells() -> None:
    assert load_sequence_graph().unfilled_cells() == []


def test_cs_overtake_is_authored_not_en_fallback() -> None:
    graph = load_sequence_graph()
    cs = graph.nodes["overtake"].variant_bucket("cs", "pushing")
    en = graph.nodes["overtake"].variant_bucket("en", "pushing")
    assert cs and en and cs != en


def test_w1_mock_four_emotion_matrix_valid() -> None:
    graph = load_sequence_graph()
    expected = {
        "in_car": ("calm", "focused", "pushing", "high"),
        "lap_complete": ("calm", "focused", "pushing", "high"),
        "pit_entry": ("calm", "focused"),
        "back_on_track": ("calm", "focused"),
    }
    for node_id, emotions in expected.items():
        node = graph.nodes[node_id]
        examples = {slot.name: slot.example for slot in node.slots}
        locale_map = node.variants["en"]
        assert locale_map.get("neutral"), node_id
        for emotion in emotions:
            lines = locale_map.get(emotion) or ()
            assert len(lines) == _expected_density(node_id), (node_id, emotion)
            for line in lines:
                assert validate_utterance(line, node) == []
                bound = fill_slots(line, examples)
                assert not leftover_slots(bound), (node_id, emotion, line)


def test_director_speaks_in_car_czech_when_locale_cs() -> None:
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
    assert spoken.locale == "cs"
    assert spoken.text in spoken.node.variant_bucket("cs", "unknown")


def test_w2_race_beat_nodes_speak_english() -> None:
    graph = load_sequence_graph()
    expected = {
        "finish": ("neutral", "calm", "focused", "pushing", "high"),
        "final_lap": ("neutral", "focused", "pushing", "high"),
        "incident": ("neutral", "focused", "pushing", "high"),
        "overtake": ("neutral", "focused", "pushing", "high"),
        "battle_won": ("neutral", "focused", "pushing", "high"),
        "position_gained": ("neutral", "calm", "focused", "pushing"),
        "position_lost": ("neutral", "focused", "pushing", "high"),
        "side_by_side": ("neutral", "pushing", "high"),
        "hunting": ("neutral", "focused", "pushing", "high"),
        "hunted": ("neutral", "focused", "pushing", "high"),
    }
    for node_id, emotions in expected.items():
        node = graph.nodes[node_id]
        examples = {slot.name: slot.example for slot in node.slots}
        locale_map = node.variants["en"]
        for emotion in emotions:
            lines = locale_map.get(emotion) or ()
            assert len(lines) == _expected_density(node_id), (node_id, emotion)
            for line in lines:
                assert validate_utterance(line, node) == []
                assert not leftover_slots(fill_slots(line, examples))


def test_w3_pit_outcome_english() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["pit_outcome"]
    examples = {slot.name: slot.example for slot in node.slots}
    for emotion in ("neutral", "calm", "focused"):
        lines = node.variants["en"].get(emotion) or ()
        assert len(lines) == _expected_density("pit_outcome"), emotion
        for line in lines:
            assert validate_utterance(line, node) == []
            assert not leftover_slots(fill_slots(line, examples))


def test_director_speaks_overtake_and_finish() -> None:
    graph = load_sequence_graph()
    cases = (
        ("OVERTAKE", "RESULT", "overtake", {"position": 5, "target_name": "Rossi"}),
        ("FINISH", "RESULT", "finish", {"position": 3}),
        ("HUNTING", "ENTER", "hunting", {"gap": 1.2, "target_name": "Rossi", "position": 6}),
    )
    for event_type, phase, node_id, metrics in cases:
        director = CommentaryDirector(
            graph=graph,
            settings=CommentarySettings(enabled=True, cooldown_s=0.1),
            sink=NullTtsSink(),
            language="en",
            rng=random.Random(3),
        )
        spoken = director.observe(
            [make_envelope(event_type=event_type, phase=phase, metrics=metrics)],
            None,
            10.0,
        )
        assert spoken is not None, event_type
        assert spoken.node_id == node_id
        assert spoken.text


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


def test_director_speaks_race_in_car_mode_node() -> None:
    director = CommentaryDirector(
        graph=load_sequence_graph(),
        settings=CommentarySettings(enabled=True, cooldown_s=0.1),
        sink=NullTtsSink(),
        language="en",
        rng=random.Random(2),
    )
    spoken = director.observe(
        [make_envelope(event_type="ENTER_CAR", phase="RESULT", mode="RACE")],
        None,
        10.0,
    )
    assert spoken is not None
    assert spoken.node_id == "in_car_race"
    assert spoken.text
