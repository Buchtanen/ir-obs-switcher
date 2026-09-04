from __future__ import annotations

from irswitch.race.editorial_stage import (
    EditorialStage,
    EditorialStageController,
    EditorialStageFeedback,
    EditorialStageInput,
)


def _state(**overrides: object) -> EditorialStageInput:
    values: dict[str, object] = {
        "connected": True,
        "context_ready": True,
        "session_id": "42:0",
        "overlay_mode": "PRACTICE",
        "run_epoch": 1,
        "in_car": False,
        "on_pit_road": False,
    }
    values.update(overrides)
    return EditorialStageInput(**values)  # type: ignore[arg-type]


def test_stream_waits_for_context_then_opens_intro() -> None:
    stages = EditorialStageController()
    assert stages.note_stream_started().stage == EditorialStage.WAIT_CONTEXT
    assert stages.observe(_state(connected=False)).stage == EditorialStage.WAIT_CONTEXT
    snap = stages.observe(_state())
    assert snap.stage == EditorialStage.STREAM_LOBBY_INTRO
    assert snap.stream_epoch == 1


def test_practice_enter_car_drains_whole_intro() -> None:
    stages = EditorialStageController()
    stages.note_stream_started()
    stages.observe(_state())
    snap = stages.observe(_state(in_car=True, on_pit_road=True))
    assert snap.stage == EditorialStage.STREAM_LOBBY_INTRO
    assert snap.practice_intro_draining is True
    assert stages.complete_intro_chain().stage == EditorialStage.IN_CAR_PREP


def test_qualifying_enter_car_cuts_to_event_intro() -> None:
    stages = EditorialStageController()
    stages.note_stream_started()
    stages.observe(_state(overlay_mode="QUALIFYING"))
    snap = stages.observe(_state(overlay_mode="QUALIFYING", in_car=True, on_pit_road=True))
    assert snap.stage == EditorialStage.SESSION_EVENT_INTRO
    assert snap.practice_intro_draining is False


def test_pit_exit_opens_one_out_lap_and_wrap_closes_it() -> None:
    stages = EditorialStageController()
    stages.note_stream_started()
    stages.observe(_state())
    stages.observe(_state(in_car=True, on_pit_road=True, lap_completed=2))
    stages.complete_intro_chain()
    snap = stages.observe(_state(in_car=True, on_pit_road=False, lap_completed=2))
    assert snap.stage == EditorialStage.OUT_LAP
    assert snap.stint_epoch == 1
    assert stages.observe(_state(in_car=True, lap_completed=3)).stage == EditorialStage.LIVE_SESSION


def test_practice_pit_return_reopens_preparation_before_next_out_lap() -> None:
    stages = EditorialStageController()
    stages.note_stream_started()
    stages.observe(_state())
    stages.observe(_state(in_car=True, on_pit_road=True, lap_completed=2))
    stages.complete_intro_chain()
    stages.observe(_state(in_car=True, on_pit_road=False, lap_completed=2))
    stages.observe(_state(in_car=True, on_pit_road=False, lap_completed=3))

    returned = stages.observe(_state(in_car=True, on_pit_road=True, lap_completed=3))
    next_exit = stages.observe(_state(in_car=True, on_pit_road=False, lap_completed=3))

    assert returned.stage == EditorialStage.IN_CAR_PREP
    assert next_exit.stage == EditorialStage.OUT_LAP
    assert next_exit.stint_epoch == 2


def test_green_and_finish_take_precedence() -> None:
    stages = EditorialStageController()
    stages.note_stream_started()
    stages.observe(_state(overlay_mode="RACE", in_car=True, session_state=3))
    assert (
        stages.observe(_state(overlay_mode="RACE", green=True)).stage == EditorialStage.LIVE_SESSION
    )
    assert (
        stages.observe(_state(overlay_mode="RACE", player_finished=True)).stage
        == EditorialStage.SESSION_CONCLUSION
    )


