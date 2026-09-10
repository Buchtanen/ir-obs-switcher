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
    """Default config block when no CONFIG_UPDATE ledger is cached."""

    return {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 0,
        "desiredHash": _UNLOADED_HASH,
        "effectiveHash": _UNLOADED_HASH,
        "applySequence": 0,
        "pendingChanges": [],
    }


def _config_projection(status: RuntimeStatus) -> dict[str, Any]:
    """Project live CONFIG_UPDATE ledger or unloaded zeros."""

    ledger = status.config_ledger
    if not isinstance(ledger, dict):
        return _unloaded_config_projection()
    desired_generation = ledger.get("desiredGeneration")
    desired_hash = ledger.get("desiredHash")
    effective_hash = ledger.get("effectiveHash")
    apply_sequence = ledger.get("applySequence")
    pending = ledger.get("pendingChanges")
    if (
        isinstance(desired_generation, bool)
        or not isinstance(desired_generation, int)
        or desired_generation < 0
        or not isinstance(desired_hash, str)
        or not desired_hash.startswith("sha256:")
        or not isinstance(effective_hash, str)
        or not effective_hash.startswith("sha256:")
        or isinstance(apply_sequence, bool)
        or not isinstance(apply_sequence, int)
        or apply_sequence < 0
        or not isinstance(pending, list)
    ):
        return _unloaded_config_projection()
    return {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": int(desired_generation),
        "desiredHash": desired_hash,
        "effectiveHash": effective_hash,
        "applySequence": int(apply_sequence),
        "pendingChanges": [dict(item) if isinstance(item, dict) else item for item in pending],
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


def _episodes_projection(status: RuntimeStatus) -> dict[str, Any]:
    counts = status.episode_counts
    if not isinstance(counts, dict):
        return _empty_episodes_projection()
    required = (
        "active",
        "candidate",
        "suspended",
        "retainedCurrentCapacity",
        "resolved",
        "resolvedCapacity",
    )
    if any(
        isinstance(counts.get(key), bool) or not isinstance(counts.get(key), int)
        for key in required
    ):
        return _empty_episodes_projection()
    return {key: int(counts[key]) for key in required}


def _by_tape_channel_projection(status: RuntimeStatus) -> dict[str, dict[str, int]]:
    raw = status.by_tape_channel
    if not isinstance(raw, dict) or not raw:
        return {}
    projected: dict[str, dict[str, int]] = {}
    required = ("kick", "accepted", "queued", "selected", "started", "expired")
    for channel, counters in raw.items():
        if not isinstance(channel, str) or not isinstance(counters, dict):
            continue
        if any(
            isinstance(counters.get(key), bool) or not isinstance(counters.get(key), int)
            for key in required
        ):
            continue
        projected[channel] = {key: int(counters[key]) for key in required}
    return projected


_TTS_BACKENDS = frozenset({"sapi", "espeak", "supertonic"})
_LLM_MODEL_UNCONFIGURED = "unconfigured"


def _timeline_session_identity(status: RuntimeStatus) -> dict[str, Any]:
    """Project session identity with StatusResponse all-or-none nulls."""

    plan = status.session_plan
    ref = status.session_ref
    occurrence_id = status.occurrence_id
    lineage_id = status.lineage_id
    stage = status.stage
    if plan is None or ref is None or occurrence_id is None or lineage_id is None or stage is None:
        return {
            "sessionPlan": None,
            "sessionRef": None,
            "occurrenceId": None,
            "lineageId": None,
            "stage": None,
        }
    return {
        "sessionPlan": dict(plan),
        "sessionRef": dict(ref),
        "occurrenceId": occurrence_id,
        "lineageId": lineage_id,
        "stage": stage,
    }


def _config_desired_generation(status: RuntimeStatus) -> int:
    """Best-effort desiredGeneration from CONFIG_UPDATE ledger; else 0."""

    ledger = status.config_ledger
    if not isinstance(ledger, dict):
        return 0
    desired = ledger.get("desiredGeneration")
    if isinstance(desired, bool) or not isinstance(desired, int) or desired < 0:
        return 0
    return int(desired)


def _llm_component_projection(status: RuntimeStatus) -> dict[str, Any]:
    """#273 llm block — live transport/residency when LlmComponent is attached."""

    config_generation = _config_desired_generation(status)
    if not status.llm_attached:
        health = str(status.component_health.get("llm", "ready"))
        return {
            "status": health,
            "reason": None,
            "generation": 0,
            "configGeneration": config_generation,
            "model": _LLM_MODEL_UNCONFIGURED,
            "residencyEvidence": "not_requested",
            "lastAttempt": None,
        }
    health = str(status.component_health.get("llm", "ready"))
    model = status.llm_model if status.llm_model else _LLM_MODEL_UNCONFIGURED
    evidence = status.llm_residency_evidence
    if evidence not in {"warmup_succeeded", "not_requested"}:
        evidence = "not_requested"
    return {
        "status": health,
        "reason": status.llm_reason,
        "generation": int(status.llm_generation),
        "configGeneration": config_generation,
        "model": model,
        "residencyEvidence": evidence,
        "lastAttempt": (None if status.llm_last_attempt is None else dict(status.llm_last_attempt)),
    }


def _tts_component_projection(
    status: RuntimeStatus,
    *,
    component_status: str,
) -> dict[str, Any]:
    """#273 tts block — speech-lane backend plus configGeneration from ledger."""

    mapped_backend = status.speech_backend if status.speech_backend in _TTS_BACKENDS else None
    return {
        "status": component_status,
        "reason": None,
        "backend": mapped_backend,
        "backendGeneration": int(status.speech_backend_generation or 0),
        "configGeneration": _config_desired_generation(status),
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
    thin #273 catalog/config/episodes/byTapeChannel projection (packaged
    catalog hash; CONFIG_UPDATE ledger when cached; EpisodeRegistry /
    OpportunityQueue counters when injected; otherwise unloaded/empty
    stubs), schema-complete llm/tts components (live transport/residency when an
    LlmComponent is attached; otherwise stubs), and null-or-live timeline
    session-identity fields (sessionPlan/sessionRef/occurrenceId/
    lineageId/stage — all-or-none; filled from APPLY_CONTEXT timeline
    when complete).
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
        "episodes": _episodes_projection(status),
        "catalog": dict(_packaged_catalog_projection()),
        "config": _config_projection(status),
        "byTapeChannel": _by_tape_channel_projection(status),
        "loop": {
            "active": bool(status.loop_active),
        },
        "timeline": {
            "broadcastEpoch": int(status.broadcast_epoch),
            "streamEpoch": int(status.stream_epoch),
            "narrativeRunActive": bool(status.narrative_run_active),
            "streamActive": status.stream_active,
            "streamState": str(status.stream_state),
            **_timeline_session_identity(status),
            "historyComplete": history_complete,
        },
        "components": {
            "llm": _llm_component_projection(status),
            "tts": _tts_component_projection(
                status,
                component_status=tts_status,
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
