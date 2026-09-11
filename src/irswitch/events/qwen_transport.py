"""Bounded Qwen transport, warm-up and one-worker admission (v2 #269).

Implementation-time tooling. Not live-wired. Composes #268 CompiledPrompt
and #238 generation-tagged preflight. Does not import commentary or overlay
and does not activate the live narrative actor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from irswitch.contracts.primitives import canonical_json, canonical_sha256

SCHEMA_REQUEST = "realization-request/2"
SCHEMA_RESULT = "realization-result/2"
SCHEMA_ATTEMPT = "llm-attempt/2"
WARMUP_TIMEOUT_MS = 10_000
VISIBLE_LIMIT = 2_048
FRAME_LIMIT = 16_384
STREAM_LIMIT = 65_536
GOLDENS_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "v2.0.0"
    / "machine"
    / "qwen-transport-goldens.json"
)


class TransportError(RuntimeError):
    """Network or admission failure that never starts a fallback chain."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        raise TransportError("redirects_disabled")


def load_transport_goldens() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(GOLDENS_PATH.read_text(encoding="utf-8")))


def warmup_request_body(model: str) -> dict[str, Any]:
    return {
        "max_tokens": 2,
        "messages": [
            {"content": "Return exactly OK.", "role": "system"},
            {"content": "OK", "role": "user"},
        ],
        "model": model,
        "n": 1,
        "reasoning_effort": "none",
        "seed": 0,
        "stream": False,
        "temperature": 0,
        "think": False,
        "top_p": 1,
    }


@dataclass(frozen=True, slots=True)
class RealizationIntent:
    process_instance_id: str
    request_ordinal: int
    dispatch_generation: int
    backend: str
    plan_id: str
    planning_cycle_id: str
    cycle_attempt_ordinal: int
    bundle_id: str
    bundle_hash: str
    compiled_prompt: dict[str, Any] | None
    component_generation: int | None
    config_generation: int
    effective_config_hash: str
    config_apply_sequence: int
    capture_prompt: str
    capture_completion: bool
    dispatched_mono_ms: int
    deadline_mono_ms: int
    beat_id: str
    episode_revision: int
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    seed: int
    pattern_id: str
    render_contract_version: int
    now_ms: int
    authored_text: str | None = None
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class RealizationRequest:
    schema_version: str
    request_id: str
    request_ordinal: int
    dispatch_generation: int
    backend: str
    plan_id: str
    planning_cycle_id: str
    cycle_attempt_ordinal: int
    bundle_id: str
    bundle_hash: str
    compiled_prompt: dict[str, Any] | None
    component_generation: int | None
    config_generation: int
    effective_config_hash: str
    config_apply_sequence: int
    backend_request: dict[str, Any]
    capture_policy: dict[str, Any]
    dispatched_mono_ms: int
    deadline_mono_ms: int
    request_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "backendRequest": self.backend_request,
            "bundleHash": self.bundle_hash,
            "bundleId": self.bundle_id,
            "capturePolicy": self.capture_policy,
            "compiledPrompt": self.compiled_prompt,
            "componentGeneration": self.component_generation,
            "configApplySequence": self.config_apply_sequence,
            "configGeneration": self.config_generation,
            "cycleAttemptOrdinal": self.cycle_attempt_ordinal,
            "deadlineMonoMs": self.deadline_mono_ms,
            "dispatchGeneration": self.dispatch_generation,
            "dispatchedMonoMs": self.dispatched_mono_ms,
            "effectiveConfigHash": self.effective_config_hash,
            "planId": self.plan_id,
            "planningCycleId": self.planning_cycle_id,
            "requestHash": self.request_hash,
            "requestId": self.request_id,
            "requestOrdinal": self.request_ordinal,
            "schemaVersion": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class RealizationResult:
    schema_version: str
    result_id: str
    request_id: str
    request_ordinal: int
    dispatch_generation: int
    backend: str
    outcome: str
    text: str | None
    text_hash: str | None
    failure_reason: str | None
    model_reported: str | None
    transport_started_mono_ms: int
    response_started_mono_ms: int | None
    first_content_mono_ms: int | None
    completed_mono_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    usage_source: str
    finish_reason: str | None
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "completedMonoMs": self.completed_mono_ms,
            "completionTokens": self.completion_tokens,
            "dispatchGeneration": self.dispatch_generation,
            "failureReason": self.failure_reason,
            "finishReason": self.finish_reason,
            "firstContentMonoMs": self.first_content_mono_ms,
            "modelReported": self.model_reported,
            "outcome": self.outcome,
            "promptTokens": self.prompt_tokens,
            "requestId": self.request_id,
            "requestOrdinal": self.request_ordinal,
            "responseStartedMonoMs": self.response_started_mono_ms,
            "resultHash": self.result_hash,
            "resultId": self.result_id,
            "schemaVersion": self.schema_version,
            "text": self.text,
            "textHash": self.text_hash,
            "totalTokens": self.total_tokens,
            "transportStartedMonoMs": self.transport_started_mono_ms,
            "usageSource": self.usage_source,
        }


