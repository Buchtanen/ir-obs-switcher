"""#272 legacy↔v2 shadow compare — silent observational harness (first slice)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_story_director import _cand, _world

from irswitch.events import __all__ as events_exports
from irswitch.events.legacy_v2_shadow_compare import (
    FAMILY_ROUTE,
    DivergenceRecord,
    ShadowCompareResult,
    compare_director_decisions,
    route_for_family,
)
from irswitch.events.story_director import StoryDirector

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "legacy_v2_shadow_compare.py"
)


def test_module_is_branch_private_and_documents_observation_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "Not exported from ``events/__init__.py``" in text
    assert "observation-only" in text or "Observation-only" in text
    assert "legacy_v2_shadow_compare" not in events_exports
    assert "compare_director_decisions" not in events_exports


def test_lap_family_routes_to_shadow_via_private_table() -> None:
    assert FAMILY_ROUTE["lap"] == "shadow"
    assert route_for_family("lap") == "shadow"
    assert route_for_family("unknown_family") == "legacy"


def test_matching_director_decisions_produce_no_divergence() -> None:
    world = _world()
    candidate = _cand()
    decision = StoryDirector().evaluate(world, (candidate,))
    assert decision.selected is not None

    result = compare_director_decisions(
        family="lap",
        legacy_selected_beat_id=decision.selected.beat_id,
        legacy_reason=decision.reason,
        world=world,
        candidates=(candidate,),
    )
    assert isinstance(result, ShadowCompareResult)
    assert result.family == "lap"
    assert result.route == "shadow"
    assert result.matched is True
    assert result.divergences == ()
    assert result.speech_effects == ()


def test_divergent_director_selection_records_reason_without_speech_effects() -> None:
    world = _world()
    candidate = _cand()
    decision = StoryDirector().evaluate(world, (candidate,))
    assert decision.selected is not None

    result = compare_director_decisions(
        family="lap",
        legacy_selected_beat_id="legacy.other_beat",
        legacy_reason="legacy_pick",
        world=world,
        candidates=(candidate,),
    )
    assert result.matched is False
    assert result.speech_effects == ()
    assert len(result.divergences) == 1
    row = result.divergences[0]
    assert isinstance(row, DivergenceRecord)
    assert row.family == "lap"
    assert row.aspect == "director"
    assert row.reason == "selected_beat_mismatch"
    assert row.legacy_fingerprint == "legacy.other_beat"
    assert row.v2_fingerprint == decision.selected.beat_id


def test_compare_does_not_invoke_mailbox_or_tts_hooks() -> None:
    """Observational path must not accept side-effect callables."""

    world = _world()
    candidate = _cand()
    with pytest.raises(TypeError):
        compare_director_decisions(
            family="lap",
            legacy_selected_beat_id="battle.approach",
            legacy_reason="ok",
            world=world,
            candidates=(candidate,),
            on_speech=lambda *_a, **_k: None,  # type: ignore[call-arg]
        )
