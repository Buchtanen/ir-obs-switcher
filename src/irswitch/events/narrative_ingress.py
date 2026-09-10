"""Shadow fanout→mailbox ingress for NarrativeRuntime (#284).

Library-adjacent adapter: partitions one accepted publication into
``APPLY_CONTEXT_BATCH`` commands and admits them into ``NarrativeMailbox``,
preserving ``(fanout_stream_sequence, source_ordinal)`` external order.

Not exported from ``events/__init__.py``. Not constructed by
``commentary.consumer``. ``race.runtime`` may construct
``NarrativeShadowConsumer`` (which owns an ingress) only when
``_narrative_shadow_enabled`` is explicitly True; that flag defaults False.
``project_commentary_health_component`` is the only helper consumed by
``GET /health`` (bounded commentary field); it does not construct an ingress.
Production EventSubscription cutover still needs an explicit kick.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from irswitch.commentary.mailbox import AdmissionResult, NarrativeMailbox
from irswitch.contracts.catalog_loader import load_narrative_catalog
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.primitives import ContractViolation
from irswitch.events.episode_registry import ACTIVE_CAP, RESOLVED_CAP
from irswitch.events.narrative import NarrativeEvent, partition_context_batches
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus
from irswitch.events.opportunity_queue import OPPORTUNITY_CAPACITY

_UNLOADED_HASH = "sha256:" + ("0" * 64)
_CATALOG_EVENT_IDENTIFIER_COUNT = 60
_CATALOG_BEAT_COUNT = 64


@lru_cache(maxsize=1)
def _packaged_catalog_projection() -> dict[str, Any]:
    """Schema-shaped catalog block from the frozen packaged narrative catalog.

    Const counts match StatusResponse; hash is the live packaged digest.
    Catalog load failure must never raise out of status projection.
    """

    try:
        catalog = load_narrative_catalog().require_catalog()
        digest = str(catalog.catalog_hash)
    except Exception:
        digest = _UNLOADED_HASH
    return {
        "schemaVersion": "narrative-catalog/2",
        "hash": digest,
        "eventIdentifierCount": _CATALOG_EVENT_IDENTIFIER_COUNT,
        "beatCount": _CATALOG_BEAT_COUNT,
    }


def _unloaded_config_projection() -> dict[str, Any]:
    """Thin config block — live apply/generation wiring is #273 remainder."""

    return {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 0,
        "desiredHash": _UNLOADED_HASH,
        "effectiveHash": _UNLOADED_HASH,
        "applySequence": 0,
        "pendingChanges": [],
    }


def _empty_episodes_projection() -> dict[str, Any]:
    return {
        "active": 0,
        "candidate": 0,
        "suspended": 0,
        "retainedCurrentCapacity": int(ACTIVE_CAP),
        "resolved": 0,
        "resolvedCapacity": int(RESOLVED_CAP),
    }


_TTS_BACKENDS = frozenset({"sapi", "espeak", "supertonic"})
_LLM_MODEL_UNCONFIGURED = "unconfigured"


def _llm_component_projection(status: str) -> dict[str, Any]:
    """Thin #273 llm block — schema-complete defaults, no live transport wiring."""

    return {
        "status": status,
        "reason": None,
        "generation": 0,
        "configGeneration": 0,
        "model": _LLM_MODEL_UNCONFIGURED,
        "residencyEvidence": "not_requested",
        "lastAttempt": None,
    }


def _tts_component_projection(
    status: str,
    *,
    backend: str | None,
    backend_generation: int | None,
) -> dict[str, Any]:
    """Thin #273 tts block — schema-complete defaults; backend from speech lane when known."""

    mapped_backend = backend if backend in _TTS_BACKENDS else None
    return {
        "status": status,
        "reason": None,
        "backend": mapped_backend,
        "backendGeneration": int(backend_generation or 0),
        "configGeneration": 0,
        "quarantinedGeneration": None,
        "voice": None,
    }


