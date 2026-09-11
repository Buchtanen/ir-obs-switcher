"""Immutable NarrativeCommand envelope and mailbox-facing constructors."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, ClassVar, Literal, Self

from .coalesce_policy import coalesce_key_for
from .context import ContextBatchPart, ContextRevision, ExternalOrder
from .primitives import (
    MAX_SIGNED_INT64,
    ContractViolation,
    Identifier,
    MonotonicMs,
    SchemaVersion,
    Sha256Hash,
    canonical_json,
    canonical_sha256,
)

CommandKind = Literal[
    "APPLY_CONTEXT_BATCH",
    "CONFIG_UPDATE",
    "LONG_SILENCE_ELAPSED",
    "VALIDITY_DEADLINE_ELAPSED",
    "REALIZATION_SUCCEEDED",
    "REALIZATION_FAILED",
    "REALIZATION_DEADLINE_ELAPSED",
    "PLAYBACK_ACCEPTED",
    "SPEECH_COMPLETED",
    "SPEECH_INTERRUPTED",
    "SPEECH_FAILED",
    "SPEECH_DEADLINE_ELAPSED",
    "MANUAL_SPEAK_REQUEST",
    "TAPE_HEALTH_CHANGED",
    "COMPONENT_HEALTH_CHANGED",
    "MAILBOX_RECOVERY",
    "SHUTDOWN",
]

COMMAND_KINDS = frozenset(
    {
        "APPLY_CONTEXT_BATCH",
        "CONFIG_UPDATE",
        "LONG_SILENCE_ELAPSED",
        "VALIDITY_DEADLINE_ELAPSED",
        "REALIZATION_SUCCEEDED",
        "REALIZATION_FAILED",
        "REALIZATION_DEADLINE_ELAPSED",
        "PLAYBACK_ACCEPTED",
        "SPEECH_COMPLETED",
        "SPEECH_INTERRUPTED",
        "SPEECH_FAILED",
        "SPEECH_DEADLINE_ELAPSED",
        "MANUAL_SPEAK_REQUEST",
        "TAPE_HEALTH_CHANGED",
        "COMPONENT_HEALTH_CHANGED",
        "MAILBOX_RECOVERY",
        "SHUTDOWN",
    }
)
_ALWAYS_PROTECTED = frozenset(
    {
        "CONFIG_UPDATE",
        "REALIZATION_SUCCEEDED",
        "REALIZATION_FAILED",
        "REALIZATION_DEADLINE_ELAPSED",
        "PLAYBACK_ACCEPTED",
        "SPEECH_COMPLETED",
        "SPEECH_INTERRUPTED",
        "SPEECH_FAILED",
        "SPEECH_DEADLINE_ELAPSED",
        "MAILBOX_RECOVERY",
        "SHUTDOWN",
    }
)


def _nonnegative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be a nonnegative integer")
    if not 0 <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{field} must fit a nonnegative signed 64-bit integer")
    return value


def _positive(value: object, field: str) -> int:
    result = _nonnegative(value, field)
    if result < 1:
        raise ContractViolation(f"{field} must be positive")
    return result


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ContractViolation(f"{label} fields must be exactly {sorted(expected)!r}")


def _frozen_object(value: dict[str, Any], label: str) -> str:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    return canonical_json(value)


def _object_with_exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractViolation(f"{label} must be an object")
    _exact_keys(value, expected, label)
    return value


def _validate_result_payload(payload: dict[str, Any], token: dict[str, Any], kind: str) -> None:
    required = {
        "schemaVersion",
        "resultId",
        "requestId",
        "requestOrdinal",
        "dispatchGeneration",
        "backend",
        "outcome",
        "text",
        "textHash",
        "failureReason",
        "modelReported",
        "transportStartedMonoMs",
        "responseStartedMonoMs",
        "firstContentMonoMs",
        "completedMonoMs",
        "promptTokens",
        "completionTokens",
        "totalTokens",
        "usageSource",
        "finishReason",
        "resultHash",
    }
    _exact_keys(payload, required, "realization result")
    if payload["schemaVersion"] != "realization-result/2":
        raise ContractViolation("realization result schemaVersion is invalid")
    if (
        payload["requestId"] != token["requestId"]
        or payload["requestOrdinal"] != token["requestOrdinal"]
        or payload["dispatchGeneration"] != token["dispatchGeneration"]
    ):
        raise ContractViolation("realization result identity must match command token")
    allowed_outcomes = {"succeeded"} if kind == "REALIZATION_SUCCEEDED" else {"failed", "cancelled"}
    if payload["outcome"] not in allowed_outcomes:
        raise ContractViolation(f"{kind} realization outcome is invalid")
    Identifier(payload["resultId"])
    Identifier(payload["requestId"])
    Sha256Hash(payload["resultHash"])
    if payload["backend"] not in {"authored", "qwen_compiled"}:
        raise ContractViolation("realization backend is invalid")
    outcome = payload["outcome"]
    if outcome == "succeeded":
        if not isinstance(payload["text"], str) or not payload["text"]:
            raise ContractViolation("successful realization requires text")
        Sha256Hash(payload["textHash"])
        if payload["failureReason"] is not None:
            raise ContractViolation("successful realization must not carry failureReason")
    else:
        if payload["text"] is not None or payload["textHash"] is not None:
            raise ContractViolation("unsuccessful realization must not carry text")
        allowed_reasons = {
            "realization_timeout",
            "realization_transport",
            "realization_invalid_response",
            "realization_output_oversize",
        }
        if outcome == "cancelled":
            allowed_reasons = {"realization_cancelled"}
        if payload["failureReason"] not in allowed_reasons:
            raise ContractViolation("realization failureReason is invalid")
    ordered_times: list[int] = []
    for field in (
        "transportStartedMonoMs",
        "responseStartedMonoMs",
        "firstContentMonoMs",
        "completedMonoMs",
    ):
        value = payload[field]
        if value is not None:
            ordered_times.append(_nonnegative(value, field))
    if ordered_times != sorted(ordered_times):
        raise ContractViolation("realization monotonic times must be ordered")
    usage = [payload[field] for field in ("promptTokens", "completionTokens", "totalTokens")]
    if payload["usageSource"] == "server":
        if any(value is None for value in usage):
            raise ContractViolation("server realization usage must be complete")
        prompt, completion, total = (_nonnegative(value, "token usage") for value in usage)
        if prompt + completion != total:
            raise ContractViolation("realization token usage must sum")
    elif payload["usageSource"] == "unavailable":
        if any(value is not None for value in usage):
            raise ContractViolation("unavailable realization usage must be null")
    else:
        raise ContractViolation("realization usageSource is invalid")


def _validate_tts_payload(payload: dict[str, Any], token: dict[str, Any], kind: str) -> None:
    required = {
        "schemaVersion",
        "callbackId",
        "kind",
        "utteranceId",
        "utteranceOrdinal",
        "backend",
        "backendGeneration",
        "dispatchGeneration",
        "workerSequence",
        "observedMonoMs",
        "detailCode",
    }
    _exact_keys(payload, required, "TTS callback")
    if payload["schemaVersion"] != "tts-callback/2":
        raise ContractViolation("TTS callback schemaVersion is invalid")
    callback_kind = {
        "PLAYBACK_ACCEPTED": "playback_accepted",
        "SPEECH_COMPLETED": "completed",
        "SPEECH_INTERRUPTED": "interrupted",
        "SPEECH_FAILED": "failed",
    }[kind]
    if payload["kind"] != callback_kind:
        raise ContractViolation(f"{kind} callback kind is invalid")
    for field in (
        "utteranceId",
        "utteranceOrdinal",
        "backendGeneration",
        "dispatchGeneration",
    ):
        if payload[field] != token[field]:
            raise ContractViolation("TTS callback identity must match command token")
    Identifier(payload["callbackId"])
    Identifier(payload["utteranceId"])
    if payload["backend"] not in {"sapi", "espeak", "supertonic"}:
        raise ContractViolation("TTS callback backend is invalid")
    _positive(payload["workerSequence"], "workerSequence")
    _nonnegative(payload["observedMonoMs"], "observedMonoMs")
    detail_by_kind: dict[str, set[str | None]] = {
        "playback_accepted": {None},
        "completed": {None},
        "interrupted": {"backend_cancelled"},
        "failed": {
            "backend_rejected",
            "backend_process_exit",
            "backend_audio_error",
            "backend_unavailable",
        },
    }
    allowed_detail = detail_by_kind[callback_kind]
    if payload["detailCode"] not in allowed_detail:
        raise ContractViolation("TTS callback detailCode is invalid")


@dataclass(frozen=True, slots=True)
class NarrativeCommand:
    command_id: Identifier
    kind: CommandKind | str
    enqueued_mono_ms: MonotonicMs
    mailbox_sequence: int
    external_order: ExternalOrder | None
    context_revision: ContextRevision | None
    _token_json: str | None
    _payload_json: str
    _context_part: ContextBatchPart | None = None
    _protected_hint: bool = False

    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion("narrative-command/2")

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", Identifier(self.command_id))
        if self.kind not in COMMAND_KINDS:
            raise ContractViolation(f"unknown NarrativeCommand kind: {self.kind!r}")
        object.__setattr__(self, "enqueued_mono_ms", MonotonicMs(self.enqueued_mono_ms))
        object.__setattr__(
            self, "mailbox_sequence", _nonnegative(self.mailbox_sequence, "mailboxSequence")
        )
        if self.kind == "APPLY_CONTEXT_BATCH":
            if (
                self._context_part is None
                or self.external_order is None
                or self.context_revision is None
            ):
                raise ContractViolation("APPLY_CONTEXT_BATCH requires context and external order")
        elif self.kind == "MAILBOX_RECOVERY":
            if self.external_order is None or self.context_revision is None:
                raise ContractViolation("MAILBOX_RECOVERY requires externalOrder/contextRevision")
        elif self.external_order is not None or self.context_revision is not None:
            raise ContractViolation(f"{self.kind} must not carry externalOrder/contextRevision")
        if self.external_order is not None and not isinstance(self.external_order, ExternalOrder):
            raise ContractViolation("externalOrder must be ExternalOrder or null")
        if self.context_revision is not None and not isinstance(
            self.context_revision, ContextRevision
        ):
            raise ContractViolation("contextRevision must be ContextRevision or null")
        if self._token_json is not None:
            token = json.loads(self._token_json)
            if not isinstance(token, dict):
                raise ContractViolation("command token must be an object or null")
        payload = json.loads(self._payload_json)
        if not isinstance(payload, dict):
            raise ContractViolation("command payload must be an object")
        self._validate_discriminator(token if self._token_json is not None else None, payload)
        expected_hint = self.kind in {"TAPE_HEALTH_CHANGED", "COMPONENT_HEALTH_CHANGED"} and (
            payload.get("status") == "unavailable"
        )
        if self._protected_hint != expected_hint:
            raise ContractViolation("protected admission hint must match derived command policy")

    def _validate_discriminator(
        self, token: dict[str, Any] | None, payload: dict[str, Any]
    ) -> None:
        if self.kind == "APPLY_CONTEXT_BATCH":
            context_part = self._context_part
            if context_part is None or token is not None or payload != context_part.batch.to_dict():
                raise ContractViolation("context command content must match its immutable batch")
            return
        if self.kind == "CONFIG_UPDATE":
            if token is not None:
                raise ContractViolation("CONFIG_UPDATE token must be null")
            _object_with_exact_keys(payload, {"valid", "ledger", "diagnostics"}, "config payload")
            if not isinstance(payload["valid"], bool):
                raise ContractViolation("config valid must be boolean")
            if (payload["ledger"] is not None) != payload["valid"]:
                raise ContractViolation("config ledger is required exactly when valid")
            diagnostics = payload["diagnostics"]
            if not isinstance(diagnostics, list) or len(diagnostics) > 32:
                raise ContractViolation("config diagnostics must contain 0..32 items")
            seen_diagnostics: set[str] = set()
            for diagnostic in diagnostics:
                if not isinstance(diagnostic, dict) or not {"code"} <= set(diagnostic) <= {
                    "code",
                    "key",
                    "messageHash",
                }:
                    raise ContractViolation("config diagnostic fields are invalid")
                Identifier(diagnostic["code"])
                if diagnostic.get("key") is not None:
                    Identifier(diagnostic["key"])
                if diagnostic.get("messageHash") is not None:
                    Sha256Hash(diagnostic["messageHash"])
                diagnostic_identity = canonical_json(diagnostic)
                if diagnostic_identity in seen_diagnostics:
                    raise ContractViolation("config diagnostics must be unique")
                seen_diagnostics.add(diagnostic_identity)
            ledger = payload["ledger"]
            if ledger is not None:
                ledger = _object_with_exact_keys(
                    ledger,
                    {
                        "schemaVersion",
                        "desiredGeneration",
                        "desiredHash",
                        "effectiveHash",
                        "applySequence",
                        "desiredValues",
                        "effectiveValues",
                        "pendingChanges",
                        "acceptedMonoMs",
                    },
                    "config ledger",
                )
                if ledger["schemaVersion"] != "commentary-config/2":
                    raise ContractViolation(
                        "config ledger schemaVersion must be commentary-config/2"
                    )
                for field in (
                    "desiredGeneration",
                    "applySequence",
                    "acceptedMonoMs",
                ):
                    _nonnegative(ledger[field], field)
                Sha256Hash(ledger["desiredHash"])
                Sha256Hash(ledger["effectiveHash"])
                if not isinstance(ledger["desiredValues"], dict) or not isinstance(
                    ledger["effectiveValues"], dict
                ):
                    raise ContractViolation("config ledger values must be objects")
                if (
                    not isinstance(ledger["pendingChanges"], list)
                    or len(ledger["pendingChanges"]) > 128
                ):
                    raise ContractViolation("config pendingChanges must contain 0..128 items")
            return
        if self.kind in {"LONG_SILENCE_ELAPSED", "VALIDITY_DEADLINE_ELAPSED"}:
            token = _object_with_exact_keys(
                token, {"generation", "deadlineMonoMs"}, f"{self.kind} token"
            )
            _nonnegative(token["generation"], "generation")
            _nonnegative(token["deadlineMonoMs"], "deadlineMonoMs")
            _exact_keys(payload, set(), f"{self.kind} payload")
            return
        if self.kind in {"REALIZATION_SUCCEEDED", "REALIZATION_FAILED"}:
            token = _object_with_exact_keys(
                token,
                {"requestId", "requestOrdinal", "dispatchGeneration"},
                f"{self.kind} token",
            )
            Identifier(token["requestId"])
            _positive(token["requestOrdinal"], "requestOrdinal")
            _positive(token["dispatchGeneration"], "dispatchGeneration")
            _validate_result_payload(payload, token, self.kind)
            return
        if self.kind == "REALIZATION_DEADLINE_ELAPSED":
            token = _object_with_exact_keys(
                token,
                {"requestId", "requestOrdinal", "dispatchGeneration", "deadlineMonoMs"},
                "realization deadline token",
            )
            Identifier(token["requestId"])
            _positive(token["requestOrdinal"], "requestOrdinal")
            _positive(token["dispatchGeneration"], "dispatchGeneration")
            _nonnegative(token["deadlineMonoMs"], "deadlineMonoMs")
            _exact_keys(payload, set(), "realization deadline payload")
            return
        if self.kind in {
            "PLAYBACK_ACCEPTED",
            "SPEECH_COMPLETED",
            "SPEECH_INTERRUPTED",
            "SPEECH_FAILED",
        }:
            token = _object_with_exact_keys(
                token,
                {
                    "utteranceId",
                    "utteranceOrdinal",
                    "backendGeneration",
                    "dispatchGeneration",
                },
                f"{self.kind} token",
            )
            Identifier(token["utteranceId"])
            for field in ("utteranceOrdinal", "backendGeneration", "dispatchGeneration"):
                _positive(token[field], field)
            _validate_tts_payload(payload, token, self.kind)
            return
        if self.kind == "SPEECH_DEADLINE_ELAPSED":
            token = _object_with_exact_keys(
                token,
                {
                    "utteranceId",
                    "utteranceOrdinal",
                    "backendGeneration",
                    "dispatchGeneration",
                    "stage",
                    "deadlineMonoMs",
                },
                "speech deadline token",
            )
            Identifier(token["utteranceId"])
            for field in ("utteranceOrdinal", "backendGeneration", "dispatchGeneration"):
                _positive(token[field], field)
            if token["stage"] not in {"start", "playback", "stop"}:
                raise ContractViolation("speech deadline stage is invalid")
            _nonnegative(token["deadlineMonoMs"], "deadlineMonoMs")
            _exact_keys(payload, set(), "speech deadline payload")
            return
        if self.kind == "MANUAL_SPEAK_REQUEST":
            token = _object_with_exact_keys(
                token, {"manualRequestId", "admissionOrdinal"}, "manual request token"
            )
            _exact_keys(payload, {"text", "language"}, "manual request payload")
            Identifier(token["manualRequestId"])
            _positive(token["admissionOrdinal"], "admissionOrdinal")
            if token["manualRequestId"] != self.command_id:
                raise ContractViolation("manualRequestId must equal commandId")
            if payload["language"] != "en" or not isinstance(payload["text"], str):
                raise ContractViolation("manual request language/text is invalid")
            normalized = " ".join(payload["text"].split())
            if payload["text"] != normalized or not 1 <= len(normalized) <= 400:
                raise ContractViolation(
                    "manual speech text must be normalized and 1..400 characters"
                )
            return
        if self.kind == "TAPE_HEALTH_CHANGED":
            if token is not None:
                raise ContractViolation("TAPE_HEALTH_CHANGED token must be null")
            _exact_keys(
                payload,
                {
                    "recorderGeneration",
                    "status",
                    "affectedDetectorIds",
                    "firstLostSequence",
                    "lastLostSequence",
                },
                "tape health payload",
            )
            _nonnegative(payload["recorderGeneration"], "recorderGeneration")
            if payload["status"] not in {"ready", "degraded", "unavailable"}:
                raise ContractViolation("invalid tape health status")
            detectors = payload["affectedDetectorIds"]
            if not isinstance(detectors, list) or len(detectors) > 128:
                raise ContractViolation("affected detector ids must contain 0..128 items")
            normalized_detectors = [str(Identifier(item)) for item in detectors]
            if len(set(normalized_detectors)) != len(normalized_detectors):
                raise ContractViolation("affected detector ids must be unique")
            first = payload["firstLostSequence"]
            last = payload["lastLostSequence"]
            if (first is None) != (last is None):
                raise ContractViolation("tape health loss endpoints must both be present or null")
            if first is not None and last is not None:
                if _nonnegative(last, "lastLostSequence") < _nonnegative(
                    first, "firstLostSequence"
                ):
                    raise ContractViolation("tape health loss endpoints must be ordered")
            return
        if self.kind == "COMPONENT_HEALTH_CHANGED":
            if token is not None:
                raise ContractViolation("COMPONENT_HEALTH_CHANGED token must be null")
            _exact_keys(
                payload, {"component", "generation", "status", "reason"}, "component health payload"
            )
            if payload["component"] not in {"llm", "tts"} or payload["status"] not in {
                "ready",
                "degraded",
                "unavailable",
            }:
                raise ContractViolation("invalid component health identity")
            _nonnegative(payload["generation"], "generation")
            if payload["reason"] is not None and not isinstance(payload["reason"], str):
                raise ContractViolation("component health reason must be a string or null")
            return
        if self.kind == "MAILBOX_RECOVERY":
            if token is not None:
                raise ContractViolation("MAILBOX_RECOVERY token must be null")
            _exact_keys(
                payload,
                {
                    "latestTimeline",
                    "latestFactView",
                    "lossFirstMailboxSequence",
                    "lossLastMailboxSequence",
                    "historyComplete",
                    "safetyEffects",
                },
                "mailbox recovery payload",
            )
            if payload["historyComplete"] is not False:
                raise ContractViolation("mailbox recovery historyComplete must be false")
            assert self.context_revision is not None
            if not isinstance(payload["latestTimeline"], dict) or not isinstance(
                payload["latestFactView"], dict
            ):
                raise ContractViolation("mailbox recovery projections must be objects")
            if (
                payload["latestTimeline"].get("timelineRevision")
                != self.context_revision.timeline_revision
                or payload["latestFactView"].get("viewRevision")
                != self.context_revision.fact_view_revision
            ):
                raise ContractViolation("mailbox recovery projections must match contextRevision")
            first = _nonnegative(payload["lossFirstMailboxSequence"], "lossFirstMailboxSequence")
            last = _nonnegative(payload["lossLastMailboxSequence"], "lossLastMailboxSequence")
            if last < first:
                raise ContractViolation("mailbox recovery loss range must be ordered")
            effects = payload["safetyEffects"]
            if not isinstance(effects, list) or not 1 <= len(effects) <= 64:
                raise ContractViolation("mailbox recovery requires 1..64 safety effects")
            seen: set[str] = set()
            for effect in effects:
                effect = _object_with_exact_keys(
                    effect, {"kind", "identity", "payloadHash"}, "recovery safety effect"
                )
                if effect["kind"] not in _ALWAYS_PROTECTED | {
                    "APPLY_CONTEXT_BATCH",
                    "TAPE_HEALTH_CHANGED",
                    "COMPONENT_HEALTH_CHANGED",
                }:
                    raise ContractViolation("recovery safety effect kind must be protected")
                Identifier(effect["identity"])
                Sha256Hash(effect["payloadHash"])
                identity = canonical_json(effect)
                if identity in seen:
                    raise ContractViolation("recovery safety effects must be unique")
                seen.add(identity)
            return
        if self.kind == "SHUTDOWN":
            if token is not None:
                raise ContractViolation("SHUTDOWN token must be null")
            _exact_keys(payload, {"reason", "requestedMonoMs"}, "shutdown payload")
            Identifier(payload["reason"])
            _nonnegative(payload["requestedMonoMs"], "requestedMonoMs")

    @classmethod
    def _new(
        cls,
        *,
        command_id: str,
        kind: CommandKind,
        enqueued_mono_ms: int,
        token: dict[str, Any] | None,
        payload: dict[str, Any],
        external_order: ExternalOrder | None = None,
        context_revision: ContextRevision | None = None,
        context_part: ContextBatchPart | None = None,
        protected_hint: bool = False,
        mailbox_sequence: int = 0,
    ) -> Self:
        return cls(
            Identifier(command_id),
            kind,
            MonotonicMs(enqueued_mono_ms),
            mailbox_sequence,
            external_order,
            context_revision,
            None if token is None else _frozen_object(token, "command token"),
            _frozen_object(payload, "command payload"),
            context_part,
            protected_hint,
        )

    @classmethod
    def context_batch(cls, command_id: str, enqueued_mono_ms: int, part: ContextBatchPart) -> Self:
        if not isinstance(part, ContextBatchPart):
            raise ContractViolation("context command requires ContextBatchPart")
        return cls._new(
            command_id=command_id,
            kind="APPLY_CONTEXT_BATCH",
            enqueued_mono_ms=enqueued_mono_ms,
            token=None,
            payload=part.batch.to_dict(),
            external_order=part.external_order,
            context_revision=part.context_revision,
            context_part=part,
        )

    @classmethod
    def deadline(
        cls,
        command_id: str,
        kind: Literal["LONG_SILENCE_ELAPSED", "VALIDITY_DEADLINE_ELAPSED"],
        enqueued_mono_ms: int,
        *,
        generation: int,
        deadline_mono_ms: int,
    ) -> Self:
        if kind not in {"LONG_SILENCE_ELAPSED", "VALIDITY_DEADLINE_ELAPSED"}:
            raise ContractViolation("deadline constructor requires an ordinary deadline kind")
        return cls._new(
            command_id=command_id,
            kind=kind,
            enqueued_mono_ms=enqueued_mono_ms,
            token={
                "generation": _nonnegative(generation, "generation"),
                "deadlineMonoMs": _nonnegative(deadline_mono_ms, "deadlineMonoMs"),
            },
            payload={},
        )

    @classmethod
    def realization_result(
        cls,
        command_id: str,
        kind: Literal["REALIZATION_SUCCEEDED", "REALIZATION_FAILED"],
        enqueued_mono_ms: int,
        *,
        request_id: str,
        request_ordinal: int,
        dispatch_generation: int,
        result: dict[str, Any],
    ) -> Self:
        if kind not in {"REALIZATION_SUCCEEDED", "REALIZATION_FAILED"}:
            raise ContractViolation(
                "realization result constructor requires a terminal result kind"
            )
        return cls._new(
            command_id=command_id,
            kind=kind,
            enqueued_mono_ms=enqueued_mono_ms,
            token={
                "requestId": str(Identifier(request_id)),
                "requestOrdinal": _positive(request_ordinal, "requestOrdinal"),
                "dispatchGeneration": _positive(dispatch_generation, "dispatchGeneration"),
            },
            payload=result,
        )

    @classmethod
    def realization_deadline(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        request_id: str,
        request_ordinal: int,
        dispatch_generation: int,
        deadline_mono_ms: int,
    ) -> Self:
        return cls._new(
            command_id=command_id,
            kind="REALIZATION_DEADLINE_ELAPSED",
            enqueued_mono_ms=enqueued_mono_ms,
            token={
                "requestId": str(Identifier(request_id)),
                "requestOrdinal": _positive(request_ordinal, "requestOrdinal"),
                "dispatchGeneration": _positive(dispatch_generation, "dispatchGeneration"),
                "deadlineMonoMs": _nonnegative(deadline_mono_ms, "deadlineMonoMs"),
            },
            payload={},
        )

    @classmethod
    def tts_callback(
        cls,
        command_id: str,
        kind: Literal[
            "PLAYBACK_ACCEPTED", "SPEECH_COMPLETED", "SPEECH_INTERRUPTED", "SPEECH_FAILED"
        ],
        enqueued_mono_ms: int,
        *,
        utterance_id: str,
        utterance_ordinal: int,
        backend_generation: int,
        dispatch_generation: int,
        callback: dict[str, Any],
    ) -> Self:
        if kind not in {
            "PLAYBACK_ACCEPTED",
            "SPEECH_COMPLETED",
            "SPEECH_INTERRUPTED",
            "SPEECH_FAILED",
        }:
            raise ContractViolation("TTS callback constructor requires a callback kind")
        return cls._new(
            command_id=command_id,
            kind=kind,
            enqueued_mono_ms=enqueued_mono_ms,
            token={
                "utteranceId": str(Identifier(utterance_id)),
                "utteranceOrdinal": _positive(utterance_ordinal, "utteranceOrdinal"),
                "backendGeneration": _positive(backend_generation, "backendGeneration"),
                "dispatchGeneration": _positive(dispatch_generation, "dispatchGeneration"),
            },
            payload=callback,
        )

    @classmethod
    def speech_deadline(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        utterance_id: str,
        utterance_ordinal: int,
        backend_generation: int,
        dispatch_generation: int,
        stage: Literal["start", "playback", "stop"],
        deadline_mono_ms: int,
    ) -> Self:
        if stage not in {"start", "playback", "stop"}:
            raise ContractViolation("speech deadline stage is invalid")
        return cls._new(
            command_id=command_id,
            kind="SPEECH_DEADLINE_ELAPSED",
            enqueued_mono_ms=enqueued_mono_ms,
            token={
                "utteranceId": str(Identifier(utterance_id)),
                "utteranceOrdinal": _positive(utterance_ordinal, "utteranceOrdinal"),
                "backendGeneration": _positive(backend_generation, "backendGeneration"),
                "dispatchGeneration": _positive(dispatch_generation, "dispatchGeneration"),
                "stage": stage,
                "deadlineMonoMs": _nonnegative(deadline_mono_ms, "deadlineMonoMs"),
            },
            payload={},
        )

    @classmethod
    def manual_speak(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        text: str,
        admission_ordinal: int,
    ) -> Self:
        if not isinstance(text, str):
            raise ContractViolation("manual speech text must be normalized and 1..400 characters")
        normalized = " ".join(text.split())
        if text != normalized or not 1 <= len(text) <= 400 or any(ord(char) < 32 for char in text):
            raise ContractViolation("manual speech text must be normalized and 1..400 characters")
        return cls._new(
            command_id=command_id,
            kind="MANUAL_SPEAK_REQUEST",
            enqueued_mono_ms=enqueued_mono_ms,
            token={
                "manualRequestId": command_id,
                "admissionOrdinal": _positive(admission_ordinal, "admissionOrdinal"),
            },
            payload={"text": normalized, "language": "en"},
        )

    @classmethod
    def config_update(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        valid: bool,
        ledger: dict[str, Any] | None,
        diagnostics: tuple[dict[str, Any], ...],
    ) -> Self:
        if not isinstance(valid, bool):
            raise ContractViolation("config valid must be boolean")
        if (ledger is not None) != valid:
            raise ContractViolation("config ledger is required exactly when valid")
        if not isinstance(diagnostics, tuple) or len(diagnostics) > 32:
            raise ContractViolation("config diagnostics must contain 0..32 items")
        frozen_diagnostics: list[dict[str, Any]] = []
        seen: set[str] = set()
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                raise ContractViolation("config diagnostic must be an object")
            allowed = {"code", "key", "messageHash"}
            if not {"code"} <= set(diagnostic) <= allowed:
                raise ContractViolation("config diagnostic fields are invalid")
            Identifier(diagnostic["code"])
            if diagnostic.get("key") is not None:
                Identifier(diagnostic["key"])
            if diagnostic.get("messageHash") is not None:
                Sha256Hash(diagnostic["messageHash"])
            identity = canonical_json(diagnostic)
            if identity in seen:
                raise ContractViolation("config diagnostics must be unique")
            seen.add(identity)
            frozen_diagnostics.append(diagnostic)
        if ledger is not None:
            _exact_keys(
                ledger,
                {
                    "schemaVersion",
                    "desiredGeneration",
                    "desiredHash",
                    "effectiveHash",
                    "applySequence",
                    "desiredValues",
                    "effectiveValues",
                    "pendingChanges",
                    "acceptedMonoMs",
                },
                "config ledger",
            )
            if ledger["schemaVersion"] != "commentary-config/2":
                raise ContractViolation("config ledger schemaVersion must be commentary-config/2")
        return cls._new(
            command_id=command_id,
            kind="CONFIG_UPDATE",
            enqueued_mono_ms=enqueued_mono_ms,
            token=None,
            payload={"valid": valid, "ledger": ledger, "diagnostics": frozen_diagnostics},
        )

    @classmethod
    def tape_health(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        recorder_generation: int,
        status: Literal["ready", "degraded", "unavailable"],
        affected_detector_ids: tuple[str, ...],
        first_lost_sequence: int | None,
        last_lost_sequence: int | None,
    ) -> Self:
        if status not in {"ready", "degraded", "unavailable"}:
            raise ContractViolation("invalid tape health status")
        if not isinstance(affected_detector_ids, tuple) or len(affected_detector_ids) > 128:
            raise ContractViolation("affected detector ids must contain 0..128 items")
        detectors = tuple(sorted(str(Identifier(item)) for item in affected_detector_ids))
        if len(set(detectors)) != len(detectors):
            raise ContractViolation("affected detector ids must be unique")
        if (first_lost_sequence is None) != (last_lost_sequence is None):
            raise ContractViolation("tape health loss endpoints must both be present or null")
        if first_lost_sequence is not None and last_lost_sequence is not None:
            first_lost_sequence = _nonnegative(first_lost_sequence, "firstLostSequence")
            last_lost_sequence = _nonnegative(last_lost_sequence, "lastLostSequence")
            if last_lost_sequence < first_lost_sequence:
                raise ContractViolation("tape health loss endpoints must be ordered")
        return cls._new(
            command_id=command_id,
            kind="TAPE_HEALTH_CHANGED",
            enqueued_mono_ms=enqueued_mono_ms,
            token=None,
            payload={
                "recorderGeneration": _nonnegative(recorder_generation, "recorderGeneration"),
                "status": status,
                "affectedDetectorIds": list(detectors),
                "firstLostSequence": first_lost_sequence,
                "lastLostSequence": last_lost_sequence,
            },
            protected_hint=status == "unavailable",
        )

    @classmethod
    def component_health(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        component: Literal["llm", "tts"],
        generation: int,
        status: Literal["ready", "degraded", "unavailable"],
        reason: str | None,
    ) -> Self:
        if component not in {"llm", "tts"} or status not in {
            "ready",
            "degraded",
            "unavailable",
        }:
            raise ContractViolation("invalid component health identity")
        if reason is not None and not isinstance(reason, str):
            raise ContractViolation("component health reason must be a string or null")
        return cls._new(
            command_id=command_id,
            kind="COMPONENT_HEALTH_CHANGED",
            enqueued_mono_ms=enqueued_mono_ms,
            token=None,
            payload={
                "component": component,
                "generation": _nonnegative(generation, "generation"),
                "status": status,
                "reason": reason,
            },
            protected_hint=status == "unavailable",
        )

    @classmethod
    def recovery(
        cls,
        command_id: str,
        enqueued_mono_ms: int,
        *,
        latest_context: ContextBatchPart,
        loss_first_sequence: int,
        loss_last_sequence: int,
        safety_effects: tuple[dict[str, Any], ...],
        mailbox_sequence: int = 0,
    ) -> Self:
        first = _nonnegative(loss_first_sequence, "lossFirstMailboxSequence")
        last = _nonnegative(loss_last_sequence, "lossLastMailboxSequence")
        if last < first:
            raise ContractViolation("mailbox recovery loss range must be ordered")
        if not 1 <= len(safety_effects) <= 64:
            raise ContractViolation("mailbox recovery requires 1..64 safety effects")
        return cls._new(
            command_id=command_id,
            kind="MAILBOX_RECOVERY",
            enqueued_mono_ms=enqueued_mono_ms,
            token=None,
            payload={
                "latestTimeline": latest_context.batch.timeline,
                "latestFactView": latest_context.batch.fact_view,
                "lossFirstMailboxSequence": first,
                "lossLastMailboxSequence": last,
                "historyComplete": False,
                "safetyEffects": list(safety_effects),
            },
            external_order=latest_context.external_order,
            context_revision=latest_context.context_revision,
            mailbox_sequence=mailbox_sequence,
        )

    @classmethod
    def shutdown(cls, command_id: str, enqueued_mono_ms: int, reason: str) -> Self:
        return cls._new(
            command_id=command_id,
            kind="SHUTDOWN",
            enqueued_mono_ms=enqueued_mono_ms,
            token=None,
            payload={"reason": str(Identifier(reason)), "requestedMonoMs": enqueued_mono_ms},
        )

    @property
    def token(self) -> dict[str, Any] | None:
        if self._token_json is None:
            return None
        value = json.loads(self._token_json)
        assert isinstance(value, dict)
        return value

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._payload_json)
        assert isinstance(value, dict)
        return value

    @property
    def context_part(self) -> ContextBatchPart | None:
        return self._context_part

    @property
    def protected(self) -> bool:
        if self.kind in _ALWAYS_PROTECTED or self._protected_hint:
            return True
        return self._context_part.protected if self._context_part is not None else False

    @property
    def coalesce_key(self) -> tuple[object, ...] | None:
        return coalesce_key_for(self.kind, token=self.token, payload=self.payload)

    @property
    def fingerprint(self) -> str:
        value = self.to_dict()
        value["mailboxSequence"] = 0
        return str(canonical_sha256(value))

    def safety_effect(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "identity": str(self.command_id),
            "payloadHash": self.fingerprint,
        }

    def with_mailbox_sequence(self, sequence: int) -> Self:
        return replace(self, mailbox_sequence=_nonnegative(sequence, "mailboxSequence"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": str(self.SCHEMA_VERSION),
            "commandId": str(self.command_id),
            "kind": self.kind,
            "enqueuedMonoMs": int(self.enqueued_mono_ms),
            "mailboxSequence": self.mailbox_sequence,
            "externalOrder": None if self.external_order is None else self.external_order.to_dict(),
            "contextRevision": (
                None if self.context_revision is None else self.context_revision.to_dict()
            ),
            "token": self.token,
            "payload": self.payload,
        }