@dataclass(frozen=True, slots=True)
class TransportStep:
    outcome: str
    reason: str
    request: RealizationRequest | None
    result: RealizationResult | None
    used_live_view: bool
    used_roster: bool
    used_config: bool


@dataclass(frozen=True, slots=True)
class SseParse:
    text: str | None
    finish_reason: str | None
    usage: tuple[int, int, int] | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    content_type: str
    chunks: list[bytes]


@dataclass
class FakeTransport:
    chunks: list[bytes] = field(default_factory=list)
    fail: bool = False
    hold: bool = False
    status: int = 200
    content_type: str = "text/event-stream"

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        stream: bool,
        timeout_ms: int,
    ) -> HttpResponse:
        if self.fail:
            raise TransportError("unreachable")
        if self.hold:
            raise TransportError("held")
        return HttpResponse(self.status, self.content_type, list(self.chunks))


class StdlibTransport:
    def __init__(self) -> None:
        self.used_proxies: dict[str, str] = {}
        self.followed_redirects = False

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        stream: bool,
        timeout_ms: int,
    ) -> HttpResponse:
        request = Request(url, data=body, headers=headers, method="POST")
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=max(0.001, timeout_ms / 1000.0)) as response:
                payload = response.read()
                content_type = str(response.headers.get("Content-Type") or "")
                status = int(getattr(response, "status", 200))
        except HTTPError as exc:
            raise TransportError(f"http_{exc.code}") from exc
        except URLError as exc:
            raise TransportError(str(exc.reason)) from exc
        return HttpResponse(status, content_type, [payload] if payload else [])


class LlmComponent:
    def __init__(self) -> None:
        self.desired_generation = 0
        self.applied_generation = 0
        self.status = "idle"
        self.residency: str | None = None
        self.model: str | None = None
        self.last_attempt: dict[str, object] | None = None

    @property
    def qwen_ready(self) -> bool:
        return self.status == "ready" and self.residency in {"warmup_succeeded", "not_requested"}

    @property
    def authored_ready(self) -> bool:
        return True

    def start_preflight(self, *, desired_generation: int, warmup: bool) -> None:
        self.desired_generation = int(desired_generation)
        self.status = "pending"
        self.residency = None
        del warmup

    def complete_preflight(self, *, generation: int, residency: str) -> str:
        if int(generation) != self.desired_generation:
            return "stale_generation_noop"
        self.applied_generation = int(generation)
        self.residency = residency
        if residency in {"warmup_succeeded", "not_requested"}:
            self.status = "ready"
        else:
            self.status = "failed"
        return residency


class AttemptReducer:
    def __init__(self) -> None:
        self.terminal_attempts = 0
        self._late = "stale_noop"
        self._done = False

    def reduce(self, kind: str) -> str:
        if self._done:
            return self._late
        self._done = True
        self.terminal_attempts += 1
        self._late = "cleanup_only" if kind == "SHUTDOWN" else "stale_noop"
        return "terminal"


def build_qwen_backend_request(intent: RealizationIntent) -> dict[str, Any]:
    prompt = intent.compiled_prompt or {}
    return {
        "max_tokens": int(intent.max_tokens),
        "messages": [
            {"content": str(prompt["systemText"]), "role": "system"},
            {"content": str(prompt["userText"]), "role": "user"},
        ],
        "model": intent.model,
        "n": 1,
        "reasoning_effort": "none",
        "seed": int(intent.seed),
        "stream": True,
        "temperature": float(intent.temperature),
        "think": False,
        "top_p": float(intent.top_p),
        "transport": "openai_chat_completions_sse",
    }


