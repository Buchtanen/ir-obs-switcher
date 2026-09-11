"""#272 legacy↔v2 shadow compare — observational harness tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_story_director import _cand, _world

from irswitch.events import __all__ as events_exports
from irswitch.events.envelope import make_envelope
from irswitch.events.legacy_v2_shadow_compare import (
    FAMILY_ROUTE,
    REMOVAL_MANIFEST_ENTRIES,
    DivergenceRecord,
    ShadowCompareResult,
    adapt_event_envelope_to_v2,
    adapt_race_state_to_v2,
    compare_director_decisions,
    compare_episode_decisions,
    compare_event_decisions,
    family_for_event_type,
    observe_family_safely,
    route_for_family,
    unmigrated_families,
)
from irswitch.events.story_director import StoryDirector
from irswitch.overlay.models import RaceState

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "legacy_v2_shadow_compare.py"
)
MANIFEST = (
    Path(__file__).resolve().parents[1] / "docs" / "v2.0.0" / "final-pr-exclusion-manifest.md"
)


def test_module_is_branch_private_and_documents_observation_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "Not exported from ``events/__init__.py``" in text
    assert "observation-only" in text or "Observation-only" in text
    assert "legacy_v2_shadow_compare" not in events_exports
    assert "compare_director_decisions" not in events_exports
    assert "FAMILY_ROUTE" not in events_exports


def test_lap_family_routes_to_shadow_via_private_table() -> None:
    assert FAMILY_ROUTE["lap"] == "shadow"
    assert route_for_family("lap") == "shadow"
    assert route_for_family("unknown_family") == "legacy"


def test_unmigrated_families_stay_legacy_inside_branch() -> None:
    migrated = {name for name, route in FAMILY_ROUTE.items() if route != "legacy"}
    assert migrated == {"incident", "lap", "pit", "position", "session", "timing"}
    unmigrated = unmigrated_families()
    assert "timing" not in unmigrated
    assert "pit" not in unmigrated
    assert "incident" not in unmigrated
    assert "battle" in unmigrated
    assert "bio" in unmigrated
    assert "position" not in unmigrated
    assert "session" not in unmigrated
    assert all(route_for_family(name) == "legacy" for name in unmigrated)


def test_adapt_race_state_to_v2_is_immutable_projection() -> None:
    state = RaceState(
        lap=12,
        lap_completed=11,
        session_num=2,
        subsession_id="sub:9",
        track_id="track:7",
        overlay_mode="RACE",
        run_epoch=3,
        data_quality="ok",
        stale_for_ms=None,
    )
    projection = adapt_race_state_to_v2(state)
    assert projection.lap == 12
    assert projection.overlay_mode == "RACE"
    assert "12" in projection.fingerprint
    assert projection.fingerprint == adapt_race_state_to_v2(state).fingerprint


def test_adapt_event_envelope_to_v2_maps_family_and_fingerprint() -> None:
    envelope = make_envelope(event_type="LAP_COMPLETE", phase="ENTER")
    projection = adapt_event_envelope_to_v2(envelope)
    assert projection.family == "lap"
    assert projection.fingerprint == "LAP_COMPLETE|ENTER|lap"
    assert family_for_event_type("BATTLE_OVERTAKE") == "battle"


def test_compare_event_decisions_match_and_mismatch() -> None:
    envelope = make_envelope(event_type="LAP_COMPLETE", phase="ENTER")
    matched = compare_event_decisions(
        family="lap",
        legacy_event_type="LAP_COMPLETE",
        legacy_phase="ENTER",
        envelope=envelope,
    )
    assert matched.matched is True
    assert matched.speech_effects == ()
    assert matched.latency_ms is not None
    assert matched.evidence is not None

    mismatched = compare_event_decisions(
        family="lap",
        legacy_event_type="LAP_COMPLETE",
        legacy_phase="EXIT",
        envelope=envelope,
    )
    assert mismatched.matched is False
    assert mismatched.divergences[0].aspect == "event"
    assert mismatched.divergences[0].reason == "event_fingerprint_mismatch"


def test_compare_episode_decisions_match_and_mismatch() -> None:
    matched = compare_episode_decisions(
        family="lap",
        legacy_episode_id="episode:lap:1",
        legacy_state="active",
        v2_episode_id="episode:lap:1",
        v2_state="active",
    )
    assert matched.matched is True
    assert matched.speech_effects == ()

    mismatched = compare_episode_decisions(
        family="lap",
        legacy_episode_id="episode:lap:1",
        legacy_state="active",
        v2_episode_id="episode:lap:1",
        v2_state="resolved",
    )
    assert mismatched.matched is False
    assert mismatched.divergences[0].aspect == "episode"
    assert mismatched.divergences[0].reason == "episode_fingerprint_mismatch"


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
    assert result.latency_ms is not None


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


def test_observe_family_safely_swallows_v2_failures() -> None:
    def boom() -> ShadowCompareResult:
        raise RuntimeError("v2 exploded")

    result = observe_family_safely(family="lap", observer=boom)
    assert result.matched is False
    assert result.speech_effects == ()
    assert result.divergences[0].reason == "observation_failed"
    assert result.divergences[0].v2_fingerprint == "RuntimeError"


def test_observe_family_safely_maps_timeout_and_cancellation() -> None:
    import asyncio

    timed_out = observe_family_safely(
        family="lap",
        observer=lambda: (_ for _ in ()).throw(TimeoutError("deadline")),
    )
    assert timed_out.divergences[0].reason == "observation_timeout"
    assert timed_out.speech_effects == ()

    cancelled = observe_family_safely(
        family="lap",
        observer=lambda: (_ for _ in ()).throw(asyncio.CancelledError()),
    )
    assert cancelled.divergences[0].reason == "observation_cancelled"
    assert cancelled.speech_effects == ()


def test_observe_family_safely_preserves_successful_compare() -> None:
    envelope = make_envelope(event_type="LAP_COMPLETE", phase="ENTER")
    result = observe_family_safely(
        family="lap",
        observer=lambda: compare_event_decisions(
            family="lap",
            legacy_event_type="LAP_COMPLETE",
            legacy_phase="ENTER",
            envelope=envelope,
        ),
    )
    assert result.matched is True
    assert result.speech_effects == ()


def test_stale_race_state_still_projects_for_observation() -> None:
    state = RaceState(lap=4, data_quality="stale", stale_for_ms=2500.0)
    projection = adapt_race_state_to_v2(state)
    assert projection.data_quality == "stale"
    assert projection.stale_for_ms == 2500.0


def test_compare_does_not_invoke_mailbox_or_tts_hooks() -> None:
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


def test_final_removal_manifest_lists_shadow_harness_paths() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    for entry in REMOVAL_MANIFEST_ENTRIES:
        assert entry in text
    assert "legacy_v2_shadow_compare" in text
    assert "one NarrativeRuntime" in text or "one mailbox" in text


def test_removal_manifest_entries_name_single_v2_owner_proof() -> None:
    """Architecture proof targets required before cutover (#279/#282)."""

    assert "src/irswitch/events/legacy_v2_shadow_compare.py" in REMOVAL_MANIFEST_ENTRIES
    assert "FAMILY_ROUTE" in REMOVAL_MANIFEST_ENTRIES


def test_timing_family_wires_route_to_shadow_families() -> None:
    from irswitch.contracts.timing_family_map import TIMING_WIRE_IDS
    from irswitch.events.legacy_v2_shadow_compare import family_for_event_type, route_for_family

    assert route_for_family("timing") == "shadow"
    assert route_for_family("lap") == "shadow"
    assert route_for_family("session") == "shadow"
    for wire_id in TIMING_WIRE_IDS:
        family = family_for_event_type(wire_id)
        assert family in {"lap", "timing", "session"}
        assert route_for_family(family) == "shadow"


def test_race_outcome_wires_route_to_shadow_families() -> None:
    assert family_for_event_type("OVERTAKE") == "position"
    assert family_for_event_type("OVERTAKEN") == "position"
    assert family_for_event_type("POSITION_GAINED") == "position"
    assert family_for_event_type("POSITION_LOST") == "position"
    assert family_for_event_type("LEADER_CHANGE") == "position"
    assert family_for_event_type("FINISH") == "session"
    # Battle overtake must stay on the battle family (substring trap).
    assert family_for_event_type("BATTLE_OVERTAKE") == "battle"
    assert route_for_family("position") == "shadow"
    assert route_for_family("session") == "shadow"
    assert route_for_family("battle") == "legacy"


def test_position_family_shadow_compare_stays_observation_only() -> None:
    envelope = make_envelope(event_type="POSITION_GAINED", phase="ENTER")
    result = observe_family_safely(
        family="position",
        observer=lambda: compare_event_decisions(
            family="position",
            legacy_event_type="POSITION_GAINED",
            legacy_phase="ENTER",
            envelope=envelope,
        ),
    )
    assert result.route == "shadow"
    assert result.matched is True
    assert result.speech_effects == ()


def test_ops_wires_route_to_shadow_families() -> None:
    assert family_for_event_type("PIT_ENTRY") == "pit"
    assert family_for_event_type("BACK_UNDER_WAY") == "incident"
    assert family_for_event_type("INCIDENT_AFTERMATH") == "incident"
    assert family_for_event_type("SESSION_FLAG") == "session"
    assert route_for_family("pit") == "shadow"
    assert route_for_family("incident") == "shadow"
