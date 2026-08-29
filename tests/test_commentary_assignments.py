"""Assignment briefs generated from graph structure."""

from irswitch.commentary.assignments import render_assignments
from irswitch.commentary.graph import load_sequence_graph


def test_assignments_cover_unfilled_speak_nodes() -> None:
    text = render_assignments()
    assert text.startswith("# Commentary text assignments")
    assert "`overtake`" in text
    assert "{position}" in text
    assert "speak_priority" in text
    assert "Emotion variants to write" in text
    graph = load_sequence_graph()
    for node_id in graph.nodes:
        assert f"`{node_id}`" in text


def test_assignments_can_filter_locale() -> None:
    text = render_assignments(locale="cs")
    assert " — cs / " in text
    assert " — en / " not in text