def build_realization_request(intent: RealizationIntent) -> RealizationRequest:
    if intent.backend == "authored":
        backend_request = {
            "patternId": intent.pattern_id,
            "renderContractVersion": int(intent.render_contract_version),
        }
        compiled = None
        component = None
    else:
        backend_request = build_qwen_backend_request(intent)
        compiled = dict(intent.compiled_prompt or {})
        component = intent.component_generation
    request_id = f"rr:{intent.process_instance_id}:{int(intent.request_ordinal)}"
    capture_policy = {
        "completion": bool(intent.capture_completion),
        "prompt": intent.capture_prompt,
    }
    payload = {
        "backend": intent.backend,
        "backendRequest": backend_request,
        "bundleHash": intent.bundle_hash,
        "bundleId": intent.bundle_id,
        "capturePolicy": capture_policy,
        "compiledPrompt": compiled,
        "componentGeneration": component,
        "configApplySequence": int(intent.config_apply_sequence),
        "configGeneration": int(intent.config_generation),
        "cycleAttemptOrdinal": int(intent.cycle_attempt_ordinal),
        "deadlineMonoMs": int(intent.deadline_mono_ms),
        "dispatchGeneration": int(intent.dispatch_generation),
        "dispatchedMonoMs": int(intent.dispatched_mono_ms),
        "effectiveConfigHash": intent.effective_config_hash,
        "planId": intent.plan_id,
        "planningCycleId": intent.planning_cycle_id,
        "requestId": request_id,
        "requestOrdinal": int(intent.request_ordinal),
        "schemaVersion": SCHEMA_REQUEST,
    }
    request_hash = str(canonical_sha256(payload))
    return RealizationRequest(
        schema_version=SCHEMA_REQUEST,
        request_id=request_id,
        request_ordinal=int(intent.request_ordinal),
        dispatch_generation=int(intent.dispatch_generation),
        backend=intent.backend,
        plan_id=intent.plan_id,
        planning_cycle_id=intent.planning_cycle_id,
        cycle_attempt_ordinal=int(intent.cycle_attempt_ordinal),
        bundle_id=intent.bundle_id,
        bundle_hash=intent.bundle_hash,
        compiled_prompt=compiled,
        component_generation=component,
        config_generation=int(intent.config_generation),
        effective_config_hash=intent.effective_config_hash,
        config_apply_sequence=int(intent.config_apply_sequence),
        backend_request=backend_request,
        capture_policy=capture_policy,
        dispatched_mono_ms=int(intent.dispatched_mono_ms),
        deadline_mono_ms=int(intent.deadline_mono_ms),
        request_hash=request_hash,
    )


def latency_metrics(
    *,
    dispatched_mono_ms: int,
    transport_started_mono_ms: int,
    response_started_mono_ms: int | None,
    first_content_mono_ms: int | None,
    completed_mono_ms: int,
    result_reduced_mono_ms: int,
    planned_mono_ms: int,
    timeout_elapsed_ms: int | None = None,
) -> dict[str, int | None]:
    return {
        "admissionMs": transport_started_mono_ms - dispatched_mono_ms,
        "ttfbMs": (
            None
            if response_started_mono_ms is None
            else response_started_mono_ms - transport_started_mono_ms
        ),
        "ttftMs": (
            None
            if first_content_mono_ms is None
            else first_content_mono_ms - transport_started_mono_ms
        ),
        "generationMs": (
            None if first_content_mono_ms is None else completed_mono_ms - first_content_mono_ms
        ),
        "totalMs": completed_mono_ms - transport_started_mono_ms,
        "reducerLagMs": result_reduced_mono_ms - completed_mono_ms,
        "planToResultMs": result_reduced_mono_ms - planned_mono_ms,
        "timeoutElapsedMs": timeout_elapsed_ms,
    }


