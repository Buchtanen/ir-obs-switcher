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
from typing import Any

from irswitch.commentary.mailbox import AdmissionResult, NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.primitives import ContractViolation
from irswitch.events.narrative import NarrativeEvent, partition_context_batches
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus

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
    attachment remain a later cutover slice. This helper only shapes
    actor/recovery fields already owned by the library RuntimeStatus.
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
            }
        },
        "timeline": {
            "broadcastEpoch": int(status.broadcast_epoch),
            "streamEpoch": int(status.stream_epoch),
            "narrativeRunActive": bool(status.narrative_run_active),
            "streamActive": status.stream_active,
            "streamState": str(status.stream_state),
            "historyComplete": bool(status.history_complete),
        },
        "components": {
            "llm": {"status": llm_status, "reason": None},
            "tts": {"status": tts_status, "reason": None},
            "tape": tape_component,
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
