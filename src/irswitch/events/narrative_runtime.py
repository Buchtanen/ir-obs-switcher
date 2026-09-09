"""Single-owner NarrativeRuntime actor (#284) — library reducer.

Not exported from ``events/__init__.py``. Not live-wired into commentary
consumer, overlay, or server loops. Owns mailbox dequeue order,
``reducer_sequence``, speech-lane bookkeeping and planning-cycle caps.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterator, Sequence
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


EffectWorker = Callable[
    [dict[str, Any]], Awaitable[NarrativeCommand | Sequence[NarrativeCommand] | None]
]


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
    last_admission_reason: str | None
    mailbox_depth: int
    mailbox_capacity: int
    admission_diagnostics: tuple[str, ...]
    mailbox_overflows: int
    reason_codes: tuple[str, ...]
    recovery_count: int
    last_recovery_loss_first: int | None
    last_recovery_loss_last: int | None
    last_recovery_safety_effect_count: int
    last_recovery_cancelled_lane: LaneState | None


class NarrativeRuntime:
    """Reduce admitted commands in mailbox order and assign reducer_sequence."""

    def __init__(
        self,
        mailbox: NarrativeMailbox | None = None,
        *,
        realization_effect: EffectWorker | None = None,
        tts_effect: EffectWorker | None = None,
        silence_deadline_delay_s: float = 3600.0,
        validity_deadline_delay_s: float = 3600.0,
    ) -> None:
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
        self._realization_effect = realization_effect
        self._tts_effect = tts_effect
        self._realization_task: asyncio.Task[None] | None = None
        self._tts_task: asyncio.Task[None] | None = None
        self._silence_deadline_task: asyncio.Task[None] | None = None
        self._validity_deadline_task: asyncio.Task[None] | None = None
        self._silence_deadline_delay_s = float(silence_deadline_delay_s)
        self._validity_deadline_delay_s = float(validity_deadline_delay_s)
        self._last_admission_reason: str | None = None
        self._admission_diagnostics: list[str] = []
        self._mailbox_overflows = 0
        self._recovery_seen = False
        self._recovery_count = 0
        self._last_recovery_loss_first: int | None = None
        self._last_recovery_loss_last: int | None = None
        self._last_recovery_safety_effect_count = 0
        self._last_recovery_cancelled_lane: LaneState | None = None

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
            last_admission_reason=self._last_admission_reason,
            mailbox_depth=len(self._mailbox),
            mailbox_capacity=NarrativeMailbox.TOTAL_CAPACITY,
            admission_diagnostics=tuple(self._admission_diagnostics),
            mailbox_overflows=self._mailbox_overflows,
            reason_codes=self._reason_codes(),
            recovery_count=self._recovery_count,
            last_recovery_loss_first=self._last_recovery_loss_first,
            last_recovery_loss_last=self._last_recovery_loss_last,
            last_recovery_safety_effect_count=self._last_recovery_safety_effect_count,
            last_recovery_cancelled_lane=self._last_recovery_cancelled_lane,
        )

    def admit(self, command: NarrativeCommand) -> AdmissionResult:
        result = self._mailbox.admit(command)
        self._last_admission_reason = result.reason
        if result.reason not in self._admission_diagnostics:
            self._admission_diagnostics.append(result.reason)
        if result.reason in {"mailbox_evicted_update", "mailbox_recovery", "mailbox_overloaded"}:
            self._mailbox_overflows += 1
        if result.reason == "mailbox_recovery":
            self._recovery_seen = True
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
            await self.apply_effects(result.effects)
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

    def realization_task_active(self) -> bool:
        return self._realization_task is not None and not self._realization_task.done()

    def tts_task_active(self) -> bool:
        return self._tts_task is not None and not self._tts_task.done()

    def silence_deadline_task_active(self) -> bool:
        return self._silence_deadline_task is not None and not self._silence_deadline_task.done()

    def validity_deadline_task_active(self) -> bool:
        return self._validity_deadline_task is not None and not self._validity_deadline_task.done()

    async def wait_effects_idle(self) -> None:
        # Realization/TTS workers only. Deadline timers are long-lived arms.
        tasks = [task for task in (self._realization_task, self._tts_task) if task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_deadline_timers_idle(self) -> None:
        tasks = [
            task
            for task in (self._silence_deadline_task, self._validity_deadline_task)
            if task is not None
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def apply_effects(self, effects: Sequence[str]) -> None:
        for effect in effects:
            if effect == "effect:cancel_realization":
                await self._cancel_task("_realization_task")
            elif effect == "effect:cancel_tts":
                await self._cancel_task("_tts_task")
            elif effect == "effect:cancel_silence_deadline":
                await self._cancel_task("_silence_deadline_task")
            elif effect == "effect:cancel_validity_deadline":
                await self._cancel_task("_validity_deadline_task")
            elif effect == "effect:dispatch_realization":
                await self._cancel_task("_realization_task")
                token = self.current_realization_token()
                if token is None or self._realization_effect is None:
                    continue
                self._realization_task = asyncio.create_task(
                    self._run_worker(self._realization_effect, token, "_realization_task"),
                    name="narrative-realization",
                )
            elif effect == "effect:dispatch_tts":
                await self._cancel_task("_tts_task")
                token = self.current_utterance_token()
                if token is None or self._tts_effect is None:
                    continue
                self._tts_task = asyncio.create_task(
                    self._run_worker(self._tts_effect, token, "_tts_task"),
                    name="narrative-tts",
                )
            elif effect == "effect:arm_silence_deadline":
                await self._cancel_task("_silence_deadline_task")
                generation = self._silence_generation
                self._silence_deadline_task = asyncio.create_task(
                    self._run_deadline_timer(
                        kind="LONG_SILENCE_ELAPSED",
                        generation=generation,
                        delay_s=self._silence_deadline_delay_s,
                        attr="_silence_deadline_task",
                    ),
                    name=f"narrative-silence-{generation}",
                )
            elif effect == "effect:arm_validity_deadline":
                await self._cancel_task("_validity_deadline_task")
                generation = self._validity_generation
                self._validity_deadline_task = asyncio.create_task(
                    self._run_deadline_timer(
                        kind="VALIDITY_DEADLINE_ELAPSED",
                        generation=generation,
                        delay_s=self._validity_deadline_delay_s,
                        attr="_validity_deadline_task",
                    ),
                    name=f"narrative-validity-{generation}",
                )
        # Yield so newly created workers observe dispatch before the caller continues.
        await asyncio.sleep(0)

    async def _run_deadline_timer(
        self,
        *,
        kind: Literal["LONG_SILENCE_ELAPSED", "VALIDITY_DEADLINE_ELAPSED"],
        generation: int,
        delay_s: float,
        attr: str,
    ) -> None:
        try:
            await asyncio.sleep(delay_s)
            now_ms = int(time.monotonic() * 1000)
            self.admit(
                NarrativeCommand.deadline(
                    f"deadline:{kind}:{generation}:{now_ms}",
                    kind,
                    now_ms,
                    generation=generation,
                    deadline_mono_ms=now_ms,
                )
            )
        except asyncio.CancelledError:
            raise
        finally:
            if getattr(self, attr) is asyncio.current_task():
                setattr(self, attr, None)

    async def _cancel_task(self, attr: str) -> None:
        task: asyncio.Task[None] | None = getattr(self, attr)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        if getattr(self, attr) is task:
            setattr(self, attr, None)

    async def _run_worker(
        self,
        worker: EffectWorker,
        token: dict[str, Any],
        attr: str,
    ) -> None:
        try:
            produced = await worker(dict(token))
        except asyncio.CancelledError:
            raise
        except Exception:
            return
        else:
            if produced is None:
                return
            commands = (
                produced
                if isinstance(produced, Sequence)
                and not isinstance(produced, (str, bytes))
                and not hasattr(produced, "kind")
                else (produced,)
            )
            # NarrativeCommand is not a Sequence of commands; treat single command as one-item.
            if hasattr(produced, "kind"):
                commands = (produced,)
            for command in commands:
                self.admit(command)
        finally:
            if getattr(self, attr) is asyncio.current_task():
                setattr(self, attr, None)

    def _reason_codes(self) -> tuple[str, ...]:
        codes: list[str] = []
        if not self._history_complete:
            codes.append("history_incomplete")
            codes.append("mailbox_history_incomplete")
        if self._recovery_seen:
            codes.append("mailbox_recovery")
        if self._tape_status == "unavailable":
            codes.append("capture_unavailable")
        if any(status == "unavailable" for status in self._component_health.values()):
            codes.append("component_unavailable")
        # stable unique
        return tuple(dict.fromkeys(codes))

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
        lane_before_cancel = self._lane
        self._history_complete = False
        self._recovery_seen = True
        self._recovery_count += 1
        payload = command.payload
        self._last_recovery_loss_first = int(payload["lossFirstMailboxSequence"])
        self._last_recovery_loss_last = int(payload["lossLastMailboxSequence"])
        safety_effects = payload.get("safetyEffects") or ()
        self._last_recovery_safety_effect_count = len(safety_effects)
        effects = ["recovery_applied", "history_incomplete"]
        self._bump_deadline_generations(effects)
        if self._lane == "building":
            self._cancel_building(effects, reason="building_cancelled")
            self._last_recovery_cancelled_lane = lane_before_cancel
        elif self._lane in {"committed", "speaking"}:
            self._request_speech_cancel(effects, reason="committed_cancel_requested")
            self._last_recovery_cancelled_lane = lane_before_cancel
        else:
            self._last_recovery_cancelled_lane = None
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