def build_last_attempt(
    result: RealizationResult,
    *,
    reduced_mono_ms: int | None = None,
) -> dict[str, object]:
    """Project public commentary-runtime/2 components.llm.lastAttempt."""

    reduced = int(result.completed_mono_ms if reduced_mono_ms is None else reduced_mono_ms)
    metrics = latency_metrics(
        dispatched_mono_ms=int(result.transport_started_mono_ms),
        transport_started_mono_ms=int(result.transport_started_mono_ms),
        response_started_mono_ms=result.response_started_mono_ms,
        first_content_mono_ms=result.first_content_mono_ms,
        completed_mono_ms=int(result.completed_mono_ms),
        result_reduced_mono_ms=reduced,
        planned_mono_ms=int(result.transport_started_mono_ms),
    )
    outcome = str(result.outcome)
    if outcome == "failed" and result.failure_reason == "realization_timeout":
        outcome = "timed_out"
    return {
        "requestId": str(result.request_id),
        "outcome": outcome,
        "ttfbMs": metrics["ttfbMs"],
        "ttftMs": metrics["ttftMs"],
        "totalMs": metrics["totalMs"],
        "reducerLagMs": metrics["reducerLagMs"],
        "terminalReason": result.failure_reason,
    }


def record_qwen_last_attempt(
    component: LlmComponent,
    intent: RealizationIntent,
    step: TransportStep,
) -> None:
    """Persist latest admitted Qwen attempt; authored/backend-less steps ignored."""

    if intent.backend == "authored":
        return
    if step.result is None or step.outcome == "admitted":
        return
    component.last_attempt = build_last_attempt(step.result)


def parse_sse(chunks: list[bytes]) -> SseParse:
    stream = 0
    buffer = bytearray()
    pieces: list[str] = []
    finish: str | None = None
    usage: tuple[int, int, int] | None = None
    saw_done = False
    for chunk in chunks:
        stream += len(chunk)
        if stream > STREAM_LIMIT:
            return SseParse(None, None, None, "realization_output_oversize")
        buffer.extend(chunk)
        while b"\n\n" in buffer:
            raw_event, _, buffer = buffer.partition(b"\n\n")
            frame = raw_event + b"\n\n"
            if len(frame) > FRAME_LIMIT:
                return SseParse(None, None, None, "realization_output_oversize")
            parsed = _parse_event(bytes(frame), pieces, finish, usage, saw_done)
            if parsed[0] is not None:
                return SseParse(None, None, None, parsed[0])
            pieces, finish, usage, saw_done = parsed[1], parsed[2], parsed[3], parsed[4]
    if buffer:
        if len(buffer) > FRAME_LIMIT:
            return SseParse(None, None, None, "realization_output_oversize")
        if not saw_done:
            leftover = _parse_event(bytes(buffer) + b"\n\n", pieces, finish, usage, saw_done)
            if leftover[0] is not None:
                return SseParse(None, None, None, leftover[0])
            pieces, finish, usage, saw_done = leftover[1], leftover[2], leftover[3], leftover[4]
    text = "".join(pieces)
    if not saw_done or finish != "stop" or not text:
        return SseParse(None, None, None, "realization_invalid_response")
    if len(text.encode("utf-8")) > VISIBLE_LIMIT:
        return SseParse(None, None, None, "realization_output_oversize")
    return SseParse(text, finish, usage, None)


def _parse_event(
    frame: bytes,
    pieces: list[str],
    finish: str | None,
    usage: tuple[int, int, int] | None,
    saw_done: bool,
) -> tuple[str | None, list[str], str | None, tuple[int, int, int] | None, bool]:
    if saw_done:
        return ("realization_invalid_response", pieces, finish, usage, True)
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError:
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    line = text.strip()
    if not line.startswith("data:"):
        return (None, pieces, finish, usage, saw_done)
    payload = line[5:].strip()
    if payload == "[DONE]":
        return (None, pieces, finish, usage, True)
    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    if not isinstance(body, dict):
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    if len(choices) != 1 or not isinstance(choices[0], dict) or choices[0].get("index", 0) != 0:
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    choice = choices[0]
    if choice.get("tool_calls") or choice.get("function_call"):
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    delta = choice.get("delta") or {}
    if not isinstance(delta, dict):
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    if "tool_calls" in delta or "function_call" in delta:
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    content = delta.get("content")
    if content is None and "content" not in delta:
        content = choice.get("content")
    if content is not None and not isinstance(content, str):
        return ("realization_invalid_response", pieces, finish, usage, saw_done)
    if isinstance(content, str) and content:
        pieces = [*pieces, content]
        visible = "".join(pieces).encode("utf-8")
        if len(visible) > VISIBLE_LIMIT:
            return ("realization_output_oversize", pieces, finish, usage, saw_done)
    reason = choice.get("finish_reason")
    if reason is not None:
        finish = str(reason)
    usage_obj = body.get("usage")
    if isinstance(usage_obj, dict):
        try:
            prompt_tokens = int(usage_obj["prompt_tokens"])
            completion_tokens = int(usage_obj["completion_tokens"])
            total_tokens = int(usage_obj["total_tokens"])
        except (KeyError, TypeError, ValueError):
            usage = None
        else:
            if (
                prompt_tokens >= 0
                and completion_tokens >= 0
                and total_tokens >= 0
                and prompt_tokens + completion_tokens == total_tokens
            ):
                usage = (prompt_tokens, completion_tokens, total_tokens)
            else:
                usage = None
    return (None, pieces, finish, usage, saw_done)


