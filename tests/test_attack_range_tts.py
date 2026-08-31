"""P5 content gaps: ATTACK_RANGE and mid-pit PIT_STOPPED speech."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.adapters.pit import pit_race_event_to_envelope
from irswitch.overlay.protocol import RaceEvent
from irswitch.overlay.settings import CommentarySettings


def _director() -> CommentaryDirector:
    return CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, use_hr_emotion=False, cooldown_s=0.1),
        sink=NullTtsSink(),
    )


def test_graph_has_attack_range_and_pit_stopped_nodes() -> None:
    graph = load_sequence_graph()
    assert "attack_range" in graph.nodes
    assert "pit_stopped" in graph.nodes
    assert graph.nodes_for("ATTACK_RANGE", "ENTER")
    assert graph.nodes_for("PIT_STOPPED", "ENTER")


def test_director_speaks_attack_range_enter() -> None:
    envelope = battle_race_event_to_envelope(
        RaceEvent(
            name="battle",
            channel="battle",
            priority=60,
            phase="enter",
            timestamp=1.0,
            data={
                "state": "attack_range",
                "gap": 0.45,
                "targetName": "Rossi",
                "position": 5,
                "correlationId": "battle:attack_range",
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "ATTACK_RANGE"
    spoken = _director().observe([envelope], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "attack_range"
    assert spoken.event_type == "ATTACK_RANGE"


def test_director_speaks_pit_stopped_enter() -> None:
    envelope = pit_race_event_to_envelope(
        RaceEvent(
            name="pit_story",
            channel="pit",
            priority=55,
            phase="enter",
            timestamp=1.0,
            data={
                "state": "stopped",
                "position": 8,
                "correlationId": "pit:sub:1",
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=12.0,
    )
    assert envelope is not None
    assert envelope.event_type == "PIT_STOPPED"
    spoken = _director().observe([envelope], None, 12.0)
    assert spoken is not None
    assert spoken.node_id == "pit_stopped"
