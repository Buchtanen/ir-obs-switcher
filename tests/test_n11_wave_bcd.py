"""N11 B/C/D graph copy: incident branches, flags, quali recap / parade pad."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.observer import RaceObserver


def test_director_speaks_off_track_not_generic_contact() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    env = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        metrics={"value": 2, "branch": "off_track"},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "incident_off_track"
    assert "contact" not in spoken.text.lower()
    lowered = spoken.text.lower()
    assert any(word in lowered for word in ("off", "runoff", "road", "surface", "track"))


def test_director_speaks_unknown_incident_branch() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    env = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        metrics={"value": 2, "branch": "unknown"},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "incident_unknown"


def test_unclassified_incident_still_uses_generic_node() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    env = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        metrics={"value": 2},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "incident"


def test_director_speaks_flag_branch_nodes() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    yellow = make_envelope(
        event_type="SESSION_FLAG",
        phase="RESULT",
        mode="RACE",
        priority=78,
        metrics={"kind": "yellow", "branch": "yellow"},
    )
    spoken = director.observe([yellow], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "session_flag_yellow"
    assert "Caution" in spoken.text

    graph = load_sequence_graph()
    for branch, node_id in (
        ("green", "session_flag_green"),
        ("checkered", "session_flag_checkered"),
    ):
        node = graph.nodes[node_id]
        assert node.branch == branch
        assert len(node.variant_bucket("en", "unknown")) == 1
        assert len(node.variant_bucket("cs", "unknown")) == 1


def test_director_speaks_quali_recap_graph_not_formatter() -> None:
    observer = RaceObserver()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    env = make_envelope(
        event_type="QUALI_RECAP",
        phase="RESULT",
        mode="RACE",
        priority=66,
        metrics={"kind": "quali_recap", "position": 4, "lapTime": 91.234},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "quali_recap"
    assert "P4" in spoken.text
    pad = make_envelope(
        event_type="PARADE_PAD",
        phase="RESULT",
        mode="RACE",
        priority=30,
        metrics={"kind": "parade_pad"},
    )
    later = director.observe([pad], None, 20.0)
    assert later is not None
    assert later.node_id == "parade_pad"
