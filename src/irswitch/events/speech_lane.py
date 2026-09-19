"""Single in-flight speech lane and playback-acceptance contract (v2 #264).

Not live-wired and not exported from ``events/__init__.py``. Owns lane
idle/building/committed/speaking/stopping and consume-at-accept effects.
Does not import commentary or overlay packages or drive a physical backend.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from irswitch.events.opportunity_queue import OpportunityQueue

SCHEMA_VERSION = "tts-utterance/2"
CALLBACK_SCHEMA = "tts-callback/2"
LANE_STATES = frozenset({"idle", "building", "committed", "speaking", "stopping"})
BUSY_LANES = frozenset({"building", "committed", "speaking", "stopping"})
AUTO_BACKEND_ORDER = ("sapi", "espeak")
EXPLICIT_ONLY = frozenset({"supertonic"})
START_TIMEOUT_MS = 5_000
STOP_TIMEOUT_MS = 1_000
MANUAL_LATCH_TIMEOUT_MS = 1_000
ACCEPTANCE_BOUNDARIES = {
    "sapi": "async_speak_positive_stream",
    "sapi_waveout": "waveout_write_success",
    "espeak": "owned_spawn_probe_ok",
    "supertonic": "sounddevice_play_accepted",
}
ALLOWED_CANCEL = frozenset(
    {
        "stream_end",
        "occurrence_reset",
        "run_reset",
        "commentary_disable",
        "truth_invalidation",
        "shutdown",
    }
)
NARRATIVE_ONLY_CANCEL = frozenset(
    {"stream_end", "occurrence_reset", "run_reset", "commentary_disable", "truth_invalidation"}
)
PENDING_HEALTH = frozenset({"pending", "failed", "unavailable"})


def resolve_backend(requested: str, *, available: Iterable[str]) -> str | None:
    have = tuple(available)
    if requested == "auto":
        for name in AUTO_BACKEND_ORDER:
            if name in have:
                return name
        return None
    if requested in EXPLICIT_ONLY or requested in AUTO_BACKEND_ORDER:
        return requested if requested in have else None
    return None


@dataclass(frozen=True, slots=True)
class SpeechIntent:
    utterance_id: str
    source_kind: str
    opportunity_id: str | None
    reservation_token: str | None
    plan_id: str | None
    beat_id: str | None
    episode_id: str | None
    episode_revision: int
    backend: str
    adapter: str
    backend_generation: int
    config_generation: int
    config_hash: str
    config_apply_sequence: int
    tts_ready: bool
    available_backends: tuple[str, ...]
    now_ms: int
    dispatch_generation: int
    max_seconds: float
    manual_request_id: str | None
    text: str | None
    replace_building: bool = False


@dataclass(frozen=True, slots=True)
class TtsCallback:
    schema_version: str
    callback_id: str
    kind: str
    utterance_id: str
    worker_sequence: int
    backend: str
    backend_generation: int
    dispatch_generation: int
    observed_mono_ms: int
    detail_code: str | None


@dataclass(frozen=True, slots=True)
class TtsUtterance:
    schema_version: str
    utterance_id: str
    source_kind: str
    backend: str
    adapter: str
    backend_generation: int
    dispatch_generation: int
    opportunity_id: str | None
    reservation_token: str | None
    plan_id: str | None
    beat_id: str | None
    episode_id: str | None
    config_generation: int
    config_hash: str
    config_apply_sequence: int
    max_seconds: float


@dataclass(frozen=True, slots=True)
class LaneStep:
    reason: str
    lane: str
    waiter_created: bool
    utterance: TtsUtterance | None
    public_command: str | None
    opportunity_effect: str | None
    accepted: bool
    failover_attempted: bool
    schema_version: str
    latency_ms: dict[str, int] | None = None


class SpeechLane:
    """At most one building/committed/speaking utterance; never a prepared waiter."""

    def __init__(self, queue: OpportunityQueue | None = None) -> None:
        self.queue = queue
        self.lane = "idle"
        self.pending_count = 0
        self.start_count = 0
        self.terminal_count = 0
        self._current: TtsUtterance | None = None
        self._accepted = False
        self._commit_ms: int | None = None
        self._accept_ms: int | None = None
        self._cancel_ms: int | None = None
        self._worker_sequence = 0
        self._quarantined = 0
        self._health_status = "ready"
        self._health_generation = 0
        self._latches: dict[str, str] = {}

    def try_start(self, intent: SpeechIntent) -> LaneStep:
        if intent.source_kind == "manual":
            return self._try_manual(intent)
        if not self._admission_ok(intent):
            return self._step("tts_unavailable", utterance=None)
        if self.lane != "idle" and not (
            intent.replace_building and self.lane == "building" and not self._accepted
        ):
            return self._step("lane_busy")
        backend = resolve_backend(intent.backend, available=intent.available_backends)
        if backend is None:
            return self._step("tts_unavailable", utterance=None)
        utterance = _utterance(intent, backend)
        self._reset_token(utterance)
        self.lane = "building"
        return self._step("started_building", utterance=utterance)

    def commit(self, utterance_id: str, *, now_ms: int) -> LaneStep:
        if self.lane != "building" or self._current is None:
            return self._step("stale_callback")
        if self._current.utterance_id != utterance_id:
            return self._step("stale_callback")
        self.lane = "committed"
        self._commit_ms = now_ms
        return self._step("committed")

    def note_progress(self, utterance_id: str, _kind: str, *, now_ms: int) -> LaneStep:
        del now_ms
        if self._current is None or self._current.utterance_id != utterance_id:
            return self._step("stale_callback")
        return self._step("progress_ignored", opportunity_effect=None)

    def acknowledge(
        self,
        utterance_id: str,
        *,
        adapter: str,
        boundary: str,
        now_ms: int,
    ) -> LaneStep:
        if self._current is None or self._current.utterance_id != utterance_id:
            return self._step("stale_callback")
        if self.lane == "speaking" and self._accepted:
            self.lane = "stopping"
            return self._step("protocol_violation")
        if self.lane != "committed":
            return self._step("stale_callback")
        expected = ACCEPTANCE_BOUNDARIES.get(adapter)
        if expected is None or boundary != expected:
            return self._step("boundary_not_reached", accepted=False)
        self.lane = "speaking"
        self._accepted = True
        self._accept_ms = now_ms
        self.start_count += 1
        self._worker_sequence = 1
        effect = self._consume()
        latency = None
        if self._commit_ms is not None:
            latency = {"commit_to_accept": now_ms - self._commit_ms}
        return self._step(
            "playback_accepted",
            public_command="SPEECH_STARTED",
            opportunity_effect=effect,
            accepted=True,
            latency_ms=latency,
        )

    def callback(self, callback: TtsCallback) -> LaneStep:
        if self._current is None or callback.utterance_id != self._current.utterance_id:
            return self._step("stale_callback")
        if self.lane == "idle":
            return self._step("stale_callback")
        if callback.kind == "failed" and not self._accepted:
            effect = self._release()
            return self._terminal("speech_failed", "SPEECH_FAILED", effect)
        if not self._accepted:
            self.lane = "stopping"
            return self._step("protocol_violation")
        if callback.kind == "completed":
            return self._terminal("speech_completed", "SPEECH_COMPLETED", "consumed")
        if callback.kind == "interrupted":
            return self._terminal("speech_interrupted", "SPEECH_INTERRUPTED", "consumed")
        if callback.kind == "failed":
            return self._terminal("speech_failed", "SPEECH_FAILED", "consumed")
        return self._step("stale_callback")

    def note_race_event(self, *, now_ms: int) -> LaneStep:
        del now_ms
        if self.lane in {"committed", "speaking"}:
            return self._step("race_ignored")
        return self._step("race_ignored")

    def cancel(self, reason: str, *, now_ms: int) -> LaneStep:
        if reason not in ALLOWED_CANCEL:
            return self._step("cancel_rejected")
        current = self._current
        if current is not None and current.source_kind == "manual":
            if reason in NARRATIVE_ONLY_CANCEL:
                return self._step("cancel_rejected")
        if self.lane not in BUSY_LANES:
            return self._step("cancel_rejected")
        self.lane = "stopping"
        self._cancel_ms = now_ms
        effect = None if self._accepted else "unconsumed"
        return self._step("cancel_requested", opportunity_effect=effect)

    def watchdog(self, stage: str, *, now_ms: int) -> LaneStep:
        if stage == "start":
            if self.lane != "committed" or self._commit_ms is None:
                return self._step("stale_callback")
            if now_ms < self._commit_ms + START_TIMEOUT_MS:
                return self._step("watchdog_armed")
            self.lane = "stopping"
            self._cancel_ms = now_ms
            return self._step("watchdog_start", opportunity_effect="unconsumed")
        if stage == "playback":
            if self.lane != "speaking" or self._accept_ms is None or self._current is None:
                return self._step("stale_callback")
            limit = int(self._current.max_seconds * 1000)
            if now_ms < self._accept_ms + limit:
                return self._step("watchdog_armed")
            self.lane = "stopping"
            self._cancel_ms = now_ms
            return self._step("watchdog_playback")
        if stage == "stop":
            if self.lane != "stopping" or self._cancel_ms is None:
                return self._step("stale_callback")
            if now_ms < self._cancel_ms + STOP_TIMEOUT_MS:
                return self._step("watchdog_armed")
            if self._current is not None:
                self._quarantined = max(self._quarantined, self._current.backend_generation)
            self._clear()
            return self._step("quarantined", utterance=None)
        return self._step("stale_callback")

    def note_health(self, *, backend_generation: int, status: str, now_ms: int) -> LaneStep:
        del now_ms
        self._health_generation = backend_generation
        self._health_status = status
        if status == "ready" and backend_generation > self._quarantined:
            return self._step("health_ready")
        return self._step("health_noted")

    def abandon_manual(self, request_id: str) -> LaneStep:
        current = self._latches.get(request_id)
        if current == "actor_claimed":
            return self._step("manual_claimed")
        self._latches[request_id] = "caller_abandoned"
        return self._step("latch_abandoned", utterance=None)

    def _try_manual(self, intent: SpeechIntent) -> LaneStep:
        request_id = intent.manual_request_id or intent.utterance_id
        if self._latches.get(request_id) == "caller_abandoned":
            return self._step("latch_abandoned", utterance=None)
        if not self._admission_ok(intent) or self.lane != "idle":
            reason = "lane_busy" if self.lane != "idle" else "tts_unavailable"
            return self._step(reason, utterance=None)
        backend = resolve_backend(intent.backend, available=intent.available_backends)
        if backend is None:
            return self._step("tts_unavailable", utterance=None)
        self._latches[request_id] = "actor_claimed"
        utterance = _utterance(intent, backend)
        self._reset_token(utterance)
        self.lane = "committed"
        self._commit_ms = intent.now_ms
        return self._step("manual_committed", utterance=utterance)

    def _admission_ok(self, intent: SpeechIntent) -> bool:
        if not intent.tts_ready:
            return False
        if intent.backend_generation <= self._quarantined:
            return False
        if self._health_status in PENDING_HEALTH:
            return False
        return True

    def _consume(self) -> str:
        token = None if self._current is None else self._current.reservation_token
        if self.queue is not None and token is not None:
            self.queue.consume_speech_started(token, now_ms=self._accept_ms or 0)
        return "consumed" if token is not None else None  # type: ignore[return-value]

    def _release(self) -> str:
        token = None if self._current is None else self._current.reservation_token
        beat = (
            "unknown"
            if self._current is None or self._current.beat_id is None
            else self._current.beat_id
        )
        if self.queue is not None and token is not None:
            self.queue.reject_attempt(token, beat_id=beat, now_ms=self._commit_ms or 0)
        return "released"

    def _terminal(self, reason: str, command: str, effect: str | None) -> LaneStep:
        self.terminal_count += 1
        self._clear()
        return self._step(reason, public_command=command, opportunity_effect=effect, utterance=None)

    def _reset_token(self, utterance: TtsUtterance) -> None:
        self._current = utterance
        self._accepted = False
        self._commit_ms = None
        self._accept_ms = None
        self._cancel_ms = None
        self._worker_sequence = 0

    def _clear(self) -> None:
        self.lane = "idle"
        self._current = None
        self._accepted = False
        self._commit_ms = None
        self._accept_ms = None
        self._cancel_ms = None

    def _step(
        self,
        reason: str,
        *,
        utterance: TtsUtterance | None | object = ...,
        public_command: str | None = None,
        opportunity_effect: str | None = None,
        accepted: bool | None = None,
        latency_ms: dict[str, int] | None = None,
    ) -> LaneStep:
        current = self._current if utterance is ... else utterance
        return LaneStep(
            reason=reason,
            lane=self.lane,
            waiter_created=False,
            utterance=current if isinstance(current, TtsUtterance) else None,
            public_command=public_command,
            opportunity_effect=opportunity_effect,
            accepted=self._accepted if accepted is None else accepted,
            failover_attempted=False,
            schema_version=SCHEMA_VERSION,
            latency_ms=latency_ms,
        )


def _utterance(intent: SpeechIntent, backend: str) -> TtsUtterance:
    return TtsUtterance(
        schema_version=SCHEMA_VERSION,
        utterance_id=intent.utterance_id,
        source_kind=intent.source_kind,
        backend=backend,
        adapter=intent.adapter,
        backend_generation=intent.backend_generation,
        dispatch_generation=intent.dispatch_generation,
        opportunity_id=intent.opportunity_id,
        reservation_token=intent.reservation_token,
        plan_id=intent.plan_id,
        beat_id=intent.beat_id,
        episode_id=intent.episode_id,
        config_generation=intent.config_generation,
        config_hash=intent.config_hash,
        config_apply_sequence=intent.config_apply_sequence,
        max_seconds=intent.max_seconds,
    )
