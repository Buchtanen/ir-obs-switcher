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
            assert not leftover_slots(line)


def test_cs_falls_back_to_english_mock() -> None:
    graph = load_sequence_graph()
    assert graph.nodes["in_car"].variant_bucket("cs", "unknown")
    assert graph.nodes["in_car"].variant_bucket("cs", "unknown") == graph.nodes[
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
    examples = {
        "lap": 8,
        "lap_time": "1:31.1",
        "delta": "-0.4",
        "segment": "minisector 4",
        "target_time": "1:31.8",
        "projected_time": "1:31.5",
        "confidence": "high",
        "position": 4,
        "streak": 5,
        "gap": "2.4",
        "target_name": "Kovalainen",
    }
    for node_id, emotions in expected.items():
        node = graph.nodes[node_id]
        for emotion in emotions:
            lines = node.variants["en"].get(emotion) or ()
            assert 1 <= len(lines) <= 3, (node_id, emotion)
            for line in lines:
                assert validate_utterance(line, node) == []
                assert not leftover_slots(fill_slots(line, examples))


def test_w5_hr_and_invalid_lap_english() -> None:
    graph = load_sequence_graph()
    examples = {"bpm": 142, "lap": 4}
    for emotion, lines in (
        ("pushing", graph.nodes["hr_pressure"].variants["en"]["pushing"]),
        ("high", graph.nodes["hr_pressure"].variants["en"]["high"]),
    ):
        assert 1 <= len(lines) <= 3
        for line in lines:
            assert validate_utterance(line, graph.nodes["hr_pressure"]) == []
            assert not leftover_slots(fill_slots(line, examples))
    node = graph.nodes["invalid_lap"]
    for emotion in ("neutral", "calm", "focused"):
        lines = node.variants["en"][emotion]
        assert 1 <= len(lines) <= 3
        for line in lines:
            assert validate_utterance(line, node) == []
            assert not leftover_slots(fill_slots(line, examples))


def test_english_graph_has_no_unfilled_cells() -> None:
    missing_en = [c for c in load_sequence_graph().unfilled_cells() if c[1] == "en"]
    assert missing_en == []


def test_unfilled_emotion_still_falls_back_to_neutral() -> None:
    graph = load_sequence_graph()
    # CS still empty on race nodes; EN overtake is filled.
    assert graph.nodes["overtake"].variant_bucket("cs", "pushing") == graph.nodes[
        "overtake"
    ].variant_bucket("en", "pushing")


def test_w1_mock_four_emotion_matrix_valid() -> None:
    graph = load_sequence_graph()
    expected = {
        "in_car": ("calm", "focused", "pushing", "high"),
        "lap_complete": ("calm", "focused", "pushing", "high"),
        "pit_entry": ("calm", "focused"),
        "back_on_track": ("calm", "focused"),
    }
    examples = {
        "lap": 12,
        "lap_time": "1:32.4",
        "position": 8,
    }
    for node_id, emotions in expected.items():
        node = graph.nodes[node_id]
        locale_map = node.variants["en"]
        assert locale_map.get("neutral"), node_id
        for emotion in emotions:
            lines = locale_map.get(emotion) or ()
            assert 1 <= len(lines) <= 3, (node_id, emotion)
            for line in lines:
                assert validate_utterance(line, node) == []
                bound = fill_slots(line, examples)
                assert not leftover_slots(bound), (node_id, emotion, line)


def test_director_speaks_in_car_from_english_matrix() -> None:
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
    assert spoken.text in spoken.node.variant_bucket("en", "unknown")


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
    examples = {
        "position": 5,
        "old_position": 6,
        "target_name": "Rossi",
        "gap": "1.2",
        "value": 4,
    }
    for node_id, emotions in expected.items():
        node = graph.nodes[node_id]
        locale_map = node.variants["en"]
        for emotion in emotions:
            lines = locale_map.get(emotion) or ()
            assert 1 <= len(lines) <= 3, (node_id, emotion)
            for line in lines:
                assert validate_utterance(line, node) == []
                assert not leftover_slots(fill_slots(line, examples))


def test_w3_pit_outcome_english() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["pit_outcome"]
    examples = {"position": 11, "old_position": 8}
    for emotion in ("neutral", "calm", "focused"):
        lines = node.variants["en"].get(emotion) or ()
        assert 1 <= len(lines) <= 3, emotion
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
