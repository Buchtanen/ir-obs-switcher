"""#260 long-silence clock and filler opportunities."""

from __future__ import annotations

from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.silence_clock import (
    LONG_SILENCE_MS,
    FillerContext,
    FillerFact,
    SilenceClock,
    evaluate_filler,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "silence_clock.py"

OPEN = {
    "runtime_status": "ready",
    "commentary_enabled": True,
    "narrative_run_active": True,
    "obs_state": "active",
}


def _clock(interval_ms: int = 1_000) -> SilenceClock:
    return SilenceClock(interval_ms=interval_ms)


def _fact(
    predicate: str,
    *,
    scope: str = "occurrence",
    fresh: bool = True,
    weather_source: str | None = None,
) -> FillerFact:
    return FillerFact(
        predicate=predicate,
        scope=scope,
        fresh=fresh,
        weather_source=weather_source,
    )


def test_first_filler_cannot_fire_before_full_interval_after_stream_start() -> None:
    clock = _clock()
    armed = clock.after_lifecycle(now_ms=10_000, window=OPEN, speech_accepted=False)
    assert armed.reason == "armed"
    assert armed.generation == 1
    assert armed.deadline_mono_ms == 11_000
    assert armed.impulse is None

    early = clock.on_elapsed(generation=1, deadline_mono_ms=11_000, now_ms=10_999, lane="idle")
    assert early.impulse is None
    assert early.reason == "deadline_pending"
    assert clock.deadline_mono_ms == 11_000


def test_elapsed_is_one_shot_and_rearms_exactly_interval() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    step = clock.on_elapsed(generation=1, deadline_mono_ms=1_000, now_ms=1_000, lane="idle")
    assert step.impulse is not None
    assert step.impulse.kind == "LONG_SILENCE_ELAPSED"
    assert step.impulse.generation == 1
    assert step.reason == "rearmed"
    assert step.generation == 2
    assert step.deadline_mono_ms == 2_000

    stale = clock.on_elapsed(generation=1, deadline_mono_ms=1_000, now_ms=1_500, lane="idle")
    assert stale.reason == "stale_token"
    assert stale.impulse is None
    assert clock.generation == 2


def test_playback_accepted_cancels_and_terminal_rearms() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    cancelled = clock.on_playback_accepted(now_ms=400)
    assert cancelled.reason == "cancelled_playback_accepted"
    assert clock.deadline_mono_ms is None
    late = clock.on_elapsed(generation=1, deadline_mono_ms=1_000, now_ms=1_000, lane="speaking")
    assert late.reason == "stale_token"

    rearmed = clock.on_speech_terminal(now_ms=800, window=OPEN)
    assert rearmed.reason == "armed"
    assert rearmed.generation == 2
    assert rearmed.deadline_mono_ms == 1_800


def test_building_committed_do_not_move_origin() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    again = clock.after_lifecycle(now_ms=200, window=OPEN, speech_accepted=False)
    assert again.reason == "origin_unchanged"
    assert clock.deadline_mono_ms == 1_000
    race = clock.on_race_event(now_ms=300)
    assert race.reason == "origin_unchanged"
    assert clock.deadline_mono_ms == 1_000


def test_obs_unknown_pauses_without_credit_and_resume_rearms_full_interval() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    paused = clock.on_obs_unknown(now_ms=400)
    assert paused.reason == "paused_obs_unknown"
    assert clock.deadline_mono_ms is None
    resume = clock.on_audience_resume(now_ms=900, window=OPEN)
    assert resume.reason == "armed"
    assert resume.deadline_mono_ms == 1_900
    assert resume.generation == 2


def test_disable_and_shutdown_cancel_without_credit() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    disabled = clock.on_commentary_disabled(now_ms=100)
    assert disabled.reason == "cancelled_commentary_disabled"
    assert clock.deadline_mono_ms is None
    clock.after_lifecycle(now_ms=200, window=OPEN, speech_accepted=False)
    stopped = clock.on_shutdown(now_ms=250)
    assert stopped.reason == "cancelled_shutdown"
    assert clock.deadline_mono_ms is None


def test_busy_lane_selects_no_filler_and_rearms() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    step = clock.on_elapsed(generation=1, deadline_mono_ms=1_000, now_ms=1_000, lane="building")
    assert step.impulse is not None
    assert step.filler is None
    assert step.reason == "rearmed"
    assert step.deadline_mono_ms == 2_000


def test_config_change_does_not_move_armed_deadline() -> None:
    clock = _clock(interval_ms=1_000)
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    clock.set_interval_ms(5_000)
    assert clock.deadline_mono_ms == 1_000
    clock.on_speech_terminal(now_ms=2_000, window=OPEN)
    assert clock.deadline_mono_ms == 7_000


def test_lobby_stream_scope_requires_fresh_track_identity() -> None:
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
    assert missing.scope is None

    ok = evaluate_filler(
        FillerContext(
            broadcast_context="lobby",
            vehicle_phase=None,
            has_session_ref=False,
            occurrence_id=None,
            lineage_id=None,
            has_live_race_opportunity=False,
            facts=(_fact("context.track_identity", scope="stream"),),
        )
    )
    assert ok.beat_id == "filler.lobby"
    assert ok.scope == "stream"
    assert ok.story_id == "filler_single"
    assert ok.occurrence_id is None
    assert ok.lineage_id is None


def test_other_fillers_require_occurrence_and_phase_facts() -> None:
    no_session = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="out_lap",
            has_session_ref=False,
            occurrence_id=None,
            lineage_id=None,
            has_live_race_opportunity=False,
            facts=(_fact("vehicle.phase"), _fact("context.track_identity")),
        )
    )
    assert no_session.beat_id is None
    assert no_session.reason == "source_guard_failed"

    out_lap = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="out_lap",
            has_session_ref=True,
            occurrence_id="3:race:0",
            lineage_id="3:practice:0>3:race:0",
            has_live_race_opportunity=False,
            facts=(_fact("vehicle.phase"), _fact("context.track_identity")),
        )
    )
    assert out_lap.beat_id == "filler.out_lap"
    assert out_lap.scope == "occurrence"


