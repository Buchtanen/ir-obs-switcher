"""Tests for V4 EventEnvelope wire types."""

from __future__ import annotations

import pytest

from irswitch.events.envelope import (
    WIRE_PHASES,
    EventEnvelope,
    legacy_trigger_to_phase,
    make_envelope,
    validate_envelope,
)


def test_make_envelope_roundtrip() -> None:
    env = make_envelope(
        event_type="HUNTING",
        mode="RACE",
        phase="ENTER",
        priority=60,
        confidence=0.91,
        metrics={"gapSeconds": 0.84},
        target={"car_id": "car17", "display_name": "NOVAK"},
    )
    data = env.to_dict()
    assert data["eventType"] == "HUNTING"
    assert data["phase"] == "ENTER"
    assert data["mode"] == "RACE"
    assert data["target"]["carId"] == "car17"
    assert data["metrics"]["gapSeconds"] == 0.84
    assert data["schemaVersion"] == "1.0"
    assert validate_envelope(env) == []
    assert validate_envelope(data) == []


def test_legacy_trigger_to_phase() -> None:
    assert legacy_trigger_to_phase("trigger") == "RESULT"
    assert legacy_trigger_to_phase("enter") == "ENTER"
    assert legacy_trigger_to_phase("UPDATE") == "UPDATE"
    assert legacy_trigger_to_phase("ACTIVE") == "ACTIVE"
    with pytest.raises(ValueError):
        legacy_trigger_to_phase("nope")


def test_phase_whitelist() -> None:
    env = make_envelope(event_type="X", phase="ENTER")
    bad = env.to_dict()
    bad["phase"] = "FLASH"
    errors = validate_envelope(bad)
    assert any("invalid phase" in e for e in errors)
    assert "ACTIVE" in WIRE_PHASES


def test_validate_missing_required() -> None:
    errors = validate_envelope({"phase": "ENTER", "eventType": "X"})
    assert any("missing" in e for e in errors)


def test_confidence_bounds() -> None:
    env = make_envelope(event_type="X", confidence=1.5)
    errors = validate_envelope(env)
    assert any("confidence out of range" in e for e in errors)


def test_sequence_zero_allowed() -> None:
    env = make_envelope(event_type="LAP_COMPLETE", sequence=0)
    assert isinstance(env, EventEnvelope)
    assert validate_envelope(env) == []
