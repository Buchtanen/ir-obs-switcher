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
from irswitch.events.episode_registry import EpisodeIntent, EpisodeRegistry
from irswitch.events.freshness_commit import (
    SCHEMA_VERSION,
    CommitToken,
    CommitWorld,
    FreshnessGate,
)
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.story_director import (
    DirectorCandidate,
    DirectorWorld,
    StoryDirector,
)

RuntimeState = Literal["disabled", "starting", "ready", "degraded", "stopping", "stopped"]
LaneState = Literal["idle", "building", "committed", "speaking", "stopping"]
Disposition = Literal["handled", "ignored_stale_or_inapplicable", "rejected_busy"]

MAX_PLANS_PER_CYCLE = 2

EffectWorker = Callable[
    [dict[str, Any]], Awaitable[NarrativeCommand | Sequence[NarrativeCommand] | None]
]
CommitWorldProvider = Callable[[], CommitWorld]


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
        realization_deadline_delay_s: float = 3600.0,
        speech_deadline_delay_s: float = 3600.0,
        freshness_gate: FreshnessGate | None = None,
        commit_world_provider: CommitWorldProvider | None = None,
        opportunity_queue: OpportunityQueue | None = None,
        episode_registry: EpisodeRegistry | None = None,
        story_director: StoryDirector | None = None,
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
        self._realization_deadline_task: asyncio.Task[None] | None = None
        self._speech_deadline_task: asyncio.Task[None] | None = None
        self._silence_deadline_delay_s = float(silence_deadline_delay_s)
        self._validity_deadline_delay_s = float(validity_deadline_delay_s)
        self._realization_deadline_delay_s = float(realization_deadline_delay_s)
        self._speech_deadline_delay_s = float(speech_deadline_delay_s)
        self._speech_deadline_stage: Literal["start", "playback", "stop"] | None = None
        self._freshness_gate = freshness_gate
        self._commit_world_provider = commit_world_provider
        self._commit_token: CommitToken | None = None
        self._opportunity_queue = opportunity_queue
        self._opportunity_id: str | None = None
        self._reservation_token: str | None = None
        self._active_beat_id: str | None = None
        self._opportunity_now_ms: int = 0
        self._episode_registry = episode_registry
        self._seeded_episode_intent: EpisodeIntent | None = None
        self._episode_id: str | None = None
        self._episode_beat_id: str | None = None
        self._episode_now_ms: int = 0
        self._story_director = story_director
        self._director_world: DirectorWorld | None = None
        self._director_candidates: tuple[DirectorCandidate, ...] = ()
        self._director_selected_beat_id: str | None = None
        self._director_selected_episode_revision: int | None = None
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

    def seed_commit_token_for_test(self, token: CommitToken) -> None:
        self._commit_token = token

    def seed_opportunity_for_test(
        self, *, opportunity_id: str, beat_id: str, now_ms: int = 10_000
    ) -> None:
        self._opportunity_id = opportunity_id
        self._active_beat_id = beat_id
        self._opportunity_now_ms = int(now_ms)

    def seed_episode_for_test(
        self, *, intent: EpisodeIntent, beat_id: str, now_ms: int = 10_000
    ) -> None:
        self._seeded_episode_intent = intent
        self._episode_beat_id = beat_id
        self._episode_now_ms = int(now_ms)

    def reservation_token_for_test(self) -> str | None:
        return self._reservation_token

    def episode_id_for_test(self) -> str | None:
        return self._episode_id

    def seed_director_for_test(
        self,
        *,
        world: DirectorWorld,
        candidates: tuple[DirectorCandidate, ...],
    ) -> None:
        self._director_world = world
        self._director_candidates = candidates

    def director_selected_beat_for_test(self) -> str | None:
        return self._director_selected_beat_id

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

    def realization_deadline_task_active(self) -> bool:
        return (
            self._realization_deadline_task is not None
            and not self._realization_deadline_task.done()
        )

    def speech_deadline_task_active(self) -> bool:
        return self._speech_deadline_task is not None and not self._speech_deadline_task.done()

    async def wait_effects_idle(self) -> None:
        # Realization/TTS workers only. Deadline timers are long-lived arms.
        tasks = [task for task in (self._realization_task, self._tts_task) if task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_deadline_timers_idle(self) -> None:
        tasks = [
            task
            for task in (
                self._silence_deadline_task,
                self._validity_deadline_task,
                self._realization_deadline_task,
                self._speech_deadline_task,
            )
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
            elif effect == "effect:cancel_realization_deadline":
                await self._cancel_task("_realization_deadline_task")
            elif effect == "effect:cancel_speech_deadline":
                await self._cancel_task("_speech_deadline_task")
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
            elif effect == "effect:arm_realization_deadline":
                await self._cancel_task("_realization_deadline_task")
                token = self.current_realization_token()
                if token is None:
                    continue
                self._realization_deadline_task = asyncio.create_task(
                    self._run_realization_deadline_timer(dict(token)),
                    name=f"narrative-realization-deadline-{token['requestId']}",
                )
            elif effect == "effect:arm_speech_deadline":
                await self._cancel_task("_speech_deadline_task")
                token = self.current_utterance_token()
                stage = self._speech_deadline_stage
                if token is None or stage is None:
                    continue
                self._speech_deadline_task = asyncio.create_task(
                    self._run_speech_deadline_timer(dict(token), stage),
                    name=f"narrative-speech-deadline-{stage}-{token['utteranceId']}",
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

    async def _run_realization_deadline_timer(self, token: dict[str, Any]) -> None:
        try:
            await asyncio.sleep(self._realization_deadline_delay_s)
            now_ms = int(time.monotonic() * 1000)
            self.admit(
                NarrativeCommand.realization_deadline(
                    f"deadline:REALIZATION_DEADLINE_ELAPSED:{token['requestId']}:{now_ms}",
                    now_ms,
                    request_id=str(token["requestId"]),
                    request_ordinal=int(token["requestOrdinal"]),
                    dispatch_generation=int(token["dispatchGeneration"]),
                    deadline_mono_ms=now_ms,
                )
            )
        except asyncio.CancelledError:
            raise
        finally:
            if self._realization_deadline_task is asyncio.current_task():
                self._realization_deadline_task = None

    async def _run_speech_deadline_timer(
        self,
        token: dict[str, Any],
        stage: Literal["start", "playback", "stop"],
    ) -> None:
        try:
            await asyncio.sleep(self._speech_deadline_delay_s)
            now_ms = int(time.monotonic() * 1000)
            self.admit(
                NarrativeCommand.speech_deadline(
                    f"deadline:SPEECH_DEADLINE_ELAPSED:{stage}:{token['utteranceId']}:{now_ms}",
                    now_ms,
                    utterance_id=str(token["utteranceId"]),
                    utterance_ordinal=int(token["utteranceOrdinal"]),
                    backend_generation=int(token["backendGeneration"]),
                    dispatch_generation=int(token["dispatchGeneration"]),
                    stage=stage,
                    deadline_mono_ms=now_ms,
                )
            )
        except asyncio.CancelledError:
            raise
        finally:
            if self._speech_deadline_task is asyncio.current_task():
                self._speech_deadline_task = None

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
                if not isinstance(command, NarrativeCommand):
                    continue
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

    def _clear_opportunity_binding(self) -> None:
        self._opportunity_id = None
        self._reservation_token = None
        self._active_beat_id = None

    def _clear_episode_binding(self) -> None:
        self._episode_id = None
        self._episode_beat_id = None

    def _open_and_activate_episode(self, effects: list[str]) -> None:
        if self._episode_registry is None or self._seeded_episode_intent is None:
            return
        intent = self._seeded_episode_intent
        opened = self._episode_registry.open(intent)
        if opened.episode is None:
            effects.append("episode_open_rejected")
            return
        for transition in opened.transitions:
            effects.append(f"episode_step:{transition.reason}")
            if transition.reason == "opened":
                effects.append("episode_opened")
        episode_id = opened.episode.episode_id
        source_refs = intent.source_refs or ("runtime:dispatch",)
        activated = self._episode_registry.activate(
            episode_id,
            now_ms=self._episode_now_ms,
            source_refs=source_refs,
        )
        for transition in activated.transitions:
            effects.append(f"episode_step:{transition.reason}")
            if transition.reason == "activated":
                effects.append("episode_activated")
        self._episode_id = episode_id

    def _invalidate_episode(self, effects: list[str]) -> None:
        if self._episode_registry is None or self._episode_id is None:
            self._clear_episode_binding()
            return
        step = self._episode_registry.invalidate(
            self._episode_id,
            now_ms=self._episode_now_ms,
            reason="evidence_invalidated",
        )
        for transition in step.transitions:
            effects.append(f"episode_step:{transition.reason}")
        effects.append("episode_invalidated")
        self._clear_episode_binding()

    def _mark_episode_spoken(self, effects: list[str]) -> None:
        if self._episode_registry is None or self._episode_id is None:
            return
        beat_id = self._episode_beat_id or "beat:unknown"
        step = self._episode_registry.mark_spoken(
            self._episode_id,
            beat_id,
            now_ms=self._episode_now_ms,
            source_refs=("runtime:playback",),
        )
        for transition in step.transitions:
            effects.append(f"episode_step:{transition.reason}")
        effects.append("episode_spoken")

    def _resolve_episode(self, effects: list[str]) -> None:
        if self._episode_registry is None or self._episode_id is None:
            self._clear_episode_binding()
            return
        step = self._episode_registry.resolve(
            self._episode_id,
            now_ms=self._episode_now_ms,
            reason="natural_exit",
        )
        for transition in step.transitions:
            effects.append(f"episode_step:{transition.reason}")
        effects.append("episode_resolved")
        self._clear_episode_binding()

    def _consult_director(self, effects: list[str]) -> bool:
        """Return True when plan dispatch may proceed."""
        if self._story_director is None or self._director_world is None:
            return True
        decision = self._story_director.evaluate(self._director_world, self._director_candidates)
        effects.append("director_evaluated")
        effects.append(f"director_step:{decision.reason}")
        if decision.selected is not None and decision.speech == "speak":
            effects.append("director_selected")
            self._director_selected_beat_id = decision.selected.beat_id
            self._director_selected_episode_revision = decision.selected.episode_revision
            return True
        effects.append("director_silenced")
        self._director_selected_beat_id = None
        self._director_selected_episode_revision = None
        return False

    def _note_director_failure(self, effects: list[str]) -> None:
        if self._story_director is None or self._director_selected_beat_id is None:
            return
        revision = int(self._director_selected_episode_revision or 0)
        self._story_director.note_failure(self._director_selected_beat_id, revision)
        effects.append("director_failure_noted")
        self._director_selected_beat_id = None
        self._director_selected_episode_revision = None

    def _reserve_opportunity(self, effects: list[str]) -> None:
        if self._opportunity_queue is None or self._opportunity_id is None:
            return
        step = self._opportunity_queue.reserve(
            self._opportunity_id, now_ms=self._opportunity_now_ms
        )
        effects.append(f"opportunity_step:{step.reason}")
        if step.reason == "reserved" and step.opportunity is not None:
            self._reservation_token = step.opportunity.reservation_token
            effects.append("opportunity_reserved")
        else:
            self._reservation_token = None
            effects.append("opportunity_not_reservable")

    def _release_opportunity_attempt(self, effects: list[str]) -> None:
        if self._opportunity_queue is None or self._reservation_token is None:
            self._clear_opportunity_binding()
            return
        beat_id = self._active_beat_id or "beat:unknown"
        step = self._opportunity_queue.reject_attempt(
            self._reservation_token,
            beat_id=beat_id,
            now_ms=self._opportunity_now_ms,
        )
        effects.append(f"opportunity_step:{step.reason}")
        if step.reason == "attempt_released":
            effects.append("opportunity_attempt_released")
        self._clear_opportunity_binding()

    def _consume_opportunity(self, effects: list[str]) -> None:
        if self._opportunity_queue is None or self._reservation_token is None:
            self._clear_opportunity_binding()
            return
        step = self._opportunity_queue.consume_speech_started(
            self._reservation_token, now_ms=self._opportunity_now_ms
        )
        effects.append(f"opportunity_step:{step.reason}")
        if step.reason == "consumed":
            effects.append("opportunity_consumed")
        self._clear_opportunity_binding()

    def _cancel_building(self, effects: list[str], *, reason: str) -> None:
        if self._lane != "building":
            return
        self._realization = None
        self._commit_token = None
        self._lane = "idle"
        effects.append(reason)
        effects.append("effect:cancel_realization")
        effects.append("effect:cancel_realization_deadline")
        self._release_opportunity_attempt(effects)
        self._invalidate_episode(effects)
        self._note_director_failure(effects)

    def _request_speech_cancel(self, effects: list[str], *, reason: str) -> None:
        if self._lane not in {"committed", "speaking"}:
            return
        self._lane = "stopping"
        effects.append(reason)
        effects.append("effect:cancel_tts")
        effects.append("effect:cancel_speech_deadline")
        self._speech_deadline_stage = "stop"
        effects.append("effect:arm_speech_deadline")

    def _dispatch_plan(self, effects: list[str]) -> None:
        if self._planning_cycle_id == 0:
            self._planning_cycle_id = 1
        if self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
            effects.append("planning_cycle_exhausted")
            return
        if not self._consult_director(effects):
            return
        self._plans_in_cycle += 1
        self._lane = "building"
        self._realization = {
            "requestId": f"request:{self._reducer_sequence}",
            "requestOrdinal": self._plans_in_cycle,
            "dispatchGeneration": self._planning_cycle_id,
        }
        self._utterance = None
        if self._freshness_gate is not None:
            self._commit_token = self._default_commit_token()
        else:
            self._commit_token = None
        effects.append("plan_dispatched")
        effects.append("effect:dispatch_realization")
        effects.append("effect:arm_realization_deadline")
        self._reserve_opportunity(effects)
        self._open_and_activate_episode(effects)

    def _default_commit_token(self) -> CommitToken:
        return CommitToken(
            schema_version=SCHEMA_VERSION,
            token_id=f"commit:{self._reducer_sequence}",
            plan_id=f"plan:{self._reducer_sequence}",
            beat_id=f"beat:{self._plans_in_cycle}",
            episode_id=f"episode:{max(1, self._planning_cycle_id)}",
            episode_revision=max(1, self._plans_in_cycle),
            stream_epoch=int(self._timeline_revision or 0),
            occurrence_id=None,
            lineage_id=None,
            target_identity=(),
            selected_facts=(),
            opportunity_id=None,
            reservation_token=None,
            opportunity_material_revision=None,
            opportunity_expires_mono_ms=None,
            planned_mono_ms=0,
            fact_view_revision=int(self._fact_view_revision or 0),
        )

    def _default_commit_world(self, token: CommitToken) -> CommitWorld:
        return CommitWorld(
            now_ms=int(token.planned_mono_ms),
            lane="building",
            stream_epoch=token.stream_epoch,
            occurrence_id=token.occurrence_id,
            lineage_id=token.lineage_id,
            episode_id=token.episode_id,
            episode_revision=token.episode_revision,
            episode_state="active",
            target_identity=token.target_identity,
            facts=token.selected_facts,
            fact_view_revision=token.fact_view_revision,
            opportunity_state=None,
            opportunity_material_revision=token.opportunity_material_revision,
            opportunity_expires_mono_ms=token.opportunity_expires_mono_ms,
            reservation_token=token.reservation_token,
            critical_conflict=False,
        )

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
        if self._freshness_gate is not None:
            token = self._commit_token
            if token is None:
                self._realization = None
                self._lane = "idle"
                effects = [
                    "realization_freshness_rejected",
                    "freshness_verdict:not_reached",
                    "effect:cancel_realization_deadline",
                ]
                self._note_director_failure(effects)
                return "handled", effects
            world = (
                self._commit_world_provider()
                if self._commit_world_provider is not None
                else self._default_commit_world(token)
            )
            step = self._freshness_gate.evaluate(token, world)
            if step.verdict != "current":
                self._realization = None
                self._commit_token = None
                self._lane = "idle"
                effects = [
                    "realization_freshness_rejected",
                    f"freshness_verdict:{step.verdict}",
                    "effect:cancel_realization_deadline",
                ]
                effects.extend(f"freshness_evidence:{item}" for item in step.evidence)
                self._release_opportunity_attempt(effects)
                self._invalidate_episode(effects)
                self._note_director_failure(effects)
                return "handled", effects
        self._lane = "committed"
        self._utterance = {
            "utteranceId": f"utterance:{self._reducer_sequence}",
            "utteranceOrdinal": 1,
            "backendGeneration": 1,
            "dispatchGeneration": int(self._realization["dispatchGeneration"]),
        }
        self._realization = None
        self._commit_token = None
        self._speech_deadline_stage = "start"
        effects = [
            "realization_committed",
            "effect:cancel_realization_deadline",
            "effect:dispatch_tts",
            "effect:arm_speech_deadline",
        ]
        if self._freshness_gate is not None:
            effects.insert(1, "freshness_verdict:current")
        return "handled", effects

    def _on_realization_failed(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if self._lane != "building" or not self._matches_realization(command):
            return "ignored_stale_or_inapplicable", ["stale_realization_token"]
        self._realization = None
        self._commit_token = None
        self._lane = "idle"
        effects = ["realization_failed", "effect:cancel_realization_deadline"]
        self._release_opportunity_attempt(effects)
        self._invalidate_episode(effects)
        self._note_director_failure(effects)
        return "handled", effects

    def _on_realization_deadline(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if self._lane != "building" or not self._matches_realization(command):
            return "ignored_stale_or_inapplicable", ["stale_realization_deadline"]
        self._realization = None
        self._commit_token = None
        self._lane = "idle"
        effects = ["realization_deadline", "effect:cancel_realization_deadline"]
        self._release_opportunity_attempt(effects)
        self._invalidate_episode(effects)
        self._note_director_failure(effects)
        return "handled", effects

    def _on_playback_accepted(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if not self._matches_utterance(command):
            return "ignored_stale_or_inapplicable", ["stale_playback_token"]
        if self._lane == "committed":
            self._lane = "speaking"
            self._speech_deadline_stage = "playback"
            effects = [
                "playback_accepted",
                "effect:cancel_speech_deadline",
                "effect:arm_speech_deadline",
            ]
            self._consume_opportunity(effects)
            self._mark_episode_spoken(effects)
            return "handled", effects
        if self._lane == "speaking":
            # Duplicate acceptance while speaking requests stop; never a second utterance.
            self._lane = "stopping"
            self._speech_deadline_stage = "stop"
            return "handled", [
                "playback_accepted_duplicate_stopping",
                "effect:cancel_tts",
                "effect:cancel_speech_deadline",
                "effect:arm_speech_deadline",
            ]
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
            effects.append("effect:cancel_speech_deadline")
            self._speech_deadline_stage = "stop"
            effects.append("effect:arm_speech_deadline")
            return "handled", effects
        # Pre-accept SPEECH_FAILED still holds a reservation — release it.
        if command.kind == "SPEECH_FAILED" and self._reservation_token is not None:
            self._release_opportunity_attempt(effects)
        self._utterance = None
        self._realization = None
        self._lane = "idle"
        self._plans_in_cycle = 0
        effects.append("effect:cancel_speech_deadline")
        self._speech_deadline_stage = None
        if command.kind == "SPEECH_COMPLETED":
            effects.append("director_reentry_eligible")
            self._resolve_episode(effects)
        else:
            self._invalidate_episode(effects)
        return "handled", effects

    def _on_speech_deadline(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        if not self._matches_utterance(command):
            return "ignored_stale_or_inapplicable", ["stale_speech_deadline"]
        if self._lane not in {"committed", "speaking", "stopping"}:
            return "ignored_stale_or_inapplicable", ["lane_inapplicable"]
        if self._lane in {"committed", "speaking"}:
            self._lane = "stopping"
            self._speech_deadline_stage = "stop"
            return "handled", [
                "speech_deadline_stopping",
                "effect:cancel_tts",
                "effect:cancel_speech_deadline",
                "effect:arm_speech_deadline",
            ]
        self._utterance = None
        self._lane = "idle"
        self._speech_deadline_stage = None
        effects = ["speech_deadline_stopped", "effect:cancel_speech_deadline"]
        self._invalidate_episode(effects)
        return "handled", effects

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
        self._speech_deadline_stage = "start"
        return "handled", [
            "manual_committed",
            "effect:dispatch_tts",
            "effect:arm_speech_deadline",
        ]

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