_LANE_TO_SPEECH = {
    "idle": "idle",
    "building": "building",
    "committed": "committed",
    "speaking": "speaking",
    "stopping": "stopping",
}

_RUNTIME_TO_STATUS = {
    "disabled": "disabled",
    "starting": "starting",
    "ready": "ready",
    "degraded": "degraded",
    "stopping": "stopping",
    "stopped": "stopped",
}


@dataclass(frozen=True, slots=True)
class IngressAdmission:
    accepted: bool
    reason: str
    command_ids: tuple[str, ...]
    mailbox_sequences: tuple[int, ...]
    admissions: tuple[AdmissionResult, ...]
    effects: tuple[str, ...]


class NarrativeIngress:
    """Admit partitioned context publications into one NarrativeMailbox."""

    def __init__(self, mailbox: NarrativeMailbox | None = None) -> None:
        # Empty NarrativeMailbox is falsy via __len__; only replace on None.
        self._mailbox = NarrativeMailbox() if mailbox is None else mailbox

    @property
    def mailbox(self) -> NarrativeMailbox:
        return self._mailbox

    def admit_context_publication(
        self,
        *,
        timeline: dict[str, Any],
        fact_view: dict[str, Any],
        events: tuple[NarrativeEvent, ...],
        fanout_stream_sequence: int,
        command_id_prefix: str,
        enqueued_mono_ms: int,
    ) -> IngressAdmission:
        if not command_id_prefix:
            raise ContractViolation("command_id_prefix must be non-empty")
        if enqueued_mono_ms < 0:
            raise ContractViolation("enqueued_mono_ms must be nonnegative")
        parts = partition_context_batches(
            timeline=timeline,
            fact_view=fact_view,
            events=events,
            fanout_stream_sequence=fanout_stream_sequence,
        )
        admissions: list[AdmissionResult] = []
        effects: list[str] = ["ingress_partitioned"]
        command_ids: list[str] = []
        mailbox_sequences: list[int] = []
        for index, part in enumerate(parts):
            command_id = f"{command_id_prefix}:{index}"
            command = NarrativeCommand.context_batch(command_id, enqueued_mono_ms, part)
            result = self._mailbox.admit(command)
            admissions.append(result)
            effects.append(f"ingress_step:{result.reason}")
            if not result.accepted:
                effects.append("ingress_rejected")
                return IngressAdmission(
                    accepted=False,
                    reason=result.reason,
                    command_ids=tuple(command_ids),
                    mailbox_sequences=tuple(mailbox_sequences),
                    admissions=tuple(admissions),
                    effects=tuple(effects),
                )
            command_ids.append(str(result.command.command_id))
            mailbox_sequences.append(int(result.command.mailbox_sequence))
            effects.append("ingress_admitted")
        effects.append("ingress_publication_complete")
        return IngressAdmission(
            accepted=True,
            reason="accepted",
            command_ids=tuple(command_ids),
            mailbox_sequences=tuple(mailbox_sequences),
            admissions=tuple(admissions),
            effects=tuple(effects),
        )


