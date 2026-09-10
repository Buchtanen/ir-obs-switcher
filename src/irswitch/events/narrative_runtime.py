"""Single-owner NarrativeRuntime actor (#284) — library reducer.

Not exported from ``events/__init__.py``. Not live-wired into commentary
consumer, overlay, or server loops. Owns mailbox dequeue order,
``reducer_sequence``, speech-lane bookkeeping and planning-cycle caps.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from irswitch.commentary.mailbox import AdmissionResult, NarrativeMailbox
from irswitch.contracts.catalog_loader import load_narrative_catalog
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.context import ContextBatchPart
from irswitch.events.detector_bank import DetectorBank
from irswitch.events.episode_registry import EpisodeIntent, EpisodeRegistry
from irswitch.events.exposure_store import ExposureIntent, ExposureStore
from irswitch.events.freshness_commit import (
    SCHEMA_VERSION,
    CommitToken,
    CommitWorld,
    FreshnessGate,
)
from irswitch.events.narrative_decision_projection import build_runtime_decision_entry
from irswitch.events.narrative_director_bridge import (
    build_director_snapshot,
    planning_impulse_for_lane,
)
from irswitch.events.narrative_manual_latch import (
    ADMISSION_TIMEOUT_S,
    ManualAdmissionLatch,
)
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.qwen_transport import LlmComponent
from irswitch.events.semantic_verifier import (
    SemanticVerifier,
    VerifyIntent,
)
from irswitch.events.story_director import (
    DECISION_CAPACITY,
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

_OBS_TO_STREAM: dict[str, tuple[str, bool | None]] = {
    "inactive": ("inactive", False),
    "active": ("active", True),
    "unknown": ("unknown", None),
}


def _stream_projection_from_obs(obs_state: object | None) -> tuple[str, bool | None]:
    """Map timeline obsState/streamState into public streamState + streamActive."""

    if obs_state is None:
        return "unknown", None
    key = str(obs_state)
    return _OBS_TO_STREAM.get(key, ("unknown", None))


_STAGE_ORDER = ("practice", "qualifying", "race")


def _stages_through(stage: str) -> list[str]:
    if stage not in _STAGE_ORDER:
        return []
    return list(_STAGE_ORDER[: _STAGE_ORDER.index(stage) + 1])


def _session_identity_from_timeline(
    timeline: Mapping[str, Any],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    str | None,
    str | None,
    str | None,
]:
    """Build StatusResponse session identity from a context timeline.

    All-or-none: incomplete inputs clear the whole set (nulls).
    """

    stage_raw = timeline.get("stage")
    occurrence_id = timeline.get("occurrenceId")
    lineage_id = timeline.get("lineageId")
    session_ref_raw = timeline.get("sessionRef")
    revision_raw = timeline.get("sessionPlanRevision")
    plan_raw = timeline.get("sessionPlan")

    if not isinstance(stage_raw, str) or stage_raw not in _STAGE_ORDER:
        return None, None, None, None, None
    if not isinstance(occurrence_id, str) or not occurrence_id:
        return None, None, None, None, None
    if not isinstance(lineage_id, str) or not lineage_id:
        return None, None, None, None, None
    if not isinstance(session_ref_raw, Mapping):
        return None, None, None, None, None
    sub_session_id = session_ref_raw.get("subSessionId")
    session_num = session_ref_raw.get("sessionNum")
    if not isinstance(sub_session_id, str) or not sub_session_id:
        return None, None, None, None, None
    if isinstance(session_num, bool) or not isinstance(session_num, int) or session_num < 0:
        return None, None, None, None, None

    session_plan: dict[str, object] | None = None
    if isinstance(plan_raw, Mapping):
        revision = plan_raw.get("revision")
        valid = plan_raw.get("valid")
        reason = plan_raw.get("reason")
        stages = plan_raw.get("stages")
        if (
            isinstance(revision, int)
            and not isinstance(revision, bool)
            and revision >= 0
            and isinstance(valid, bool)
            and (reason is None or reason == "session_plan_conflict")
            and isinstance(stages, list)
            and all(isinstance(item, str) and item in _STAGE_ORDER for item in stages)
        ):
            session_plan = {
                "revision": int(revision),
                "valid": bool(valid),
                "reason": reason,
                "stages": list(stages),
            }
    if session_plan is None:
        if isinstance(revision_raw, bool) or not isinstance(revision_raw, int) or revision_raw < 0:
            return None, None, None, None, None
        session_plan = {
            "revision": int(revision_raw),
            "valid": True,
            "reason": None,
            "stages": _stages_through(stage_raw),
        }

    session_ref = {"subSessionId": sub_session_id, "sessionNum": int(session_num)}
    return session_plan, session_ref, occurrence_id, lineage_id, stage_raw


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
class ManualSpeakOutcome:
    """Sync library result for offline / test manual-speak admission (#273)."""

    kind: Literal[
        "accepted",
        "speech_busy",
        "component_unavailable",
        "mailbox_overloaded",
        "validation_failed",
        "admission_timeout",
    ]
    request_id: str | None = None
    admitted_state: str | None = None


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
    fact_active_count: int
    fact_historical_summary_count: int
    detector_disabled: tuple[dict[str, str], ...]
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
    # #273 identity projection (commentary-runtime/2 timeline subset)
    broadcast_epoch: int
    stream_epoch: int
    narrative_run_active: bool
    loop_active: bool
    loop_last_reduce_mono_ms: int | None
    loop_reduce_count: int
    loop_supervisors: dict[str, dict[str, object]]
    stream_active: bool | None
    stream_state: str
    # #273 session identity (all-or-none; null until context supplies a full set)
    session_plan: dict[str, object] | None
    session_ref: dict[str, object] | None
    occurrence_id: str | None
    lineage_id: str | None
    stage: str | None
    # #273 speech / component projection (commentary-runtime/2 subset)
    speech_source_kind: str | None
    speech_utterance_id: str | None
    speech_beat_id: str | None
    speech_opportunity_id: str | None
    speech_backend: str | None
    speech_backend_generation: int | None
    speech_quarantined_generation: int | None
    speech_dispatched_at_mono_ms: int | None
    speech_accepted_at_mono_ms: int | None
    speech_last_terminal: dict[str, object] | None
    # #273 live catalog/config/episodes/byTapeChannel projection inputs
    config_ledger: dict[str, object] | None
    episode_counts: dict[str, int] | None
    by_tape_channel: dict[str, dict[str, int]] | None
    # #273 live llm transport/residency projection inputs (None model => stubs)
    llm_attached: bool
    llm_generation: int
    llm_model: str | None
    llm_residency_evidence: str
    llm_reason: str | None
    llm_last_attempt: dict[str, object] | None


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
        exposure_store: ExposureStore | None = None,
        story_director: StoryDirector | None = None,
        llm_component: LlmComponent | None = None,
        detector_bank: DetectorBank | None = None,
        command_journal_path: Path | str | None = None,
        semantic_verifier: SemanticVerifier | None = None,
        tape_effect: EffectWorker | None = None,
        shutdown_flush_timeout_s: float = 2.0,
    ) -> None:
        # Empty NarrativeMailbox is falsy via __len__; only replace on None so
        # ingress/shadow cutover can share one injected mailbox identity.
        self._mailbox = mailbox if mailbox is not None else NarrativeMailbox()
        self._runtime: RuntimeState = "disabled"
        self._lane: LaneState = "idle"
        self._reducer_sequence = 0
        self._history_complete = True
        self._planning_cycle_id = 0
        self._plans_in_cycle = 0
        self._timeline_revision: int | None = None
        self._fact_view_revision: int | None = None
        self._config_valid: bool | None = None
        self._config_ledger: dict[str, object] | None = None
        self._component_health: dict[str, str] = {"llm": "ready", "tts": "ready"}
        self._tape_status: str | None = None
        # Public-contracts identity defaults before first observed/admitted values.
        self._broadcast_epoch = 0
        self._stream_epoch = 0
        self._narrative_run_active = False
        self._stream_active: bool | None = None
        self._stream_state = "unknown"
        self._session_plan: dict[str, object] | None = None
        self._session_ref: dict[str, object] | None = None
        self._occurrence_id: str | None = None
        self._lineage_id: str | None = None
        self._stage: str | None = None
        self._speech_source_kind: str | None = None
        self._speech_utterance_id: str | None = None
        self._speech_beat_id: str | None = None
        self._speech_opportunity_id: str | None = None
        self._speech_backend: str | None = None
        self._speech_backend_generation: int | None = None
        self._speech_quarantined_generation: int | None = None
        self._speech_dispatched_at_mono_ms: int | None = None
        self._speech_accepted_at_mono_ms: int | None = None
        self._speech_last_terminal: dict[str, object] | None = None
        self._silence_generation = 0
        self._validity_generation = 0
        self._realization: dict[str, Any] | None = None
        self._utterance: dict[str, Any] | None = None
        self._wake = asyncio.Event()
        self._realization_effect = realization_effect
        self._tts_effect = tts_effect
        self._tape_effect = tape_effect
        self._shutdown_flush_timeout_s = float(shutdown_flush_timeout_s)
        self._realization_task: asyncio.Task[None] | None = None
        self._tts_task: asyncio.Task[None] | None = None
        self._tape_task: asyncio.Task[None] | None = None
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
        self._exposure_store = exposure_store
        self._pending_exposure: dict[str, object] | None = None
        self._seeded_episode_intent: EpisodeIntent | None = None
        self._episode_id: str | None = None
        self._episode_beat_id: str | None = None
        self._episode_now_ms: int = 0
        self._story_director = story_director
        self._llm_component = llm_component
        self._detector_bank = detector_bank
        self._command_journal_path = (
            None if command_journal_path is None else Path(command_journal_path)
        )
        self._semantic_verifier = semantic_verifier
        self._fact_active_count = 0
        self._fact_historical_summary_count = 0
        self._director_world: DirectorWorld | None = None
        self._director_candidates: tuple[DirectorCandidate, ...] = ()
        self._director_manual_seed = False
        self._director_selected_beat_id: str | None = None
        self._director_selected_episode_revision: int | None = None
        self._decision_ring: deque[dict[str, Any]] = deque(maxlen=DECISION_CAPACITY)
        self._manual_latches: dict[str, ManualAdmissionLatch] = {}
        self._run_active = False
        self._loop_last_reduce_mono_ms: int | None = None
        self._loop_reduce_count = 0
        self._supervisor_heartbeat_providers: dict[str, Callable[[], Mapping[str, object]]] = {}
        self._last_admission_reason: str | None = None
        self._admission_diagnostics: list[str] = []
        self._mailbox_overflows = 0
        self._recovery_seen = False
        self._recovery_count = 0
        self._last_recovery_loss_first: int | None = None
        self._last_recovery_loss_last: int | None = None
        self._last_recovery_safety_effect_count = 0
        self._last_recovery_cancelled_lane: LaneState | None = None

    def _detector_disabled_snapshot(self) -> tuple[dict[str, str], ...]:
        if self._detector_bank is None:
            return ()
        return self._detector_bank.disabled_for_status()

    def _ingest_fact_view_counts(self, fact_view: Mapping[str, object] | dict[str, object]) -> None:
        facts = fact_view.get("facts")
        refs = fact_view.get("compactedSummaryRefs")
        self._fact_active_count = len(facts) if isinstance(facts, list) else 0
        self._fact_historical_summary_count = len(refs) if isinstance(refs, list) else 0
        if "historyComplete" in fact_view:
            self._history_complete = bool(fact_view["historyComplete"])

    def attach_supervisor_heartbeat(
        self,
        name: str,
        provider: Callable[[], Mapping[str, object]],
    ) -> None:
        """Register a race/supervisor snapshot provider for loop.supervisors."""

        key = str(name).strip()
        if not key:
            raise ValueError("supervisor heartbeat name must be non-empty")
        self._supervisor_heartbeat_providers[key] = provider

    def _supervisor_heartbeat_snapshot(self) -> dict[str, dict[str, object]]:
        snapshot: dict[str, dict[str, object]] = {}
        for name, provider in self._supervisor_heartbeat_providers.items():
            try:
                payload = provider()
            except Exception:
                continue
            if isinstance(payload, Mapping):
                snapshot[name] = dict(payload)
        return snapshot

    def enable(self) -> None:
        if self._runtime in {"stopped", "stopping"}:
            raise RuntimeError("NarrativeRuntime cannot restart after shutdown")
        self._runtime = "ready"

    def status(self) -> RuntimeStatus:
        health = dict(self._component_health)
        llm_attached = self._llm_component is not None
        llm_generation = 0
        llm_model: str | None = None
        llm_residency_evidence = "not_requested"
        llm_reason: str | None = None
        if llm_attached:
            component = self._llm_component
            assert component is not None
            llm_generation = int(component.applied_generation)
            llm_model = component.model
            residency = component.residency
            if residency in {"warmup_succeeded", "not_requested"}:
                llm_residency_evidence = residency
            else:
                llm_residency_evidence = "not_requested"
            mapped = {
                "idle": "ready",
                "pending": "starting",
                "ready": "ready",
                "failed": "unavailable",
            }.get(str(component.status), "degraded")
            health["llm"] = mapped
            if mapped == "unavailable":
                llm_reason = "component_unavailable"
        llm_last_attempt = None
        if llm_attached:
            component = self._llm_component
            assert component is not None
            if component.last_attempt is not None:
                llm_last_attempt = dict(component.last_attempt)
        return RuntimeStatus(
            runtime_state=self._runtime,
            lane=self._lane,
            reducer_sequence=self._reducer_sequence,
            history_complete=self._history_complete,
            planning_cycle_id=self._planning_cycle_id,
            plans_dispatched_in_cycle=self._plans_in_cycle,
            timeline_revision=self._timeline_revision,
            fact_view_revision=self._fact_view_revision,
            fact_active_count=int(self._fact_active_count),
            fact_historical_summary_count=int(self._fact_historical_summary_count),
            detector_disabled=self._detector_disabled_snapshot(),
            config_valid=self._config_valid,
            component_health=health,
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
            broadcast_epoch=int(self._broadcast_epoch),
            stream_epoch=int(self._stream_epoch),
            narrative_run_active=bool(self._narrative_run_active),
            loop_active=bool(self._run_active),
            loop_last_reduce_mono_ms=self._loop_last_reduce_mono_ms,
            loop_reduce_count=int(self._loop_reduce_count),
            loop_supervisors=self._supervisor_heartbeat_snapshot(),
            stream_active=self._stream_active,
            stream_state=str(self._stream_state),
            session_plan=(None if self._session_plan is None else dict(self._session_plan)),
            session_ref=(None if self._session_ref is None else dict(self._session_ref)),
            occurrence_id=self._occurrence_id,
            lineage_id=self._lineage_id,
            stage=self._stage,
            speech_source_kind=self._speech_source_kind,
            speech_utterance_id=self._speech_utterance_id,
            speech_beat_id=self._speech_beat_id,
            speech_opportunity_id=self._speech_opportunity_id,
            speech_backend=self._speech_backend,
            speech_backend_generation=self._speech_backend_generation,
            speech_quarantined_generation=self._speech_quarantined_generation,
            speech_dispatched_at_mono_ms=self._speech_dispatched_at_mono_ms,
            speech_accepted_at_mono_ms=self._speech_accepted_at_mono_ms,
            speech_last_terminal=(
                None if self._speech_last_terminal is None else dict(self._speech_last_terminal)
            ),
            config_ledger=(None if self._config_ledger is None else dict(self._config_ledger)),
            episode_counts=self._episode_counts_snapshot(),
            by_tape_channel=self._by_tape_channel_snapshot(),
            llm_attached=llm_attached,
            llm_generation=llm_generation,
            llm_model=llm_model,
            llm_residency_evidence=llm_residency_evidence,
            llm_reason=llm_reason,
            llm_last_attempt=llm_last_attempt,
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
        result = self._reduce(command)
        self._loop_reduce_count += 1
        self._loop_last_reduce_mono_ms = int(time.monotonic() * 1000)
        self._append_command_journal(command, result)
        return result

    def _append_command_journal(self, command: NarrativeCommand, result: ReduceResult) -> None:
        """Best-effort live journal row; never fails the reduce path."""

        path = self._command_journal_path
        if path is None:
            return
        try:
            from irswitch.events.narrative_reducer_replay import append_command_journal_row

            append_command_journal_row(
                path,
                reducer_sequence=int(result.reducer_sequence),
                command=command,
            )
        except Exception:
            # Journal is diagnostics-only; reduce must stay fail-soft.
            return

    def drain(self) -> Iterator[ReduceResult]:
        while True:
            result = self.reduce_next()
            if result is None:
                return
            yield result

    async def run(self) -> None:
        if self._runtime == "disabled":
            self.enable()
        self._run_active = True
        try:
            await self._run_loop()
        finally:
            self._run_active = False

    async def _run_loop(self) -> None:
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

    def exposure_store_for_test(self) -> ExposureStore | None:
        return self._exposure_store

    def seed_director_for_test(
        self,
        *,
        world: DirectorWorld,
        candidates: tuple[DirectorCandidate, ...],
    ) -> None:
        self._director_world = world
        self._director_candidates = candidates
        self._director_manual_seed = True

    def director_selected_beat_for_test(self) -> str | None:
        return self._director_selected_beat_id

    def decisions(self, limit: int = 20) -> tuple[Mapping[str, Any], ...]:
        """Newest-first decision rows for commentary-runtime/2 projection."""
        if isinstance(limit, bool) or not isinstance(limit, int):
            limit = 20
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        newest_first = list(reversed(self._decision_ring))
        return tuple(newest_first[:limit])

    def register_manual_latch(self, request_id: str, latch: ManualAdmissionLatch) -> None:
        """Attach a one-shot admission latch for ``request_id`` (HTTP/adapter)."""

        self._manual_latches[str(request_id)] = latch

    def _pop_manual_latch(self, request_id: str) -> ManualAdmissionLatch | None:
        return self._manual_latches.pop(str(request_id), None)

    async def try_manual_speak(
        self,
        text: str,
        *,
        request_id: str,
        now_ms: int,
        admission_ordinal: int = 1,
        timeout_s: float = ADMISSION_TIMEOUT_S,
        reduce_inline: bool | None = None,
    ) -> ManualSpeakOutcome:
        """Admit manual speak via one-shot ``ManualAdmissionLatch`` (1s default).

        Allocates the latch, nonblocking-admits ``MANUAL_SPEAK_REQUEST``, then
        awaits latch resolution. When the actor loop is not running, reduces
        inline so library/HTTP tests stay deterministic. On await timeout the
        caller abandons the latch and returns ``admission_timeout``; a later
        reduce cannot speak.
        """

        if self._runtime == "disabled":
            self.enable()
        latch = ManualAdmissionLatch()
        self.register_manual_latch(request_id, latch)
        try:
            command = NarrativeCommand.manual_speak(
                request_id,
                int(now_ms),
                text=text,
                admission_ordinal=int(admission_ordinal),
            )
        except Exception as exc:  # ContractViolation + TypeError
            from irswitch.contracts.primitives import ContractViolation

            self._pop_manual_latch(request_id)
            if not isinstance(exc, (ContractViolation, TypeError, ValueError)):
                raise
            return ManualSpeakOutcome(kind="validation_failed")

        admission = self.admit(command)
        if not admission.accepted:
            latch.abandon_caller()
            self._pop_manual_latch(request_id)
            return ManualSpeakOutcome(kind="mailbox_overloaded")

        inline = (not self._run_active) if reduce_inline is None else bool(reduce_inline)
        if inline:
            result = self.reduce_next()
            if result is not None:
                await self.apply_effects(result.effects)
            elif latch.outcome is None:
                latch.abandon_caller()
                self._pop_manual_latch(request_id)
                return ManualSpeakOutcome(kind="component_unavailable")

        outcome = await latch.wait(timeout_s)
        if outcome is not None:
            self._pop_manual_latch(request_id)
            return outcome

        if latch.abandon_caller():
            # Keep abandoned latch registered so a later reduce cannot speak.
            return ManualSpeakOutcome(kind="admission_timeout")
        # Actor claimed first — wait briefly for resolve without abandoning.
        outcome = await latch.wait(0.05)
        self._pop_manual_latch(request_id)
        if outcome is not None:
            return outcome
        return ManualSpeakOutcome(kind="component_unavailable")

    def fail_current_realization_for_test(self) -> None:
        self._realization = None
        if self._lane == "building":
            self._lane = "idle"

    def realization_task_active(self) -> bool:
        return self._realization_task is not None and not self._realization_task.done()

    def tts_task_active(self) -> bool:
        return self._tts_task is not None and not self._tts_task.done()

    def tape_task_active(self) -> bool:
        return self._tape_task is not None and not self._tape_task.done()

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
        tasks = [
            task
            for task in (self._realization_task, self._tts_task, self._tape_task)
            if task is not None
        ]
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
            elif effect == "effect:cancel_tape":
                await self._cancel_task("_tape_task")
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
            elif effect == "effect:flush_tape":
                await self._cancel_task("_tape_task")
                if self._tape_effect is None:
                    continue
                token = {
                    "reason": "shutdown",
                    "timeoutS": self._shutdown_flush_timeout_s,
                }
                self._tape_task = asyncio.create_task(
                    self._run_tape_flush(token),
                    name="narrative-tape-flush",
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

    async def _run_tape_flush(self, token: dict[str, Any]) -> None:
        """Owned cancellable tape flush; timeout is fail-soft (never raises)."""

        effect = self._tape_effect
        if effect is None:
            return
        timeout_s = float(token.get("timeoutS") or self._shutdown_flush_timeout_s)
        try:
            produced = await asyncio.wait_for(effect(dict(token)), timeout=max(0.0, timeout_s))
        except TimeoutError:
            # Fail-soft: bounded shutdown must not raise into the actor loop.
            # SHUTDOWN already closed ingress, so admit may be rejected — fall
            # back to a local tape_status projection.
            command = NarrativeCommand.tape_health(
                f"tape:flush-timeout:{self._reducer_sequence}",
                int(time.monotonic() * 1000),
                recorder_generation=0,
                status="degraded",
                affected_detector_ids=(),
                first_lost_sequence=None,
                last_lost_sequence=None,
            )
            admitted = self.admit(command)
            if not getattr(admitted, "accepted", False):
                self._tape_status = "degraded"
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            return
        else:
            if produced is None:
                return
            if hasattr(produced, "kind"):
                commands: Sequence[Any] = (produced,)
            elif isinstance(produced, Sequence) and not isinstance(produced, (str, bytes)):
                commands = produced
            else:
                return
            for command in commands:
                if isinstance(command, NarrativeCommand):
                    self.admit(command)
        finally:
            if self._tape_task is asyncio.current_task():
                self._tape_task = None

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

    def _clear_active_speech_projection(self) -> None:
        self._speech_source_kind = None
        self._speech_utterance_id = None
        self._speech_beat_id = None
        self._speech_opportunity_id = None
        self._speech_backend = None
        self._speech_backend_generation = None
        self._speech_dispatched_at_mono_ms = None
        self._speech_accepted_at_mono_ms = None
        self._pending_exposure = None

    def _begin_speech_projection(
        self,
        *,
        source_kind: str,
        utterance_id: str,
        beat_id: str | None,
        opportunity_id: str | None,
        backend_generation: int | None,
        dispatched_at_mono_ms: int | None,
    ) -> None:
        self._speech_source_kind = source_kind
        self._speech_utterance_id = utterance_id
        self._speech_beat_id = beat_id
        self._speech_opportunity_id = opportunity_id
        self._speech_backend = None
        self._speech_backend_generation = backend_generation
        self._speech_dispatched_at_mono_ms = dispatched_at_mono_ms
        self._speech_accepted_at_mono_ms = None

    def _retain_speech_terminal(self, *, reason: str, at_mono_ms: int | None) -> None:
        utterance_id = self._speech_utterance_id
        source_kind = self._speech_source_kind
        if utterance_id is None or source_kind is None:
            self._clear_active_speech_projection()
            return
        self._speech_last_terminal = {
            "utteranceId": utterance_id,
            "sourceKind": source_kind,
            "reason": reason,
            "atMonoMs": at_mono_ms,
        }
        self._clear_active_speech_projection()

    def _apply_context_projection(self, part: ContextBatchPart) -> list[str]:
        """Project immutable timeline/fact pointers; return transition effects."""

        transition_effects: list[str] = []
        timeline = part.batch.timeline
        self._timeline_revision = int(timeline["timelineRevision"])
        fact_view = part.batch.fact_view
        self._fact_view_revision = int(fact_view["viewRevision"])
        self._ingest_fact_view_counts(fact_view)
        self._broadcast_epoch = int(timeline.get("broadcastEpoch", self._broadcast_epoch))
        prev_epoch = int(self._stream_epoch)
        prev_run_active = bool(self._narrative_run_active)
        next_epoch = int(timeline.get("streamEpoch", self._stream_epoch))
        self._stream_epoch = next_epoch
        if "narrativeRunActive" in timeline:
            next_run_active = bool(timeline["narrativeRunActive"])
            if prev_run_active and not next_run_active:
                transition_effects.append("narrative_run_closed")
                self._plans_in_cycle = 0
            elif (not prev_run_active) and next_run_active:
                transition_effects.append("narrative_run_opened")
                if next_epoch != prev_epoch:
                    transition_effects.append(f"stream_epoch_allocated:{next_epoch}")
                self._plans_in_cycle = 0
            self._narrative_run_active = next_run_active
        obs_state = timeline.get("obsState")
        if obs_state is None and "streamState" in timeline:
            obs_state = timeline.get("streamState")
        stream_state, stream_active = _stream_projection_from_obs(obs_state)
        if obs_state is not None or "streamActive" in timeline:
            self._stream_state = stream_state
            if "streamActive" in timeline:
                raw_active = timeline["streamActive"]
                self._stream_active = None if raw_active is None else bool(raw_active)
            else:
                self._stream_active = stream_active
        (
            self._session_plan,
            self._session_ref,
            self._occurrence_id,
            self._lineage_id,
            self._stage,
        ) = _session_identity_from_timeline(timeline)
        return transition_effects

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

    def _arm_pending_exposure(self, *, text: str, beat_id: str | None) -> None:
        """Snapshot exposure fields at commit; record only on PLAYBACK_ACCEPTED."""

        self._pending_exposure = None
        if self._exposure_store is None:
            return
        if self._speech_source_kind != "narrative":
            return
        utterance_id = self._speech_utterance_id
        if not utterance_id:
            return
        resolved_beat = beat_id or self._episode_beat_id or self._active_beat_id
        if not resolved_beat:
            return
        try:
            catalog = load_narrative_catalog().require_catalog()
            beat = catalog.beat(str(resolved_beat))
        except Exception:
            return
        semantic_identity: tuple[str, ...] = ("narrative",)
        if self._episode_registry is not None and self._episode_id is not None:
            episode = self._episode_registry.get(self._episode_id)
            if episode is not None and episode.semantic_identity:
                semantic_identity = tuple(episode.semantic_identity)
        self._pending_exposure = {
            "utterance_id": str(utterance_id),
            "semantic_identity": semantic_identity,
            "family": str(beat.realization.family),
            "pattern": f"{resolved_beat}:tight:1",
            "text": str(text),
            "tape_channel": str(beat.tape_channel),
            "policy_id": str(beat.policy.id),
            "episode_id": self._episode_id,
            "beat_role": str(beat.role),
        }

    def _record_exposure(self, effects: list[str], *, now_ms: int) -> None:
        """Sole writer hook: record spoken exposure at playback accept."""

        pending = self._pending_exposure
        self._pending_exposure = None
        if self._exposure_store is None:
            return
        if self._speech_source_kind == "manual":
            effects.append("exposure_skipped_manual")
            return
        if pending is None:
            effects.append("exposure_skipped_no_pending")
            return
        intent = ExposureIntent(
            phase="speaking",
            utterance_id=str(pending["utterance_id"]),
            semantic_identity=tuple(pending["semantic_identity"]),  # type: ignore[arg-type]
            family=str(pending["family"]),
            pattern=str(pending["pattern"]),
            text=str(pending["text"]),
            tape_channel=str(pending["tape_channel"]),
            policy_id=str(pending["policy_id"]),
            episode_id=None if pending["episode_id"] is None else str(pending["episode_id"]),
            beat_role=None if pending["beat_role"] is None else str(pending["beat_role"]),
            now_ms=int(now_ms),
            source_kind="narrative",
        )
        step = self._exposure_store.record(intent)
        effects.append(f"exposure_step:{step.reason}")
        if step.reason == "recorded":
            effects.append("exposure_recorded")

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

    def _refresh_director_from_live(self, part: ContextBatchPart, effects: list[str]) -> None:
        """Seed world/candidates from context so evaluate can run (live path)."""
        if self._story_director is None or self._director_manual_seed:
            return
        impulse = planning_impulse_for_lane(self._lane)
        incumbent_score: float | None = None
        incumbent_urgency: str | None = None
        if self._lane == "building" and self._director_selected_beat_id is not None:
            incumbent_score = 40.0
            incumbent_urgency = "story"
        snapshot = build_director_snapshot(
            events=part.batch.events,
            timeline=part.batch.timeline,
            fact_view=part.batch.fact_view,
            lane=self._lane,
            impulse=impulse,
            reducer_sequence=self._reducer_sequence,
            focused_episode_id=self._episode_id,
            incumbent_score=incumbent_score,
            incumbent_urgency=incumbent_urgency,
        )
        self._director_world = snapshot.world
        self._director_candidates = snapshot.candidates
        effects.append("director_live_seeded")

    def _consult_director(self, effects: list[str]) -> bool:
        """Return True when plan dispatch may proceed."""
        if self._story_director is None or self._director_world is None:
            return True
        decision = self._story_director.evaluate(self._director_world, self._director_candidates)
        effects.append("director_evaluated")
        effects.append(f"director_step:{decision.reason}")
        if int(decision.planning_cycle_id) > 0:
            self._planning_cycle_id = int(decision.planning_cycle_id)
        at_mono_ms = int(self._director_world.now_ms)
        entry = build_runtime_decision_entry(
            decision,
            self._director_candidates,
            reducer_sequence=int(self._reducer_sequence),
            at_mono_ms=at_mono_ms,
        )
        self._decision_ring.append(entry)
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

    def _begin_planning_cycle(self, effects: list[str], *, reason: str) -> None:
        """Open a new planning impulse cycle; resets the per-cycle plan budget."""

        self._planning_cycle_id += 1
        self._plans_in_cycle = 0
        effects.append(f"planning_cycle_opened:{reason}")
        effects.append(f"planning_cycle_id:{self._planning_cycle_id}")

    def _dispatch_plan(self, effects: list[str], *, open_cycle_reason: str | None = None) -> None:
        if open_cycle_reason is not None:
            self._begin_planning_cycle(effects, reason=open_cycle_reason)
        elif self._planning_cycle_id == 0:
            self._begin_planning_cycle(effects, reason="initial")
        if self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
            effects.append("planning_cycle_exhausted")
            return
        if not self._consult_director(effects):
            return
        self._plans_in_cycle += 1
        self._lane = "building"
        beat_id = self._director_selected_beat_id or self._active_beat_id or self._episode_beat_id
        self._realization = {
            "requestId": f"request:{self._reducer_sequence}",
            "requestOrdinal": self._plans_in_cycle,
            "dispatchGeneration": self._planning_cycle_id,
        }
        if beat_id:
            self._realization["beatId"] = beat_id
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
        transition_effects = self._apply_context_projection(part)
        effects = ["context_applied"]
        effects.extend(transition_effects)
        if "narrative_run_closed" in transition_effects:
            self._cancel_building(effects, reason="building_cancelled_on_disable")
            self._request_speech_cancel(effects, reason="speech_cancel_requested_on_disable")
            if self._tape_effect is not None:
                effects.append("effect:flush_tape")
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
        open_reason: str | None = None
        if self._lane == "building":
            self._cancel_building(effects, reason="replaced_precommit")
            open_reason = "event_replacement"
        elif self._plans_in_cycle == 0:
            open_reason = "event_impulse"
        elif self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
            open_reason = "event_after_exhausted"
        self._refresh_director_from_live(part, effects)
        self._dispatch_plan(effects, open_cycle_reason=open_reason)
        return "handled", effects

    def _on_config(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        self._config_valid = bool(command.payload["valid"])
        ledger = command.payload.get("ledger")
        if self._config_valid and isinstance(ledger, dict):
            self._config_ledger = dict(ledger)
        else:
            self._config_ledger = None
        effects = ["config_cached"]
        # Config caches ledger + rearms deadline generations; speech/building
        # cancellation waits for the following coherent context batch (matrix).
        self._bump_deadline_generations(effects)
        return "handled", effects

    def _episode_counts_snapshot(self) -> dict[str, int] | None:
        if self._episode_registry is None:
            return None
        return self._episode_registry.status_counts()

    def _by_tape_channel_snapshot(self) -> dict[str, dict[str, int]] | None:
        if self._opportunity_queue is None:
            return None
        snapshot = self._opportunity_queue.tape_channel_status_counts()
        return snapshot or None

    def _on_silence(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        generation = int((command.token or {})["generation"])
        if generation < self._silence_generation:
            return "ignored_stale_or_inapplicable", ["stale_silence_generation"]
        self._silence_generation = generation
        effects = ["silence_armed"]
        if self._lane == "idle" and self._runtime in {"ready", "degraded"}:
            open_reason: str | None = None
            if self._plans_in_cycle == 0:
                open_reason = "silence_impulse"
            elif self._plans_in_cycle >= MAX_PLANS_PER_CYCLE:
                open_reason = "silence_after_exhausted"
            self._dispatch_plan(effects, open_cycle_reason=open_reason)
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

    def seed_semantic_frame_for_test(
        self,
        *,
        family: str,
        subject_surface: str,
        required_claim_surface: str,
        actor_bindings: tuple[tuple[str, tuple[str, ...]], ...] = (),
        required_actors: frozenset[str] | None = None,
    ) -> None:
        """Test seam: attach #270 verify frame onto the in-flight realization token."""

        if self._realization is None:
            raise RuntimeError("realization token required before seed_semantic_frame_for_test")
        self._realization = {
            **self._realization,
            "verifyFamily": family,
            "verifySubjectSurface": subject_surface,
            "verifyRequiredClaimSurface": required_claim_surface,
            "verifyActorBindings": [[name, list(forms)] for name, forms in actor_bindings],
            "verifyRequiredActors": sorted(
                required_actors
                if required_actors is not None
                else {name for name, _ in actor_bindings}
            ),
        }

    def _verify_intent_from_realization(
        self, command: NarrativeCommand, *, text: str
    ) -> VerifyIntent | None:
        """Build #270 intent from in-flight realization verify frame + result text."""

        token = self._realization
        if not isinstance(token, dict):
            return None
        family = token.get("verifyFamily")
        subject = token.get("verifySubjectSurface")
        claim = token.get("verifyRequiredClaimSurface")
        if not isinstance(family, str) or not family.strip():
            return None
        if not isinstance(subject, str) or not subject.strip():
            return None
        if not isinstance(claim, str) or not claim.strip():
            return None
        raw_bindings = token.get("verifyActorBindings") or ()
        bindings: list[tuple[str, tuple[str, ...]]] = []
        if isinstance(raw_bindings, (list, tuple)):
            for item in raw_bindings:
                if (
                    isinstance(item, (list, tuple))
                    and len(item) == 2
                    and isinstance(item[0], str)
                    and isinstance(item[1], (list, tuple))
                ):
                    forms = tuple(str(form) for form in item[1] if str(form).strip())
                    if forms:
                        bindings.append((item[0], forms))
        raw_required = token.get("verifyRequiredActors") or ()
        required: set[str] = set()
        if isinstance(raw_required, (list, tuple, set, frozenset)):
            required = {str(item) for item in raw_required if str(item).strip()}
        if not required and bindings:
            required = {name for name, _ in bindings}
        return VerifyIntent(
            text=text,
            family=family.strip(),
            subject_surface=subject.strip(),
            required_claim_surface=claim.strip(),
            actor_bindings=tuple(bindings),
            required_actors=frozenset(required),
            now_ms=int(command.enqueued_mono_ms),
            deadline_mono_ms=int(command.enqueued_mono_ms) + 60_000,
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
        text = str(command.payload.get("text") or "").strip()
        semantic_verdict: str | None = None
        if self._semantic_verifier is not None:
            intent = self._verify_intent_from_realization(command, text=text)
            if intent is None:
                # Live template/authored paths may not yet attach a #270 frame.
                # Skip rather than fail-closed so race can inject the verifier
                # without silencing every unframed utterance.
                semantic_verdict = "skipped_no_frame"
            else:
                verify_step = self._semantic_verifier.verify(intent)
                accepted = (
                    verify_step.outcome == "succeeded"
                    and verify_step.result is not None
                    and bool(verify_step.result.accepted)
                )
                if not accepted:
                    self._realization = None
                    self._commit_token = None
                    self._lane = "idle"
                    reasons: tuple[str, ...] = ()
                    if verify_step.result is not None:
                        reasons = tuple(verify_step.result.reasons)
                    elif verify_step.reason:
                        reasons = (str(verify_step.reason),)
                    effects = [
                        "realization_verify_rejected",
                        "semantic_verdict:rejected",
                        "effect:cancel_realization_deadline",
                    ]
                    effects.extend(f"semantic_reason:{reason}" for reason in reasons)
                    self._release_opportunity_attempt(effects)
                    self._invalidate_episode(effects)
                    self._note_director_failure(effects)
                    return "handled", effects
                semantic_verdict = "accepted"
        self._lane = "committed"
        self._utterance = {
            "utteranceId": f"utterance:{self._reducer_sequence}",
            "utteranceOrdinal": 1,
            "backendGeneration": 1,
            "dispatchGeneration": int(self._realization["dispatchGeneration"]),
            "text": text,
        }
        beat_id = self._realization.get("beatId")
        opportunity_id = self._opportunity_id
        self._begin_speech_projection(
            source_kind="narrative",
            utterance_id=str(self._utterance["utteranceId"]),
            beat_id=None if beat_id is None else str(beat_id),
            opportunity_id=None if opportunity_id is None else str(opportunity_id),
            backend_generation=1,
            dispatched_at_mono_ms=int(command.enqueued_mono_ms),
        )
        self._arm_pending_exposure(
            text=text,
            beat_id=None if beat_id is None else str(beat_id),
        )
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
        if semantic_verdict is not None:
            effects.insert(1, f"semantic_verdict:{semantic_verdict}")
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
            self._speech_accepted_at_mono_ms = int(command.enqueued_mono_ms)
            effects = [
                "playback_accepted",
                "effect:cancel_speech_deadline",
                "effect:arm_speech_deadline",
            ]
            self._consume_opportunity(effects)
            self._mark_episode_spoken(effects)
            self._record_exposure(effects, now_ms=int(command.enqueued_mono_ms))
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
        terminal_reason = {
            "SPEECH_COMPLETED": "completed",
            "SPEECH_INTERRUPTED": "interrupted",
            "SPEECH_FAILED": "failed",
        }.get(str(command.kind), "failed")
        self._retain_speech_terminal(
            reason=terminal_reason,
            at_mono_ms=int(command.enqueued_mono_ms),
        )
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
        backend_generation: int | None = None
        if isinstance(self._utterance, dict):
            raw = self._utterance.get("backendGeneration")
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
                backend_generation = int(raw)
        elif (
            isinstance(self._speech_backend_generation, int)
            and not isinstance(self._speech_backend_generation, bool)
            and self._speech_backend_generation > 0
        ):
            backend_generation = int(self._speech_backend_generation)
        self._retain_speech_terminal(
            reason="timed_out",
            at_mono_ms=int(command.enqueued_mono_ms),
        )
        self._utterance = None
        self._lane = "idle"
        self._speech_deadline_stage = None
        effects = ["speech_deadline_stopped", "effect:cancel_speech_deadline"]
        if backend_generation is not None:
            self._speech_quarantined_generation = backend_generation
            self._component_health["tts"] = "unavailable"
            if self._runtime == "ready":
                self._runtime = "degraded"
            effects.append("tts_backend_quarantined")
        self._invalidate_episode(effects)
        return "handled", effects

    def _on_manual(self, command: NarrativeCommand) -> tuple[Disposition, list[str]]:
        request_id = str(command.command_id)
        latch = self._manual_latches.get(request_id)
        if latch is not None and not latch.claim_actor():
            self._pop_manual_latch(request_id)
            return "ignored_stale_or_inapplicable", ["manual_abandoned"]

        def _resolve(outcome: ManualSpeakOutcome) -> None:
            if latch is not None:
                latch.resolve(outcome)

        if self._lane != "idle":
            _resolve(ManualSpeakOutcome(kind="speech_busy"))
            return "rejected_busy", ["manual_rejected_busy"]
        if self._component_health.get("tts") == "unavailable":
            _resolve(ManualSpeakOutcome(kind="component_unavailable"))
            return "ignored_stale_or_inapplicable", ["tts_unavailable"]
        text = str(command.payload.get("text") or "").strip()
        self._lane = "committed"
        self._utterance = {
            "utteranceId": f"utterance:manual:{self._reducer_sequence}",
            "utteranceOrdinal": 1,
            "backendGeneration": 1,
            "dispatchGeneration": max(1, self._planning_cycle_id),
            "text": text,
        }
        self._begin_speech_projection(
            source_kind="manual",
            utterance_id=str(self._utterance["utteranceId"]),
            beat_id=None,
            opportunity_id=None,
            backend_generation=1,
            dispatched_at_mono_ms=int(command.enqueued_mono_ms),
        )
        self._speech_deadline_stage = "start"
        _resolve(
            ManualSpeakOutcome(
                kind="accepted",
                request_id=request_id,
                admitted_state="committed",
            )
        )
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
        generation = int(command.payload["generation"])
        if component == "tts" and self._speech_quarantined_generation is not None:
            if status == "ready" and generation > self._speech_quarantined_generation:
                self._speech_quarantined_generation = None
                self._component_health["tts"] = "ready"
                return "handled", ["tts_quarantine_cleared", "component_health_updated"]
            if status == "ready" and generation <= self._speech_quarantined_generation:
                self._component_health["tts"] = "unavailable"
                return "handled", ["tts_quarantine_held"]
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
            if fact_view:
                self._ingest_fact_view_counts(fact_view)
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
        # Retain allocated streamEpoch; narrative run is no longer active.
        self._narrative_run_active = False
        self._bump_deadline_generations(effects)
        if self._lane == "building":
            self._cancel_building(effects, reason="building_cancelled")
        elif self._lane in {"committed", "speaking"}:
            self._request_speech_cancel(effects, reason="speech_cancel_requested")
        if self._tape_effect is not None:
            effects.append("effect:flush_tape")
        if self.mailbox_empty():
            self._runtime = "stopped"
            # Keep stopping visible only while a cancel token remains; otherwise idle.
            if self._utterance is None:
                self._lane = "idle"
            effects.append("shutdown_complete")
        self._wake.set()
        return "handled", effects