def test_disconnect_and_stop_invalidate_active_stage() -> None:
    stages = EditorialStageController()
    stages.note_stream_started()
    stages.observe(_state())
    assert stages.observe(_state(connected=False)).stage == EditorialStage.WAIT_CONTEXT
    assert stages.note_stream_stopped().stage == EditorialStage.INACTIVE


def test_run_restart_forces_new_epoch_even_when_physical_stage_is_same() -> None:
    stages = EditorialStageController()
    stages.note_stream_started(1_000)
    stages.observe(_state(run_epoch=1, observed_monotonic_ms=2_000))
    stages.complete_intro_chain(2_100)
    stages.observe(
        _state(
            in_car=True,
            on_pit_road=True,
            lap_completed=0,
            run_epoch=1,
            observed_monotonic_ms=2_200,
        )
    )
    stages.observe(
        _state(
            in_car=True,
            on_pit_road=False,
            lap_completed=0,
            run_epoch=1,
            observed_monotonic_ms=2_300,
        )
    )
    stages.observe(
        _state(
            in_car=True,
            on_pit_road=False,
            lap_completed=1,
            run_epoch=1,
            observed_monotonic_ms=2_400,
        )
    )
    before = stages.snapshot

    after = stages.observe(
        _state(in_car=True, on_pit_road=False, run_epoch=2, observed_monotonic_ms=3_000)
    )

    assert after.stage == before.stage == EditorialStage.LIVE_SESSION
    assert after.stage_epoch == before.stage_epoch + 1
    assert after.run_epoch == 2


def test_stale_completion_feedback_cannot_close_new_stream_stage() -> None:
    stages = EditorialStageController()
    first = stages.note_stream_started(1_000)
    intro = stages.observe(_state(observed_monotonic_ms=2_000))
    stale = EditorialStageFeedback(
        stream_epoch=first.stream_epoch,
        stage_epoch=intro.stage_epoch,
        stage=EditorialStage.STREAM_LOBBY_INTRO,
        action="intro_chain_completed",
        observed_monotonic_ms=2_500,
    )
    stages.note_stream_stopped(3_000)
    stages.note_stream_started(4_000)
    current = stages.observe(_state(observed_monotonic_ms=5_000))

    assert current.stage == EditorialStage.STREAM_LOBBY_INTRO
    assert stages.apply_feedback(stale) == current


def test_snapshot_predicts_next_stage_for_reserved_generation() -> None:
    stages = EditorialStageController()
    stages.note_stream_started(1_000)
    intro = stages.observe(_state(overlay_mode="RACE", observed_monotonic_ms=2_000))
    assert intro.next_stage == EditorialStage.SESSION_EVENT_INTRO
    event_intro = stages.observe(
        _state(overlay_mode="RACE", in_car=True, observed_monotonic_ms=3_000)
    )
    assert event_intro.next_stage == EditorialStage.GRID_PREP


def test_completed_conclusion_stays_closed_while_finish_flags_remain_set() -> None:
    stages = EditorialStageController()
    stages.note_stream_started(1_000)
    stages.observe(_state(overlay_mode="RACE", observed_monotonic_ms=2_000))
    conclusion = stages.observe(
        _state(
            overlay_mode="RACE",
            player_finished=True,
            result_confirmed=True,
            observed_monotonic_ms=3_000,
        )
    )
    feedback = EditorialStageFeedback(
        stream_epoch=conclusion.stream_epoch,
        stage_epoch=conclusion.stage_epoch,
        stage=EditorialStage.SESSION_CONCLUSION,
        action="conclusion_completed",
        observed_monotonic_ms=4_000,
    )

    assert stages.apply_feedback(feedback).stage == EditorialStage.BETWEEN_SESSIONS
    assert (
        stages.observe(
            _state(
                overlay_mode="RACE",
                player_finished=True,
                green=True,
                result_confirmed=True,
                observed_monotonic_ms=5_000,
            )
        ).stage
        == EditorialStage.BETWEEN_SESSIONS
    )
