"""Single-owner NarrativeRuntime actor (#284) — library reducer.

Not exported from ``events/__init__.py``. Not live-wired into commentary
consumer, overlay, or server loops. Owns mailbox dequeue order,
``reducer_sequence``, speech-lane bookkeeping and planning-cycle caps.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from irswitch.commentary.mailbox import AdmissionResult, NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.context import ContextBatchPart

RuntimeState = Literal["disabled", "starting", "ready", "degraded", "stopping", "stopped"]
LaneState = Literal["idle", "building", "committed", "speaking", "stopping"]
Disposition = Literal["handled", "ignored_stale_or_inapplicable", "rejected_busy"]

MAX_PLANS_PER_CYCLE = 2


@dataclass(frozen=True, slots=True)
class ReduceResult:
    reducer_sequence: int
    command_id: str
    kind: str
    disposition: Disposition
    lane_before: LaneState
    lane_after: LaneState
    runtime_state: RuntimeState
    history_complete: bool
    planning_cycle_id: int
    plans_dispatched: int
    effects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    runtime_state: RuntimeState
    lane: LaneState
    reducer_sequence: int
    history_complete: bool
    planning_cycle_id: int
    plans_dispatched_in_cycle: int
    timeline_revision: int | None
    fact_view_revision: int | None
    config_valid: bool | None
    component_health: dict[str, str]
    tape_status: str | None


class NarrativeRuntime:
    """Reduce admitted commands in mailbox order and assign reducer_sequence."""

    def __init__(self, mailbox: NarrativeMailbox | None = None) -> None:
        self._mailbox = mailbox or NarrativeMailbox()
        self._runtime: RuntimeState = "disabled"
        self._lane: LaneState = "idle"
        self._reducer_sequence = 0
        self._history_complete = True
        self._planning_cycle_id = 0
        self._plans_in_cycle = 0
        self._timeline_revision: int | None = None
        self._fact_view_revision: int | None = None
        self._config_valid: bool | None = None
        self._component_health: dict[str, str] = {"llm": "ready", "tts": "ready"}
        self._tape_status: str | None = None
        self._silence_generation = 0
        self._validity_generation = 0
        self._realization: dict[str, Any] | None = None
        self._utterance: dict[str, Any] | None = None
        self._wake = asyncio.Event()

    def enable(self) -> None:
        if self._runtime in {"stopped", "stopping"}:
            raise RuntimeError("NarrativeRuntime cannot restart after shutdown")
        self._runtime = "ready"

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            runtime_state=self._runtime,
            lane=self._lane,
            reducer_sequence=self._reducer_sequence,
            history_complete=self._history_complete,
            planning_cycle_id=self._planning_cycle_id,
            plans_dispatched_in_cycle=self._plans_in_cycle,
            timeline_revision=self._timeline_revision,
            fact_view_revision=self._fact_view_revision,
            config_valid=self._config_valid,
            component_health=dict(self._component_health),
            tape_status=self._tape_status,
        )

    def admit(self, command: NarrativeCommand) -> AdmissionResult:
        result = self._mailbox.admit(command)
        if result.accepted:
            self._wake.set()
        return result

    def reduce_next(self) -> ReduceResult | None:
        if self._runtime == "disabled":
            raise RuntimeError("NarrativeRuntime.enable() required before reduce")
        command = self._mailbox.dequeue()
        if command is None:
            return None
        return self._reduce(command)

    def drain(self) -> Iterator[ReduceResult]:
        while True:
            result = self.reduce_next()
            if result is None:
                return
            yield result

    async def run(self) -> None:
        if self._runtime == "disabled":
            self.enable()
        while self._runtime != "stopped":
            result = self.reduce_next()
            if result is None:
                if self._runtime == "stopping" and self.mailbox_empty():
                    self._runtime = "stopped"
                    break
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=0.05)
                except TimeoutError:
                    continue
                continue
            if result.kind == "SHUTDOWN" and self.mailbox_empty():
                self._runtime = "stopped"
                break

    def mailbox_empty(self) -> bool:
        return len(self._mailbox) == 0

    def current_realization_token(self) -> dict[str, Any] | None:
        return None if self._realization is None else dict(self._realization)

    def current_utterance_token(self) -> dict[str, Any] | None:
        return None if self._utterance is None else dict(self._utterance)

    def fail_current_realization_for_test(self) -> None:
        self._realization = None
        if self._lane == "building":
            self._lane = "idle"

    def _reduce(self, command: NarrativeCommand) -> ReduceResult:
        self._reducer_sequence += 1
        lane_before = self._lane
        handlers = {
            "APPLY_CONTEXT_BATCH": self._on_context,
            "CONFIG_UPDATE": self._on_config,
            "LONG_SILENCE_ELAPSED": self._on_silence,
            "VALIDITY_DEADLINE_ELAPSED": self._on_validity,
            "REALIZATION_SUCCEEDED": self._on_realization_succeeded,
            "REALIZATION_FAILED": self._on_realization_failed,
            "REALIZATION_DEADLINE_ELAPSED": self._on_realization_deadline,
            "PLAYBACK_ACCEPTED": self._on_playback_accepted,
            "SPEECH_COMPLETED": self._on_speech_terminal,
            "SPEECH_INTERRUPTED": self._on_speech_terminal,
            "SPEECH_FAILED": self._on_speech_terminal,
            "SPEECH_DEADLINE_ELAPSED": self._on_speech_deadline,
            "MANUAL_SPEAK_REQUEST": self._on_manual,
            "TAPE_HEALTH_CHANGED": self._on_tape_health,
            "COMPONENT_HEALTH_CHANGED": self._on_component_health,
            "MAILBOX_RECOVERY": self._on_recovery,
            "SHUTDOWN": self._on_shutdown,
        }
        disposition, effects = handlers[command.kind](command)
        return ReduceResult(
            reducer_sequence=self._reducer_sequence,
            command_id=str(command.command_id),
            kind=str(command.kind),
            disposition=disposition,
            lane_before=lane_before,
            lane_after=self._lane,
            runtime_state=self._runtime,
            history_complete=self._history_complete,
            planning_cycle_id=self._planning_cycle_id,
            plans_dispatched=self._plans_in_cycle,
            effects=tuple(effects),
        )

    def _apply_context_projection(self, part: ContextBatchPart) -> None:
        self._timeline_revision = int(part.batch.timeline["timelineRevision"])
        self._fact_view_revision = int(part.batch.fact_view["viewRevision"])

    def _bump_deadline_generations(self, effects: list[str]) -> None:
        self._silence_generation += 1
        self._validity_generation += 1
        effects.append("effect:cancel_silence_deadline")
        effects.append("effect:cancel_validity_deadline")
        effects.append("effect:arm_silence_deadline")
        effects.append("effect:arm_validity_deadline")

    def _cancel_building(self, effects: list[str], *, reason: str) -> None:
        if self._lane != "building":
            return
        self._realization = None
        self._lane = "idle"
        effects.append(reason)
        effects.append("effect:cancel_realization")

    def _request_speech_cancel(self, effects: list[str], *, reason: str) -> None:
        if self._lane not in {"committed", "speaking"}:
            return
        self._lane = "stopping"
        effects.append(reason)
        effects.append("effect:cancel_tts")

    def _dispatch_plan(self, effects: list[str]) -> None:
        if self._planning_cycle_id == 0:
            self._planning_cycle_id = 1
        if self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
            effects.append("planning_cycle_exhausted")
            return
        self._plans_in_cycle += 1
        self._lane = "building"
        self._realization = {
            "requestId": f"request:{self._reducer_sequence}",
            "requestOrdinal": self._plans_in_cycle,
            "dispatchGeneration": self._planning_cycle_id,
        }
        self._utterance = None
        effects.append("plan_dispatched")
        effects.append("effect:dispatch_realization")

    def _on_context(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        part = command.context_part
        assert part is not None
        self._apply_context_projection(part)
        effects = ["context_applied"]
        if part.batch.has_timeline_transition:
            self._bump_deadline_generations(effects)
            self._cancel_building(effects, reason="building_cancelled")
            self._request_speech_cancel(effects, reason="speech_cancel_requested")
        if not part.planning_impulse:
            effects.append("director_skipped_pure_fact")
            if self._lane == "building":
                self._cancel_building(effects, reason="building_invalidated")
            return "handled", effects
        if self._lane in {"committed", "speaking"}:
            effects.append("truth_updated_without_barge_in")
            return "handled", effects
        if self._lane == "stopping":
            effects.append("ignored_while_stopping")
            return "handled", effects
        if self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
            effects.append("planning_cycle_exhausted")
            if self._lane == "building":
                self._cancel_building(effects, reason="building_invalidated")
            return "handled", effects
        self._dispatch_plan(effects)
        return "handled", effects

    def _on_config(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        self._config_valid = bool(command.payload["valid"])
        effects = ["config_cached"]
        # Config caches ledger + rearms deadline generations; speech/building
        # cancellation waits for the following coherent context batch (matrix).
        self._bump_deadline_generations(effects)
        return "handled", effects

    def _on_silence(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        generation = int((command.token or {})["generation"])
        if generation < self._silence_generation:
            return "ignored_stale_or_inapplicable", ["stale_silence_generation"]
        self._silence_generation = generation
        effects = ["silence_armed"]
        if self._lane == "idle" and self._runtime in {"ready", "degraded"}:
            if self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
                effects.append("planning_cycle_exhausted")
            else:
                self._dispatch_plan(effects)
        return "handled", effects

    def _on_validity(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        generation = int((command.token or {})["generation"])
        if generation < self._validity_generation:
            return "ignored_stale_or_inapplicable", ["stale_validity_generation"]
        self._validity_generation = generation
        effects = ["validity_swept"]
        if self._lane == "building":
            self._cancel_building(effects, reason="building_cancelled")
        elif self._lane == "committed":
            self._request_speech_cancel(effects, reason="committed_cancel_requested")
        return "handled", effects

    def _matches_realization(self, command: NarrativeCommand) -> bool:
        if self._realization is None:
            return False
        token = command.token or {}
        return (
            token.get("requestId") == self._realization["requestId"]
            and int(token.get("requestOrdinal", -1)) == int(self._realization["requestOrdinal"])
            and int(token.get("dispatchGeneration", -1))
            == int(self._realization["dispatchGeneration"])
        )

    def _matches_utterance(self, command: NarrativeCommand) -> bool:
        if self._utterance is None:
            return False
        token = command.token or {}
        return (
            token.get("utteranceId") == self._utterance["utteranceId"]
            and int(token.get("utteranceOrdinal", -1)) == int(self._utterance["utteranceOrdinal"])
            and int(token.get("backendGeneration", -1)) == int(self._utterance["backendGeneration"])
            and int(token.get("dispatchGeneration", -1))
            == int(self._utterance["dispatchGeneration"])
        )

    def _on_realization_succeeded(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if self._lane != "building" or not self._matches_realization(command):
            return "ignored_stale_or_inapplicable", ["stale_realization_token"]
        if command.payload.get("outcome") != "succeeded":
            return "ignored_stale_or_inapplicable", ["realization_outcome_mismatch"]
        assert self._realization is not None
        self._lane = "committed"
        self._utterance = {
            "utteranceId": f"utterance:{self._reducer_sequence}",
            "utteranceOrdinal": 1,
            "backendGeneration": 1,
            "dispatchGeneration": int(self._realization["dispatchGeneration"]),
        }
        self._realization = None
        return "handled", ["realization_committed", "effect:dispatch_tts"]

    def _on_realization_failed(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if self._lane != "building" or not self._matches_realization(command):
            return "ignored_stale_or_inapplicable", ["stale_realization_token"]
        self._realization = None
        self._lane = "idle"
        return "handled", ["realization_failed"]

    def _on_realization_deadline(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if self._lane != "building" or not self._matches_realization(command):
            return "ignored_stale_or_inapplicable", ["stale_realization_deadline"]
        self._realization = None
        self._lane = "idle"
        return "handled", ["realization_deadline"]

    def _on_playback_accepted(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if not self._matches_utterance(command):
            return "ignored_stale_or_inapplicable", ["stale_playback_token"]
        if self._lane == "committed":
            self._lane = "speaking"
            return "handled", ["playback_accepted"]
        if self._lane == "speaking":
            # Duplicate acceptance while speaking requests stop; never a second utterance.
            self._lane = "stopping"
            return "handled", ["playback_accepted_duplicate_stopping", "effect:cancel_tts"]
        return "ignored_stale_or_inapplicable", ["stale_playback_token"]

    def _on_speech_terminal(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if not self._matches_utterance(command):
            return "ignored_stale_or_inapplicable", ["stale_speech_token"]
        if self._lane not in {"committed", "speaking", "stopping"}:
            return "ignored_stale_or_inapplicable", ["lane_inapplicable"]
        effects = [f"speech_terminal:{command.kind}"]
        if self._lane == "committed" and command.kind in {"SPEECH_COMPLETED", "SPEECH_INTERRUPTED"}:
            # Pre-accept terminal: enter stopping with token retained for stop watchdog.
            self._lane = "stopping"
            effects.append("speech_cancel_requested")
            effects.append("effect:cancel_tts")
            return "handled", effects
        self._utterance = None
        self._realization = None
        self._lane = "idle"
        self._plans_in_cycle = 0
        if command.kind == "SPEECH_COMPLETED":
            effects.append("director_reentry_eligible")
        return "handled", effects

    def _on_speech_deadline(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if not self._matches_utterance(command):
            return "ignored_stale_or_inapplicable", ["stale_speech_deadline"]
        if self._lane not in {"committed", "speaking", "stopping"}:
            return "ignored_stale_or_inapplicable", ["lane_inapplicable"]
        if self._lane in {"committed", "speaking"}:
            self._lane = "stopping"
            return "handled", ["speech_deadline_stopping", "effect:cancel_tts"]
        self._utterance = None
        self._lane = "idle"
        return "handled", ["speech_deadline_stopped"]

    def _on_manual(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        del command
        if self._lane != "idle":
            return "rejected_busy", ["manual_rejected_busy"]
        if self._component_health.get("tts") == "unavailable":
            return "ignored_stale_or_inapplicable", ["tts_unavailable"]
        self._lane = "committed"
        self._utterance = {
            "utteranceId": f"utterance:manual:{self._reducer_sequence}",
            "utteranceOrdinal": 1,
            "backendGeneration": 1,
            "dispatchGeneration": max(1, self._planning_cycle_id),
        }
        return "handled", ["manual_committed", "effect:dispatch_tts"]

    def _on_tape_health(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        status = str(command.payload["status"])
        self._tape_status = status
        if status == "unavailable" and self._runtime == "ready":
            self._runtime = "degraded"
            return "handled", ["tape_unavailable_degraded"]
        return "handled", ["tape_health_updated"]

    def _on_component_health(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        component = str(command.payload["component"])
        status = str(command.payload["status"])
        self._component_health[component] = status
        if status == "unavailable" and self._runtime == "ready":
            self._runtime = "degraded"
            return "handled", [f"{component}_unavailable_degraded"]
        return "handled", ["component_health_updated"]

    def _on_recovery(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        part = command.context_part
        if part is not None:
            self._apply_context_projection(part)
        else:
            timeline = command.payload.get("latestTimeline") or {}
            fact_view = command.payload.get("latestFactView") or {}
            if "timelineRevision" in timeline:
                self._timeline_revision = int(timeline["timelineRevision"])
            if "viewRevision" in fact_view:
                self._fact_view_revision = int(fact_view["viewRevision"])
        self._history_complete = False
        effects = ["recovery_applied", "history_incomplete"]
        self._bump_deadline_generations(effects)
        if self._lane == "building":
            self._cancel_building(effects, reason="building_cancelled")
        elif self._lane in {"committed", "speaking"}:
            self._request_speech_cancel(effects, reason="committed_cancel_requested")
        return "handled", effects

    def _on_shutdown(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        del command
        effects = ["shutdown_started"]
        self._runtime = "stopping"
        self._bump_deadline_generations(effects)
        if self._lane == "building":
            self._cancel_building(effects, reason="building_cancelled")
        elif self._lane in {"committed", "speaking"}:
            self._request_speech_cancel(effects, reason="speech_cancel_requested")
        if self.mailbox_empty():
            self._runtime = "stopped"
            # Keep stopping visible only while a cancel token remains; otherwise idle.
            if self._utterance is None:
                self._lane = "idle"
            effects.append("shutdown_complete")
        self._wake.set()
        return "handled", effects
