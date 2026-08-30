"""P1 proofs: live-shaped envelopes bind slots without systematic slot_unbound."""

from __future__ import annotations

import random

from irswitch.commentary.director import CommentaryDirector, choose_filled_line, slot_bindings
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import EventSubject, make_envelope
from irswitch.overlay.settings import CommentarySettings


def test_lap_complete_bindings_from_live_metrics() -> None:
    env = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        priority=40,
        metrics={"lap": 12, "lapTime": 92.456, "deltaToBest": 0.21},
    )
    bound = slot_bindings(env, "unknown")
    assert bound["lap"] == 12
    assert bound["lap_time"] == 92.456


def test_position_gained_binds_old_and_new() -> None:
    env = make_envelope(
        event_type="POSITION_GAINED",
        phase="RESULT",
        priority=70,
        metrics={"oldPosition": 6, "newPosition": 5, "delta": 1},
    )
    bound = slot_bindings(env, "unknown")
    assert bound["position"] == 5
    assert bound["old_position"] == 6


def test_hunting_without_target_name_still_has_gap_lines() -> None:
    """Live battle path often lacks display_name; gap/position-only variants must speak."""
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    env = make_envelope(
        event_type="HUNTING",
        phase="ENTER",
        priority=55,
        metrics={"gap": 1.2, "position": 4, "targetCarIdx": 12},
        # no target display_name — mirrors live OpponentInfo gap
    )
    bound = slot_bindings(env, "unknown")
    assert bound.get("target_name") in (None, "")
    assert bound["gap"] == 1.2
    texts = node.variant_bucket("en", "unknown")
    spoken = choose_filled_line(texts, bound, random.Random(0))
    assert spoken is not None
    assert "{target_name}" not in spoken
    assert "{gap}" not in spoken


def test_rival_threat_with_live_metrics_speaks() -> None:
    """After adapter fix: gap + P{n} label bind; no longer systematic slot_unbound."""
    graph = load_sequence_graph()
    node = graph.nodes["rival_threat"]
    env = make_envelope(
        event_type="RIVAL_THREAT",
        phase="ENTER",
        priority=60,
        metrics={"gap": 1.8, "targetName": "P8"},
        target=EventSubject(car_id="22", display_name="P8"),
    )
    bound = slot_bindings(env, "unknown")
    texts = node.variant_bucket("en", "unknown")
    assert choose_filled_line(texts, bound, random.Random(0)) is not None


def test_rival_threat_without_name_or_gap_still_slot_unbound() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["rival_threat"]
    env = make_envelope(event_type="RIVAL_THREAT", phase="ENTER", priority=60, metrics={})
    bound = slot_bindings(env, "unknown")
    texts = node.variant_bucket("en", "unknown")
    assert choose_filled_line(texts, bound, random.Random(0)) is None


def test_director_speaks_lap_complete_from_live_shaped_envelope() -> None:
    director = CommentaryDirector(
        graph=load_sequence_graph(),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=NullTtsSink(),
        language="en",
    )
    env = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        priority=40,
        metrics={"lap": 7, "lapTime": 88.1},
    )
    spoken = director.observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "lap_complete"
    assert director.decisions(1)[-1]["reason"] == "spoken"
