"""Assignment briefs generated from graph structure."""

from irswitch.commentary.assignments import render_assignments
from irswitch.commentary.graph import load_sequence_graph


def test_assignments_report_zero_unfilled_when_graph_complete() -> None:
    text = render_assignments()
    assert text.startswith("# Commentary text assignments")
    assert "Unfilled cells: 0." in text
    assert load_sequence_graph().unfilled_cells() == []


def test_assignments_can_include_filled_cells() -> None:
    text = render_assignments(only_unfilled=False)
    assert "`overtake`" in text
    assert "{position}" in text
    assert "speak_priority" in text
    assert "Emotion variants to write" in text
    assert "Never open with a name slot and a comma" in text
    graph = load_sequence_graph()
    for node_id in graph.nodes:
        assert f"`{node_id}`" in text


def test_assignments_can_filter_locale() -> None:
    text = render_assignments(locale="cs", only_unfilled=False)
    assert " — cs / " in text
    assert " — en / " not in text
    for node_id in ("in_car", "lap_complete", "pit_entry", "back_on_track"):
        assert f"`{node_id}`" in text


def test_assignments_can_rebrief_dense_czech_nodes() -> None:
    """Dense graph still lists core Czech speak nodes for rewrite briefs."""
    text = render_assignments(locale="cs", only_unfilled=False)
    for node_id in ("in_car", "lap_complete", "pit_entry", "back_on_track"):
        assert f"`{node_id}`" in text
