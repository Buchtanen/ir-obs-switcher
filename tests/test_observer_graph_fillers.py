"""Graph nodes for observer fillers (P2–P5 content in sequence_graph)."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.overlay.settings import CommentarySettings


def _director(**kwargs: object) -> CommentaryDirector:
    settings = CommentarySettings(
        enabled=True,
        use_hr_emotion=False,
        cooldown_s=0.1,
        session_briefs=True,
        **kwargs,  # type: ignore[arg-type]
    )
    return CommentaryDirector.from_defaults(settings=settings, sink=NullTtsSink())


def test_graph_has_observer_filler_nodes() -> None:
    graph = load_sequence_graph()
    for node_id, event_type in (
        ("incident_aftermath", "INCIDENT_AFTERMATH"),
        ("back_under_way", "BACK_UNDER_WAY"),
        ("session_wrap", "SESSION_WRAP"),
        ("session_preview", "SESSION_PREVIEW"),
        ("session_checkered", "SESSION_CHECKERED"),
        ("field_fact", "FIELD_FACT"),
        ("weather_change", "WEATHER_CHANGE"),
    ):
        assert node_id in graph.nodes
        assert graph.nodes_for(event_type, "RESULT")
        node = graph.nodes[node_id]
        assert node.variants["en"].get("neutral") or node.variants["en"].get("unknown")
        assert node.variants["cs"].get("neutral") or node.variants["cs"].get("unknown")


def test_densified_attack_and_pit_buckets() -> None:
    graph = load_sequence_graph()
    ar = graph.nodes["attack_range"]
    assert "calm" in ar.hr_states
    assert len(ar.variants["en"]["calm"]) >= 10
    assert len(ar.variants["cs"]["calm"]) >= 10
    pit = graph.nodes["pit_stopped"]
    assert "pushing" in pit.hr_states and "high" in pit.hr_states
    assert len(pit.variants["en"]["pushing"]) >= 10
    assert len(pit.variants["en"]["high"]) >= 10


def test_slot_bindings_observer_fields() -> None:
    aftermath = make_envelope(
        event_type="INCIDENT_AFTERMATH",
        phase="RESULT",
        mode="RACE",
        priority=72,
        monotonic_ms=1,
        metrics={"kind": "stalled", "position": 4},
    )
    en = slot_bindings(aftermath, "unknown", language="en")
    cs = slot_bindings(aftermath, "unknown", language="cs")
    assert en["kind"] == "stalled"
    assert cs["kind"] == "stojí"
    assert en["position"] == 4

    wrap = make_envelope(
        event_type="SESSION_WRAP",
        phase="RESULT",
        mode="RACE",
        priority=58,
        monotonic_ms=1,
        metrics={"modeLabel": "Race", "modeLabelCs": "závod", "position": 2},
    )
    assert slot_bindings(wrap, "unknown", language="en")["mode"] == "Race"
    assert slot_bindings(wrap, "unknown", language="cs")["mode"] == "závod"

    fact = make_envelope(
        event_type="FIELD_FACT",
        phase="RESULT",
        mode="RACE",
        priority=28,
        monotonic_ms=1,
        metrics={"leaderName": "Rossi", "fact": "leader"},
    )
    assert slot_bindings(fact, "unknown")["leader_name"] == "Rossi"

    gap_fact = make_envelope(
        event_type="FIELD_FACT",
        phase="RESULT",
        mode="RACE",
        priority=28,
        monotonic_ms=1,
        metrics={
            "fact": "gap",
            "target_name": "Hamilton",
            "gap": 1.25,
        },
    )
    gap_bound = slot_bindings(gap_fact, "unknown")
    assert gap_bound["target_name"] == "Hamilton"
    assert gap_bound["gap"] is not None


def test_director_speaks_aftermath_from_graph() -> None:
    env = make_envelope(
        event_type="INCIDENT_AFTERMATH",
        phase="RESULT",
        mode="RACE",
        priority=72,
        monotonic_ms=1000,
        metrics={"kind": "rolling", "value": 2},
    )
    spoken = _director().observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "incident_aftermath"
    assert spoken.text.strip().endswith((".", "!", "?"))
    assert "{" not in spoken.text


def test_director_speaks_session_wrap_from_graph() -> None:
    env = make_envelope(
        event_type="SESSION_WRAP",
        phase="RESULT",
        mode="RACE",
        priority=58,
        monotonic_ms=1000,
        metrics={
            "kind": "session_wrap",
            "mode": "RACE",
            "modeLabel": "Race",
            "modeLabelCs": "závod",
            "position": 5,
        },
    )
    spoken = _director().observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "session_wrap"
    assert spoken.text.strip().endswith((".", "!", "?"))
    assert "{" not in spoken.text


def test_director_speaks_session_checkered_from_graph() -> None:
    env = make_envelope(
        event_type="SESSION_CHECKERED",
        phase="RESULT",
        mode="QUALIFYING",
        priority=56,
        monotonic_ms=1000,
        metrics={
            "kind": "session_checkered",
            "mode": "QUALIFYING",
            "modeLabel": "Qualifying",
            "modeLabelCs": "kvalifikace",
            "position": 4,
        },
    )
    spoken = _director().observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "session_checkered"
    assert spoken.text.strip().endswith((".", "!", "?"))
    assert "{" not in spoken.text


def test_director_speaks_field_fact_from_graph() -> None:
    env = make_envelope(
        event_type="FIELD_FACT",
        phase="RESULT",
        mode="RACE",
        priority=28,
        monotonic_ms=1000,
        metrics={"fact": "position", "position": 6, "kind": "field_fact"},
    )
    spoken = _director().observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "field_fact"
    assert "6" in spoken.text or "P6" in spoken.text or "P{position}" not in spoken.text
