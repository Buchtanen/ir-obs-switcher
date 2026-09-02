"""N12 A1/A4 immutable transport contract tests."""

from __future__ import annotations

import math

import pytest

from irswitch.events.envelope import make_envelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    ConfigUpdate,
    FrozenAcceptedEventBatch,
    SessionReset,
    StreamContractError,
    canonical_json_bytes,
    freeze_accepted_event,
    freeze_config,
    freeze_context,
    freeze_envelope,
    thaw_context,
    thaw_envelope,
)


def _envelope(*, sequence: int = 1, phase: str = "RESULT", metrics=None):
    return make_envelope(
        event_type="LAP_COMPLETE",
        phase=phase,
        mode="RACE",
        event_id=f"session:LAP_COMPLETE:{sequence}",
        sequence=sequence,
        session_id="session",
        priority=50,
        monotonic_ms=1_000,
        dedupe_key="lap",
        correlation_id="lap:1",
        metrics=metrics or {"lap": 1, "nested": {"values": [1, 2]}},
    )


def _context(*, version: int = 1, session_id: str = "session") -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": version,
            "session_id": session_id,
            "captured_monotonic_ms": 1_000,
            "identity": {},
            "race": {},
            "bio": {},
            "story": {},
            "situation": {},
            "config": {},
        }
    )


def test_freeze_envelope_is_canonical_and_thaws_private_copies() -> None:
    envelope = _envelope()
    frozen = freeze_envelope(envelope)
    assert frozen == freeze_envelope(_envelope())
    assert b'"eventId":"session:LAP_COMPLETE:1"' in frozen

    first = thaw_envelope(frozen)
    second = thaw_envelope(frozen)
    first.metrics["nested"]["values"].append(3)
    first.metrics["consumer"] = "overlay"

    assert second.metrics == {"lap": 1, "nested": {"values": [1, 2]}}
    assert thaw_envelope(frozen).metrics == second.metrics


@pytest.mark.parametrize(
    "event_id,sequence",
    [("", 1), ("session:LAP_COMPLETE:0", 0), ("session:LAP_COMPLETE:-1", -1)],
)
def test_freeze_requires_producer_identity(event_id: str, sequence: int) -> None:
    envelope = _envelope(sequence=1)
    envelope.event_id = event_id
    envelope.sequence = sequence
    with pytest.raises(StreamContractError):
        freeze_envelope(envelope)


def test_canonical_json_rejects_non_json_and_non_finite_metrics() -> None:
    with pytest.raises(StreamContractError):
        canonical_json_bytes({"bad": object()})
    with pytest.raises(StreamContractError):
        canonical_json_bytes({"bad": math.nan})


def test_batch_rejects_empty_or_mismatched_context() -> None:
    with pytest.raises(StreamContractError, match="empty"):
        FrozenAcceptedEventBatch(1, "session", 1, 1_000, 1, _context(), ())
    event = freeze_accepted_event(
        _envelope(),
        audiences=("overlay", "commentary"),
        source="event_engine",
        source_ordinal=0,
    )
    with pytest.raises(StreamContractError, match="session id"):
        FrozenAcceptedEventBatch(1, "other", 1, 1_000, 1, _context(), (event,))


def test_context_and_config_are_canonical_typed_boundaries() -> None:
    context = _context()
    assert thaw_context(context)["schema_version"] == CONTEXT_SCHEMA_VERSION
    reset = SessionReset("old", "new", "session_changed", 2)
    config = ConfigUpdate(3, freeze_config({"generation": 3, "language": "cs"}), 3)
    assert reset.new_session_id == "new"
    assert config.generation == 3