def project_runtime_status(status: RuntimeStatus) -> dict[str, Any]:
    """Project RuntimeStatus into a commentary-runtime/2 status subset.

    HTTP mount: ``GET /api/commentary/runtime`` via ``narrative_runtime_http``
    (additive; does not start the actor loop). Full schema / live actor
    attachment remain a later cutover slice. This helper shapes
    actor/recovery fields already owned by the library RuntimeStatus plus
    thin #273 catalog/config/episodes/byTapeChannel defaults (packaged
    catalog hash; unloaded config; empty episode/tape-channel counters;
    opportunities queue stub; detectors/facts stubs), schema-complete
    llm/tts component stubs (no live transport/residency wiring), and
    null timeline session-identity fields (sessionPlan/sessionRef/
    occurrenceId/lineageId/stage — all-or-none nulls until live wiring).
    """

    if not isinstance(status, RuntimeStatus):
        raise ContractViolation("projector requires RuntimeStatus")
    tape_status = status.tape_status
    tape_component = {
        "status": "disabled" if not tape_status else str(tape_status),
        "reason": None,
        "path": None,
        "drops": 0,
        "dropsByPriority": {"sample": 0, "normal": 0, "critical": 0},
    }
    if tape_status == "unavailable":
        tape_component["status"] = "unavailable"
    llm_status = str(status.component_health.get("llm", "ready"))
    tts_status = str(status.component_health.get("tts", "ready"))
    last_terminal = status.speech_last_terminal
    history_complete = bool(status.history_complete)
    return {
        "schemaVersion": "commentary-runtime/2",
        "status": _RUNTIME_TO_STATUS.get(status.runtime_state, "degraded"),
        "reason": None if not status.reason_codes else status.reason_codes[0],
        "language": "en",
        "speech": {
            "state": _LANE_TO_SPEECH.get(status.lane, "idle"),
            "sourceKind": status.speech_source_kind,
            "utteranceId": status.speech_utterance_id,
            "beatId": status.speech_beat_id,
            "opportunityId": status.speech_opportunity_id,
            "backend": status.speech_backend,
            "backendGeneration": status.speech_backend_generation,
            "dispatchedAtMonoMs": status.speech_dispatched_at_mono_ms,
            "acceptedAtMonoMs": status.speech_accepted_at_mono_ms,
            "lastTerminal": None if last_terminal is None else dict(last_terminal),
        },
        "queues": {
            "mailbox": {
                "depth": int(status.mailbox_depth),
                "capacity": int(status.mailbox_capacity),
                "overflows": int(status.mailbox_overflows),
            },
            "opportunities": {
                "depth": 0,
                "capacity": int(OPPORTUNITY_CAPACITY),
                "expired": 0,
                "evicted": 0,
            },
        },
        "episodes": _empty_episodes_projection(),
        "catalog": dict(_packaged_catalog_projection()),
        "config": _unloaded_config_projection(),
        "byTapeChannel": {},
        "timeline": {
            "broadcastEpoch": int(status.broadcast_epoch),
            "streamEpoch": int(status.stream_epoch),
            "narrativeRunActive": bool(status.narrative_run_active),
            "streamActive": status.stream_active,
            "streamState": str(status.stream_state),
            # Session identity is all-or-none; library slice keeps nulls until
            # live session-plan wiring lands (#273 remainder).
            "sessionPlan": None,
            "sessionRef": None,
            "occurrenceId": None,
            "lineageId": None,
            "stage": None,
            "historyComplete": history_complete,
        },
        "components": {
            "llm": _llm_component_projection(llm_status),
            "tts": _tts_component_projection(
                tts_status,
                backend=status.speech_backend,
                backend_generation=status.speech_backend_generation,
            ),
            "tape": tape_component,
            "detectors": {"status": "ready", "reason": None, "disabled": []},
            "facts": {
                "status": "ready",
                "reason": None,
                "viewRevision": 0,
                "active": 0,
                "historicalSummaries": 0,
                "historyComplete": history_complete,
            },
        },
        "recovery": {
            "count": int(status.recovery_count),
            "lossFirst": status.last_recovery_loss_first,
            "lossLast": status.last_recovery_loss_last,
            "safetyEffectCount": status.last_recovery_safety_effect_count,
            "cancelledLane": status.last_recovery_cancelled_lane,
        },
        "diagnostics": {
            "lastAdmissionReason": status.last_admission_reason,
            "admissionDiagnostics": list(status.admission_diagnostics),
            "reasonCodes": list(status.reason_codes),
        },
    }


def project_commentary_health_component(status: RuntimeStatus | None = None) -> dict[str, Any]:
    """Bounded ``/health`` commentary field (#273 subset owned by #284).

    Disabled/degraded commentary never fails overall service health. When
    ``status`` is omitted, projects the disabled library default.
    """

    if status is None:
        projected = project_runtime_status(NarrativeRuntime().status())
    else:
        projected = project_runtime_status(status)
    return {
        "status": projected["status"],
        "reason": projected["reason"],
    }
