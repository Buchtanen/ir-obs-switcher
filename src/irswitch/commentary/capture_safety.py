"""Composition-owned required-capture loss coordinator.

TapeWriter emits CaptureHealthNotice. This coordinator disables only the named
experimental required detectors through a narrow port, closes upstream truth
as required_capture_lost, then admits TAPE_HEALTH_CHANGED plus context.
It never imports NarrativeRuntime or a concrete DetectorBank.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from irswitch.commentary.capture_plan import StreamCapturePlan
from irswitch.commentary.tape_queue import CaptureHealthNotice
from irswitch.commentary.tape_safety import tape_health_command
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.primitives import ContractViolation


class DetectorControl(Protocol):
    def disable_for_run(self, detector_ids: tuple[str, ...], reason: str) -> tuple[str, ...]:
        """Disable only the named experimental detectors. Return those actually disabled."""


class TruthCloser(Protocol):
    def close_required_capture_lost(self, detector_ids: tuple[str, ...]) -> None:
        """Close FSMs/facts/candidates for the named detectors."""


class BundleAdmiter(Protocol):
    def admit_bundle(self, control: NarrativeCommand, context: NarrativeCommand) -> Any:
        """Atomically admit tape-health plus APPLY_CONTEXT_BATCH."""


@dataclass(frozen=True, slots=True)
class CaptureSafetyEffect:
    applied: bool
    reason: str
    disabled_detector_ids: tuple[str, ...]
    health_command: NarrativeCommand | None = None


class CaptureSafetyCoordinator:
    """Fail-soft required-capture fanout. Recorder repair cannot re-enable in-run."""

    def __init__(
        self,
        *,
        plan: StreamCapturePlan,
        recorder_generation: int,
        detector_control: DetectorControl,
        truth_closer: TruthCloser,
        mailbox: BundleAdmiter,
    ) -> None:
        if recorder_generation < 0:
            raise ContractViolation("recorderGeneration must be a nonnegative int")
        self._plan = plan
        self._recorder_generation = recorder_generation
        self._detector_control = detector_control
        self._truth_closer = truth_closer
        self._mailbox = mailbox
        self._disabled: set[str] = set()
        self._lock = Lock()

    @property
    def disabled_for_run(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._disabled))

    def begin_stream(self, plan: StreamCapturePlan, *, recorder_generation: int) -> None:
        if recorder_generation < 0:
            raise ContractViolation("recorderGeneration must be a nonnegative int")
        with self._lock:
            self._plan = plan
            self._recorder_generation = recorder_generation
            self._disabled.clear()

    def note_recorder_ready(self) -> None:
        """Repair is visible but never re-enables a detector in the current run."""

        return None

    def apply_notice(
        self,
        notice: CaptureHealthNotice,
        *,
        command_id: str,
        enqueued_mono_ms: int,
        context: NarrativeCommand,
    ) -> CaptureSafetyEffect:
        if not isinstance(notice, CaptureHealthNotice):
            raise ContractViolation("capture safety requires CaptureHealthNotice")
        if context.kind != "APPLY_CONTEXT_BATCH":
            raise ContractViolation("capture safety bundle requires APPLY_CONTEXT_BATCH")
        with self._lock:
            if notice.recorder_generation != self._recorder_generation:
                return CaptureSafetyEffect(False, "stale_generation", ())
            eligible = self._eligible(notice.affected_detector_ids)
            pending = tuple(item for item in eligible if item not in self._disabled)
            if not pending:
                return CaptureSafetyEffect(False, "duplicate", ())
            self._disabled.update(pending)
        try:
            disabled = tuple(
                self._detector_control.disable_for_run(pending, "required_capture_lost")
            )
            self._truth_closer.close_required_capture_lost(disabled)
            health = tape_health_command(notice, command_id, enqueued_mono_ms)
            self._mailbox.admit_bundle(health, context)
            return CaptureSafetyEffect(True, "applied", disabled, health)
        except ContractViolation:
            raise
        except Exception:
            return CaptureSafetyEffect(False, "coordinator_failed", pending)

    def _eligible(self, detector_ids: tuple[str, ...]) -> tuple[str, ...]:
        eligible: list[str] = []
        for detector_id in detector_ids:
            try:
                entry = self._plan.entry(detector_id)
            except ContractViolation:
                continue
            if (
                entry.experimental
                and entry.effective_policy == "required"
                and (entry.enabled or entry.capture_active)
            ):
                eligible.append(entry.detector_id)
        return tuple(eligible)