def _empty_step(reason: str, outcome: str, request: RealizationRequest | None) -> TransportStep:
    return TransportStep(
        outcome=outcome,
        reason=reason,
        request=request,
        result=None,
        used_live_view=False,
        used_roster=False,
        used_config=False,
    )


def _result(
    request: RealizationRequest,
    *,
    outcome: str,
    reason: str | None,
    text: str | None,
    now_ms: int,
    response_started: int | None,
    first_content: int | None,
    usage: tuple[int, int, int] | None,
    finish_reason: str | None,
) -> RealizationResult:
    text_hash = None if text is None else str(canonical_sha256(text))
    payload = {
        "backend": request.backend,
        "completedMonoMs": int(now_ms),
        "completionTokens": None if usage is None else usage[1],
        "dispatchGeneration": request.dispatch_generation,
        "failureReason": reason,
        "finishReason": finish_reason if outcome == "succeeded" else None,
        "firstContentMonoMs": first_content,
        "modelReported": None,
        "outcome": outcome,
        "promptTokens": None if usage is None else usage[0],
        "requestId": request.request_id,
        "requestOrdinal": request.request_ordinal,
        "responseStartedMonoMs": response_started,
        "resultId": f"rr-result:{request.request_id}",
        "schemaVersion": SCHEMA_RESULT,
        "text": text,
        "textHash": text_hash,
        "totalTokens": None if usage is None else usage[2],
        "transportStartedMonoMs": request.dispatched_mono_ms,
        "usageSource": "server" if usage is not None else "unavailable",
    }
    result_hash = str(canonical_sha256(payload))
    return RealizationResult(
        schema_version=SCHEMA_RESULT,
        result_id=str(payload["resultId"]),
        request_id=request.request_id,
        request_ordinal=request.request_ordinal,
        dispatch_generation=request.dispatch_generation,
        backend=request.backend,
        outcome=outcome,
        text=text,
        text_hash=text_hash,
        failure_reason=reason,
        model_reported=None,
        transport_started_mono_ms=request.dispatched_mono_ms,
        response_started_mono_ms=response_started,
        first_content_mono_ms=first_content,
        completed_mono_ms=int(now_ms),
        prompt_tokens=None if usage is None else usage[0],
        completion_tokens=None if usage is None else usage[1],
        total_tokens=None if usage is None else usage[2],
        usage_source=str(payload["usageSource"]),
        finish_reason=None if outcome != "succeeded" else finish_reason,
        result_hash=result_hash,
    )


