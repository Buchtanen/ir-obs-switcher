"""#278 Slice 5 — offline F01/F10/F17 stream + silence runtime drivers.

Consumes frozen machine rows and proves stream-before-session identity,
long-silence filler threshold scoring, and lobby stream-scope filler guards
through StreamTimeline + SilenceClock + StoryDirector + evaluate_filler.
Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_silence_clock import OPEN
from test_story_director import CandidateOrder, _cand, _world
from test_stream_timeline import _kinds, _session, _tick

from irswitch.events.silence_clock import (
    LONG_SILENCE_MS,
    FillerContext,
    FillerFact,
    SilenceClock,
    evaluate_filler,
)
from irswitch.events.story_director import (
    SELECTION_THRESHOLD,
    SILENCE_PRESSURE_BASE,
    StoryDirector,
    score_terms,
)
from irswitch.logic.stream_timeline import StreamTimeline

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE5_IDS = ("F01", "F10", "F17")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_silence_builder_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    machine_path = str(MACHINE)
    if machine_path not in sys.path:
        sys.path.insert(0, machine_path)
    spec = importlib.util.spec_from_file_location(module_name, BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE5_IDS)
def test_slice5_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f01_stream_starts_before_session_without_inventing_session(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F01: attached stream start keeps null session identity; silence arms after terminal."""

    expected = set(fixtures_by_id["F01"]["expectations"])
    observed: set[str] = set()

    timeline = StreamTimeline()
    step = timeline.observe(
        _tick(
            1_000,
            epoch=1,
            state="active",
            enabled=True,
            session=_session(
                connected=False,
                availability="unavailable",
                sub_session_id=None,
                session_num=None,
                session_time_s=None,
            ),
        )
    )
    assert _kinds(step) == ["STREAM_STARTED"]
    started = next(cmd for cmd in step.commands if cmd.kind == "STREAM_STARTED")
    assert started.start_reason == "attached_live"
    assert step.snapshot["sessionRef"] is None
    assert step.snapshot["occurrenceId"] is None
    assert step.snapshot["lineageId"] is None
    assert step.snapshot["stage"] is None
    observed.add("stream_scope_identity_null")

    authored = _cand(
        beat_id="stream.started",
        episode_id="episode:stream",
        source="authored",
        relation="opens_new_episode",
        opportunity_id="opp:stream",
        base_priority=90.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=False,
        urgency="critical",
        policy_id="critical",
        candidate_order=CandidateOrder(1, 0),
    )
    world = _world(focused_episode_id=None, impulse="idle")
    decision = StoryDirector().evaluate(world, (authored,))
    assert decision.selected is not None
    assert decision.selected.beat_id == "stream.started"
    assert decision.selected.score == 90.0
    observed.add("authored_stream_start")

    assert "SESSION_STARTED" not in _kinds(step)
    assert decision.selected.beat_id != "session.intro"
    observed.add("no_session_invented")

    clock = SilenceClock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    cancelled = clock.on_playback_accepted(now_ms=50)
    assert cancelled.reason == "cancelled_playback_accepted"
    assert clock.deadline_mono_ms is None
    terminal = clock.on_speech_terminal(now_ms=100, window=OPEN)
    assert terminal.reason == "armed"
    assert terminal.deadline_mono_ms == 100 + LONG_SILENCE_MS
    observed.add("silence_after_terminal")

    assert observed == expected