def test_empty_allowlist_and_unsupported_weather_do_not_invent_claims() -> None:
    empty = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="out_lap",
            has_session_ref=True,
            occurrence_id="3:race:0",
            lineage_id="3:practice:0>3:race:0",
            has_live_race_opportunity=False,
            facts=(_fact("vehicle.phase"),),
        )
    )
    assert empty.reason == "source_guard_failed"
    assert empty.beat_id is None

    forecast = evaluate_filler(
        FillerContext(
            broadcast_context="garage",
            vehicle_phase=None,
            has_session_ref=True,
            occurrence_id="3:race:0",
            lineage_id="3:practice:0>3:race:0",
            has_live_race_opportunity=False,
            facts=(_fact("weather.skies", weather_source="forecast"),),
        )
    )
    assert forecast.reason == "source_guard_failed"
    assert forecast.beat_id is None

    race = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="racing",
            has_session_ref=True,
            occurrence_id="3:race:0",
            lineage_id="3:practice:0>3:race:0",
            has_live_race_opportunity=False,
            facts=(_fact("position.passed"),),
        )
    )
    assert race.reason == "source_guard_failed"
    assert race.beat_id is None


def test_race_candidate_replaces_uncommitted_filler_without_moving_origin() -> None:
    clock = _clock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    clock.pending_filler = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="out_lap",
            has_session_ref=True,
            occurrence_id="3:race:0",
            lineage_id="3:practice:0>3:race:0",
            has_live_race_opportunity=False,
            facts=(_fact("vehicle.phase"), _fact("context.field_size")),
        )
    )
    assert clock.pending_filler.beat_id == "filler.out_lap"
    step = clock.on_race_event(now_ms=200)
    assert step.reason == "race_replaces_uncommitted_filler"
    assert clock.pending_filler is None
    assert clock.deadline_mono_ms == 1_000


def test_director_may_select_silence_again() -> None:
    quiet = evaluate_filler(
        FillerContext(
            broadcast_context="on_track",
            vehicle_phase="racing",
            has_session_ref=True,
            occurrence_id="3:race:0",
            lineage_id="3:practice:0>3:race:0",
            has_live_race_opportunity=True,
            facts=(_fact("context.track_identity"),),
        )
    )
    assert quiet.beat_id is None
    assert quiet.reason == "no_candidate"


def test_defaults_match_public_contract_and_exports_stay_out_of_events() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert LONG_SILENCE_MS == 33_000
    assert "silence_clock" not in events_exports
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "BeatPlan",
        "TtsUtterance",
    ):
        assert banned not in source