class RealizerService:
    def __init__(self, transport: FakeTransport | StdlibTransport | None = None) -> None:
        self._transport = transport if transport is not None else FakeTransport()
        self._active: RealizationIntent | None = None
        self._active_request: RealizationRequest | None = None
        self._active_component: LlmComponent | None = None
        self._discarded: set[tuple[str, int]] = set()

    @property
    def active_count(self) -> int:
        return 0 if self._active is None else 1

    def try_start(self, intent: RealizationIntent, *, component: LlmComponent) -> TransportStep:
        step = self._try_start_inner(intent, component=component)
        record_qwen_last_attempt(component, intent, step)
        return step

    def _try_start_inner(
        self, intent: RealizationIntent, *, component: LlmComponent
    ) -> TransportStep:
        request = build_realization_request(intent)
        if intent.cancelled:
            result = _result(
                request,
                outcome="cancelled",
                reason="realization_cancelled",
                text=None,
                now_ms=intent.now_ms,
                response_started=None,
                first_content=None,
                usage=None,
                finish_reason=None,
            )
            return TransportStep(
                "cancelled", "realization_cancelled", request, result, False, False, False
            )
        if int(intent.now_ms) >= int(intent.deadline_mono_ms):
            result = _result(
                request,
                outcome="failed",
                reason="realization_timeout",
                text=None,
                now_ms=intent.now_ms,
                response_started=None,
                first_content=None,
                usage=None,
                finish_reason=None,
            )
            self._discarded.add((intent.beat_id, intent.episode_revision))
            return TransportStep(
                "failed", "realization_timeout", request, result, False, False, False
            )
        if (intent.beat_id, intent.episode_revision) in self._discarded:
            return _empty_step("realization_discarded", "failed", request)
        if self._active is not None:
            return _empty_step("realization_transport", "failed", None)
        if intent.backend == "authored":
            result = _result(
                request,
                outcome="succeeded",
                reason=None,
                text=intent.authored_text or "",
                now_ms=intent.now_ms,
                response_started=None,
                first_content=None,
                usage=None,
                finish_reason=None,
            )
            return TransportStep("succeeded", "succeeded", request, result, False, False, False)
        if not component.qwen_ready:
            return _empty_step("realization_transport", "failed", request)
        snapshot = replace(intent)
        self._active = snapshot
        self._active_request = request
        self._active_component = component
        if isinstance(self._transport, FakeTransport) and self._transport.hold:
            return _empty_step("admitted", "admitted", request)
        return self._complete(snapshot, request, intent.now_ms)

    def finish(self, *, now_ms: int) -> TransportStep:
        intent = self._active
        request = self._active_request
        component = self._active_component
        if intent is None or request is None:
            return _empty_step("realization_transport", "failed", None)
        if isinstance(self._transport, FakeTransport):
            self._transport.hold = False
        step = self._complete(intent, request, now_ms)
        if component is not None:
            record_qwen_last_attempt(component, intent, step)
        return step

    def _complete(
        self, intent: RealizationIntent, request: RealizationRequest, now_ms: int
    ) -> TransportStep:
        self._active = None
        self._active_request = None
        self._active_component = None
        try:
            response = self._transport.post(
                "http://127.0.0.1/v1/chat/completions",
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
                body=canonical_json(request.backend_request).encode("utf-8"),
                stream=True,
                timeout_ms=max(1, int(intent.deadline_mono_ms) - int(intent.dispatched_mono_ms)),
            )
        except TransportError:
            self._discarded.add((intent.beat_id, intent.episode_revision))
            result = _result(
                request,
                outcome="failed",
                reason="realization_transport",
                text=None,
                now_ms=now_ms,
                response_started=None,
                first_content=None,
                usage=None,
                finish_reason=None,
            )
            return TransportStep(
                "failed", "realization_transport", request, result, False, False, False
            )
        if response.status != 200 or "text/event-stream" not in response.content_type:
            self._discarded.add((intent.beat_id, intent.episode_revision))
            result = _result(
                request,
                outcome="failed",
                reason="realization_invalid_response",
                text=None,
                now_ms=now_ms,
                response_started=now_ms,
                first_content=None,
                usage=None,
                finish_reason=None,
            )
            return TransportStep(
                "failed", "realization_invalid_response", request, result, False, False, False
            )
        parsed = parse_sse(response.chunks)
        if parsed.reason is not None:
            self._discarded.add((intent.beat_id, intent.episode_revision))
            result = _result(
                request,
                outcome="failed",
                reason=parsed.reason,
                text=None,
                now_ms=now_ms,
                response_started=now_ms,
                first_content=None,
                usage=None,
                finish_reason=None,
            )
            return TransportStep("failed", parsed.reason, request, result, False, False, False)
        first_content = now_ms if parsed.text else None
        result = _result(
            request,
            outcome="succeeded",
            reason=None,
            text=parsed.text,
            now_ms=now_ms,
            response_started=now_ms,
            first_content=first_content,
            usage=parsed.usage,
            finish_reason=parsed.finish_reason,
        )
        return TransportStep("succeeded", "succeeded", request, result, False, False, False)
