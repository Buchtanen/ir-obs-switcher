"""Producer-owned editorial stage state machine for prepared commentary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

_NEXT_HANDOFF_MODE = {
    "PRACTICE": "QUALIFYING",
    "QUALIFYING": "RACE",
}


class EditorialStage(StrEnum):
    INACTIVE = "INACTIVE"
    WAIT_CONTEXT = "WAIT_CONTEXT"
    STREAM_LOBBY_INTRO = "STREAM_LOBBY_INTRO"
    SESSION_EVENT_INTRO = "SESSION_EVENT_INTRO"
    IN_CAR_PREP = "IN_CAR_PREP"
    OUT_LAP = "OUT_LAP"
    GRID_PREP = "GRID_PREP"
    FORMATION_OR_LIGHTS = "FORMATION_OR_LIGHTS"
    LIVE_SESSION = "LIVE_SESSION"
    SESSION_CONCLUSION = "SESSION_CONCLUSION"
    BETWEEN_SESSIONS = "BETWEEN_SESSIONS"


@dataclass(frozen=True, slots=True)
class EditorialStageInput:
    connected: bool
    context_ready: bool
    session_id: str
    overlay_mode: str
    run_epoch: int = 0
    in_car: bool = False
    on_pit_road: bool = False
    session_state: int | None = None
    lap_completed: int | None = None
    player_finished: bool = False
    session_checkered: bool = False
    green: bool = False
    reset_or_tow: bool = False
    observed_monotonic_ms: int = 0
    result_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class EditorialStageSnapshot:
    stage: EditorialStage
    stage_epoch: int
    stream_epoch: int
    session_id: str | None
    run_epoch: int
    practice_intro_draining: bool
    stint_epoch: int
    next_stage: EditorialStage | None
    stage_started_monotonic_ms: int
    holdover_stage: EditorialStage | None
    holdover_stage_epoch: int
    intro_line_spoken: bool
    handoff_overlay_mode: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "stage_epoch": self.stage_epoch,
            "stream_epoch": self.stream_epoch,
            "session_id": self.session_id,
            "run_epoch": self.run_epoch,
            "practice_intro_draining": self.practice_intro_draining,
            "stint_epoch": self.stint_epoch,
            "next_stage": self.next_stage.value if self.next_stage is not None else None,
            "stage_started_monotonic_ms": self.stage_started_monotonic_ms,
            "holdover_stage": (
                self.holdover_stage.value if self.holdover_stage is not None else None
            ),
            "holdover_stage_epoch": self.holdover_stage_epoch,
            "intro_line_spoken": self.intro_line_spoken,
            "handoff_overlay_mode": self.handoff_overlay_mode,
        }


@dataclass(frozen=True, slots=True)
class EditorialStageFeedback:
    """Versioned completion signal returned by the commentary lane."""

    stream_epoch: int
    stage_epoch: int
    stage: EditorialStage
    action: Literal[
        "intro_chain_completed",
        "session_intro_completed",
        "conclusion_completed",
        "intro_holdover_completed",
    ]
    observed_monotonic_ms: int


class EditorialStageController:
    """Deterministic stage owner; callers provide already-normalized state."""

    def __init__(self) -> None:
        self._stage = EditorialStage.INACTIVE
        self._stage_epoch = 0
        self._stream_epoch = 0
        self._session_id: str | None = None
        self._run_epoch = 0
        self._stint_epoch = 0
        self._practice_intro_draining = False
        self._previous_pit = False
        self._out_lap_origin: int | None = None
        self._stage_started_monotonic_ms = 0
        self._overlay_mode = "GENERIC"
        self._holdover_stage: EditorialStage | None = None
        self._holdover_stage_epoch = 0
        self._intro_line_spoken = False
        self._handoff_overlay_mode: str | None = None

    @property
    def snapshot(self) -> EditorialStageSnapshot:
        return EditorialStageSnapshot(
            stage=self._stage,
            stage_epoch=self._stage_epoch,
            stream_epoch=self._stream_epoch,
            session_id=self._session_id,
            run_epoch=self._run_epoch,
            practice_intro_draining=self._practice_intro_draining,
            stint_epoch=self._stint_epoch,
            next_stage=self._next_stage(),
            stage_started_monotonic_ms=self._stage_started_monotonic_ms,
            holdover_stage=self._holdover_stage,
            holdover_stage_epoch=self._holdover_stage_epoch,
            intro_line_spoken=self._intro_line_spoken,
            handoff_overlay_mode=self._handoff_overlay_mode,
        )

    def note_stream_started(self, observed_monotonic_ms: int = 0) -> EditorialStageSnapshot:
        if self._stage == EditorialStage.INACTIVE:
            self._stream_epoch += 1
            self._session_id = None
            self._run_epoch = 0
            self._stint_epoch = 0
            self._practice_intro_draining = False
            self._clear_intro_holdover()
            self._intro_line_spoken = False
            self._handoff_overlay_mode = None
            self._transition(EditorialStage.WAIT_CONTEXT, observed_monotonic_ms)
        return self.snapshot

    def note_stream_stopped(self, observed_monotonic_ms: int = 0) -> EditorialStageSnapshot:
        self._session_id = None
        self._run_epoch = 0
        self._stint_epoch = 0
        self._practice_intro_draining = False
        self._out_lap_origin = None
        self._previous_pit = False
        self._clear_intro_holdover()
        self._intro_line_spoken = False
        self._handoff_overlay_mode = None
        self._transition(EditorialStage.INACTIVE, observed_monotonic_ms)
        return self.snapshot

    def observe(self, item: EditorialStageInput) -> EditorialStageSnapshot:
        if self._stage == EditorialStage.INACTIVE:
            return self.snapshot
        self._overlay_mode = item.overlay_mode
        if not item.connected:
            self._session_id = None
            self._out_lap_origin = None
            self._practice_intro_draining = False
            self._clear_intro_holdover()
            self._intro_line_spoken = False
            self._handoff_overlay_mode = None
            self._transition(EditorialStage.WAIT_CONTEXT, item.observed_monotonic_ms)
            self._previous_pit = item.on_pit_road
            return self.snapshot
        if not item.context_ready:
            # iRacing is connected but the session is still loading (~50 s).
            # Stay in lobby so prepared filler can speak stream colour.
            if self._stage in {EditorialStage.WAIT_CONTEXT, EditorialStage.STREAM_LOBBY_INTRO}:
                self._transition(EditorialStage.STREAM_LOBBY_INTRO, item.observed_monotonic_ms)
            self._previous_pit = item.on_pit_road
            return self.snapshot

        session_changed = self._session_id is not None and item.session_id != self._session_id
        run_changed = self._session_id == item.session_id and item.run_epoch != self._run_epoch
        self._session_id = item.session_id
        self._run_epoch = item.run_epoch

        if self._stage == EditorialStage.WAIT_CONTEXT:
            self._transition(EditorialStage.STREAM_LOBBY_INTRO, item.observed_monotonic_ms)
        elif session_changed:
            self._practice_intro_draining = False
            self._out_lap_origin = None
            self._stint_epoch = 0
            if self._handoff_overlay_mode == item.overlay_mode and self._stage in {
                EditorialStage.SESSION_EVENT_INTRO,
                EditorialStage.IN_CAR_PREP,
                EditorialStage.GRID_PREP,
            }:
                self._handoff_overlay_mode = None
            else:
                self._handoff_overlay_mode = None
                self._clear_intro_holdover()
                self._intro_line_spoken = False
                self._transition(
                    EditorialStage.SESSION_EVENT_INTRO, item.observed_monotonic_ms, force=True
                )
        elif run_changed:
            self._practice_intro_draining = False
            self._out_lap_origin = None
            self._stint_epoch = 0
            self._clear_intro_holdover()
            self._intro_line_spoken = False
            self._transition(self._physical_stage(item), item.observed_monotonic_ms, force=True)

        if self._stage == EditorialStage.BETWEEN_SESSIONS and not (session_changed or run_changed):
            self._previous_pit = item.on_pit_road
            return self.snapshot

        if (item.player_finished and (item.overlay_mode != "RACE" or not item.in_car)) or (
            item.session_checkered and item.overlay_mode in {"PRACTICE", "QUALIFYING"}
        ):
            self._practice_intro_draining = False
            self._out_lap_origin = None
            self._clear_intro_holdover()
            self._transition(EditorialStage.SESSION_CONCLUSION, item.observed_monotonic_ms)
        elif item.overlay_mode == "RACE" and (item.green or item.session_state == 4):
            self._arm_intro_holdover()
            self._practice_intro_draining = False
            self._out_lap_origin = None
            self._transition(EditorialStage.LIVE_SESSION, item.observed_monotonic_ms)
        elif self._stage == EditorialStage.STREAM_LOBBY_INTRO and item.in_car:
            if item.overlay_mode == "PRACTICE":
                self._practice_intro_draining = True
            elif item.overlay_mode in {"QUALIFYING", "RACE"}:
                self._practice_intro_draining = False
                self._transition(EditorialStage.SESSION_EVENT_INTRO, item.observed_monotonic_ms)
        elif item.overlay_mode in {"PRACTICE", "QUALIFYING"}:
            self._observe_out_lap(item)
        elif item.overlay_mode == "RACE" and item.in_car:
            if item.session_state == 3:
                self._transition(EditorialStage.FORMATION_OR_LIGHTS, item.observed_monotonic_ms)
            elif self._stage in {
                EditorialStage.SESSION_EVENT_INTRO,
                EditorialStage.STREAM_LOBBY_INTRO,
            }:
                self._transition(EditorialStage.GRID_PREP, item.observed_monotonic_ms)

        self._previous_pit = item.on_pit_road
        return self.snapshot

    def apply_feedback(self, feedback: EditorialStageFeedback) -> EditorialStageSnapshot:
        """Apply only completion feedback for the exact active stream/stage epoch."""
        if feedback.action == "intro_holdover_completed":
            if (
                feedback.stream_epoch == self._stream_epoch
                and self._holdover_stage == feedback.stage
                and self._holdover_stage_epoch == feedback.stage_epoch
            ):
                self._clear_intro_holdover(spoken=True)
            return self.snapshot
        if (
            feedback.stream_epoch != self._stream_epoch
            or feedback.stage_epoch != self._stage_epoch
            or feedback.stage != self._stage
        ):
            return self.snapshot
        if feedback.action == "intro_chain_completed":
            return self.complete_intro_chain(feedback.observed_monotonic_ms)
        if feedback.action == "session_intro_completed":
            return self.complete_session_intro_at(feedback.observed_monotonic_ms)
        if feedback.action == "conclusion_completed":
            return self.complete_conclusion(feedback.observed_monotonic_ms)
        return self.snapshot

    def complete_intro_chain(self, observed_monotonic_ms: int = 0) -> EditorialStageSnapshot:
        if self._stage != EditorialStage.STREAM_LOBBY_INTRO:
            return self.snapshot
        draining = self._practice_intro_draining
        self._practice_intro_draining = False
        self._intro_line_spoken = True
        # Still in lobby: speak the session intro next. Already in-car practice
        # drains the stream chain straight into prep.
        target = EditorialStage.IN_CAR_PREP if draining else EditorialStage.SESSION_EVENT_INTRO
        self._transition(target, observed_monotonic_ms)
        return self.snapshot

    def complete_session_intro(self, item: EditorialStageInput) -> EditorialStageSnapshot:
        if self._stage == EditorialStage.SESSION_EVENT_INTRO:
            self._transition(self._physical_stage(item), item.observed_monotonic_ms)
        return self.snapshot

    def complete_session_intro_at(self, observed_monotonic_ms: int) -> EditorialStageSnapshot:
        if self._stage != EditorialStage.SESSION_EVENT_INTRO:
            return self.snapshot
        if self._overlay_mode == "RACE" or self._handoff_overlay_mode == "RACE":
            target = EditorialStage.GRID_PREP
        else:
            target = EditorialStage.IN_CAR_PREP
        self._intro_line_spoken = True
        self._transition(target, observed_monotonic_ms)
        return self.snapshot

    def complete_conclusion(self, observed_monotonic_ms: int = 0) -> EditorialStageSnapshot:
        if self._stage != EditorialStage.SESSION_CONCLUSION:
            return self.snapshot
        handoff = _NEXT_HANDOFF_MODE.get(self._overlay_mode)
        if handoff is None:
            self._handoff_overlay_mode = None
            self._transition(EditorialStage.BETWEEN_SESSIONS, observed_monotonic_ms)
            return self.snapshot
        self._handoff_overlay_mode = handoff
        self._intro_line_spoken = False
        self._transition(EditorialStage.SESSION_EVENT_INTRO, observed_monotonic_ms)
        return self.snapshot

    def _observe_out_lap(self, item: EditorialStageInput) -> None:
        if self._stage in {EditorialStage.LIVE_SESSION, EditorialStage.OUT_LAP} and (
            not item.in_car or item.on_pit_road
        ):
            self._out_lap_origin = None
            self._transition(EditorialStage.IN_CAR_PREP, item.observed_monotonic_ms)
            return
        pit_exit = self._previous_pit and not item.on_pit_road and item.in_car
        if pit_exit:
            self._stint_epoch += 1
            self._out_lap_origin = item.lap_completed
            self._transition(EditorialStage.OUT_LAP, item.observed_monotonic_ms)
            return
        if self._stage != EditorialStage.OUT_LAP:
            return
        wrapped = (
            self._out_lap_origin is not None
            and item.lap_completed is not None
            and item.lap_completed > self._out_lap_origin
        )
        if item.on_pit_road or item.reset_or_tow:
            self._out_lap_origin = None
            self._transition(EditorialStage.IN_CAR_PREP, item.observed_monotonic_ms)
        elif wrapped:
            self._out_lap_origin = None
            self._transition(EditorialStage.LIVE_SESSION, item.observed_monotonic_ms)

    @staticmethod
    def _physical_stage(item: EditorialStageInput) -> EditorialStage:
        if not item.in_car:
            return EditorialStage.SESSION_EVENT_INTRO
        if item.overlay_mode in {"PRACTICE", "QUALIFYING"}:
            return EditorialStage.IN_CAR_PREP if item.on_pit_road else EditorialStage.LIVE_SESSION
        if item.overlay_mode == "RACE":
            return (
                EditorialStage.FORMATION_OR_LIGHTS
                if item.session_state == 3
                else EditorialStage.GRID_PREP
            )
        return EditorialStage.LIVE_SESSION

    def _arm_intro_holdover(self) -> None:
        if self._stage not in {
            EditorialStage.STREAM_LOBBY_INTRO,
            EditorialStage.SESSION_EVENT_INTRO,
        }:
            return
        self._holdover_stage = self._stage
        self._holdover_stage_epoch = self._stage_epoch

    def _clear_intro_holdover(self, *, spoken: bool = False) -> None:
        if spoken:
            self._intro_line_spoken = True
        self._holdover_stage = None
        self._holdover_stage_epoch = 0

    def _transition(
        self, stage: EditorialStage, observed_monotonic_ms: int = 0, *, force: bool = False
    ) -> None:
        if stage == self._stage and not force:
            return
        self._stage = stage
        self._stage_epoch += 1
        self._stage_started_monotonic_ms = max(0, observed_monotonic_ms)

    def _next_stage(self) -> EditorialStage | None:
        if self._stage == EditorialStage.STREAM_LOBBY_INTRO:
            return EditorialStage.SESSION_EVENT_INTRO
        if self._stage == EditorialStage.BETWEEN_SESSIONS:
            return (
                EditorialStage.SESSION_EVENT_INTRO
                if self._overlay_mode in {"PRACTICE", "QUALIFYING"}
                else None
            )
        if self._stage == EditorialStage.SESSION_EVENT_INTRO:
            return (
                EditorialStage.GRID_PREP
                if self._overlay_mode == "RACE" or self._handoff_overlay_mode == "RACE"
                else EditorialStage.IN_CAR_PREP
            )
        if self._stage == EditorialStage.IN_CAR_PREP:
            return (
                EditorialStage.OUT_LAP
                if self._overlay_mode in {"PRACTICE", "QUALIFYING"}
                else EditorialStage.GRID_PREP
            )
        return {
            EditorialStage.OUT_LAP: EditorialStage.LIVE_SESSION,
            EditorialStage.GRID_PREP: EditorialStage.FORMATION_OR_LIGHTS,
            EditorialStage.FORMATION_OR_LIGHTS: EditorialStage.LIVE_SESSION,
            EditorialStage.LIVE_SESSION: EditorialStage.SESSION_CONCLUSION,
            EditorialStage.SESSION_CONCLUSION: EditorialStage.BETWEEN_SESSIONS,
        }.get(self._stage)