def test_f10_long_silence_filler_clears_threshold_and_rearms(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F10: 24+12 silence pressure selects filler.out_lap; missing fact stays silent + full rearm."""

    expected = set(fixtures_by_id["F10"]["expectations"])
    observed: set[str] = set()

    calc_score, calc_threshold = fixtures_by_id["F10"]["calculations"]
    assert builder.evaluate(calc_score) == 36
    assert builder.evaluate(calc_threshold) is True
    assert SILENCE_PRESSURE_BASE == 12.0
    assert SELECTION_THRESHOLD == 35.0

    filler = _cand(
        beat_id="filler.out_lap",
        episode_id="episode:filler",
        source="filler",
        relation="opens_new_episode",
        opportunity_id="opp:filler",
        base_priority=24.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=False,
        urgency="context",
        policy_id="filler",
        candidate_order=CandidateOrder(1, 0),
    )
    world = _world(focused_episode_id=None, impulse="silence", silence_impulse=True)
    terms = score_terms(filler, world, replacing=False)
    assert terms.base == 24.0
    assert terms.silence_pressure == 12.0
    assert terms.total == 36.0
    assert terms.total >= SELECTION_THRESHOLD
    observed.add("score_36")

    decision = StoryDirector().evaluate(world, (filler,))
    assert decision.selected is not None
    assert decision.selected.beat_id == "filler.out_lap"
    assert decision.selected.score == 36.0

    ok = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="out_lap",
            has_session_ref=True,
            occurrence_id="occ:1",
            lineage_id="lin:1",
            has_live_race_opportunity=False,
            facts=(
                FillerFact("vehicle.phase", "occurrence", True),
                FillerFact("context.track_identity", "occurrence", True),
            ),
        )
    )
    assert ok.beat_id == "filler.out_lap"
    assert ok.reason == "selected"
    observed.add("filler_selected")

    missing = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="out_lap",
            has_session_ref=True,
            occurrence_id="occ:1",
            lineage_id="lin:1",
            has_live_race_opportunity=False,
            facts=(FillerFact("vehicle.phase", "occurrence", True),),
        )
    )
    assert missing.beat_id is None
    assert missing.reason == "source_guard_failed"
    observed.add("missing_fact_silence")

    clock = SilenceClock()
    armed = clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    assert armed.deadline_mono_ms == LONG_SILENCE_MS
    elapsed = clock.on_elapsed(
        generation=1,
        deadline_mono_ms=LONG_SILENCE_MS,
        now_ms=LONG_SILENCE_MS,
        lane="idle",
    )
    assert elapsed.impulse is not None
    assert elapsed.impulse.kind == "LONG_SILENCE_ELAPSED"
    assert elapsed.deadline_mono_ms == 2 * LONG_SILENCE_MS
    observed.add("normal_rearm")

    assert observed == expected


def test_f17_lobby_filler_uses_stream_facts_only(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F17: lobby filler stays stream-scoped; missing track identity guards and rearms."""

    expected = set(fixtures_by_id["F17"]["expectations"])
    observed: set[str] = set()

    facts = (
        FillerFact("context.track_identity", "stream", True),
        FillerFact("broadcast.context", "stream", True),
    )
    assert len(facts) == 2
    observed.add("exact_two_facts")

    ok = evaluate_filler(
        FillerContext(
            broadcast_context="lobby",
            vehicle_phase=None,
            has_session_ref=False,
            occurrence_id=None,
            lineage_id=None,
            has_live_race_opportunity=False,
            facts=facts,
        )
    )
    assert ok.beat_id == "filler.lobby"
    assert ok.scope == "stream"
    assert ok.story_id == "filler_single"
    observed.add("stream_scope_filler")
    assert ok.occurrence_id is None
    assert ok.lineage_id is None
    observed.add("null_occurrence")
    assert ok.scope != "occurrence"
    observed.add("no_session_claim")

    missing = evaluate_filler(
        FillerContext(
            broadcast_context="lobby",
            vehicle_phase=None,
            has_session_ref=False,
            occurrence_id=None,
            lineage_id=None,
            has_live_race_opportunity=False,
            facts=(),
        )
    )
    assert missing.beat_id is None
    assert missing.reason == "source_guard_failed"

    clock = SilenceClock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    elapsed = clock.on_elapsed(
        generation=1,
        deadline_mono_ms=LONG_SILENCE_MS,
        now_ms=LONG_SILENCE_MS,
        lane="idle",
    )
    assert elapsed.impulse is not None
    assert elapsed.deadline_mono_ms == 2 * LONG_SILENCE_MS
    observed.add("missing_track_guard_rearm")

    assert observed == expected
