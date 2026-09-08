"""Composition helper for required-capture tape loss.

TapeWriter never imports DetectorBank or NarrativeRuntime. Composition reads
the out-of-queue CaptureHealthLatch and builds the protected health command.
"""

from __future__ import annotations

from irswitch.commentary.tape_queue import CaptureHealthNotice
from irswitch.contracts.command import NarrativeCommand


def tape_health_command(
    notice: CaptureHealthNotice,
    command_id: str,
    enqueued_mono_ms: int,
) -> NarrativeCommand:
    """Build TAPE_HEALTH_CHANGED(unavailable) from a latch notice."""

    return NarrativeCommand.tape_health(
        command_id,
        enqueued_mono_ms,
        recorder_generation=notice.recorder_generation,
        status="unavailable",
        affected_detector_ids=notice.affected_detector_ids,
        first_lost_sequence=notice.first_lost_sequence,
        last_lost_sequence=notice.last_lost_sequence,
    )
