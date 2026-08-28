"""Tests for V4 EventEnvelope wire types."""

from __future__ import annotations

import json

import pytest

from irswitch.events.envelope import (
    WIRE_MODES,
    WIRE_PHASES,
    EventEnvelope,
    EventSubject,
    legacy_trigger_to_phase,
    make_envelope,
    normalize_mode,
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


def _full_envelope() -> EventEnvelope:
    return make_envelope(
        event_type="BATTLE_HUNTING",
        mode="RACE",
        phase="ENTER",
        session_id="sess-42",
        occurred_at="2026-08-28T09:00:00Z",
        monotonic_ms=125_000,
        expires_at="2026-08-28T09:00:06Z",
        priority=60,
        severity=2,
        confidence=0.8,
        story_key="battle-with-17",
        subject=EventSubject(car_id="player", display_name="ME", car_number="3", class_position=4),
        target={"carId": "car17", "displayName": "NOVAK", "classPosition": 3},
        metrics={"gapSeconds": 0.42},
        copy={"headlineToken": "battle.headline", "statusToken": "battle.status"},
        presentation={
            "widget": "battle",
            "zone": "EVENT",
            "variant": "attack",
            "accent": "warn",
            "preferredState": "ACTIVE",
            "minHoldMs": 1500,
            "maxHoldMs": 8000,
        },
        reason={"detector": "battle", "rules": ["gap<1.0"], "suppressedAlternatives": ["pit"]},
    )


def test_to_dict_carries_every_wire_section() -> None:
    data = _full_envelope().to_dict()
    for key in (
        "schemaVersion",
        "eventId",
        "sequence",
        "sessionId",
        "eventType",
        "mode",
        "phase",
        "occurredAt",
        "monotonicMs",
        "expiresAt",
        "priority",
        "severity",
        "confidence",
        "dedupeKey",
        "correlationId",
        "storyKey",
        "subject",
        "target",
        "metrics",
        "copy",
        "presentation",
        "reason",
    ):
        assert key in data, key
    assert data["copy"]["headlineToken"] == "battle.headline"
    assert data["presentation"]["minHoldMs"] == 1500
    assert data["reason"]["suppressedAlternatives"] == ["pit"]
    assert validate_envelope(data) == []


def test_to_dict_is_json_serializable() -> None:
    text = json.dumps(_full_envelope().to_dict())
    assert json.loads(text)["eventType"] == "BATTLE_HUNTING"


def test_from_dict_roundtrip_is_stable() -> None:
    data = _full_envelope().to_dict()
    restored = EventEnvelope.from_dict(data)
    assert restored.to_dict() == data
    assert restored.target is not None and restored.target.car_id == "car17"
    assert restored.reason.rules == ("gap<1.0",)


def test_json_roundtrip_survives_the_wire() -> None:
    data = _full_envelope().to_dict()
    restored = EventEnvelope.from_dict(json.loads(json.dumps(data)))
    assert restored.to_dict() == data


def test_target_is_null_not_absent_when_unset() -> None:
    data = make_envelope(event_type="LAP_COMPLETE").to_dict()
    assert data["target"] is None
    assert EventEnvelope.from_dict(data).target is None


def test_manager_can_stamp_identity_and_rewrite_phase() -> None:
    env = make_envelope(event_type="PIT_STOP", phase="enter")
    assert env.phase == "ENTER"
    env.stamp("evt-9", 3)
    env.phase = "EXIT"
    assert (env.event_id, env.sequence, env.phase) == ("evt-9", 3, "EXIT")
    assert validate_envelope(env) == []


def test_every_wire_phase_validates() -> None:
    assert WIRE_PHASES == {
        "ENTER",
        "ACTIVE",
        "UPDATE",
        "COMPACT",
        "SUSPEND",
        "RESUME",
        "EXIT",
        "RESULT",
    }
    for phase in WIRE_PHASES:
        assert validate_envelope(make_envelope(event_type="X", phase=phase)) == []


def test_legacy_phase_mapping_covers_case_and_fallback() -> None:
    assert legacy_trigger_to_phase(" Trigger ") == "RESULT"
    assert legacy_trigger_to_phase("Exit") == "EXIT"
    assert legacy_trigger_to_phase("compact") == "COMPACT"
    assert legacy_trigger_to_phase("suspend") == "SUSPEND"
    assert legacy_trigger_to_phase("resume") == "RESUME"
    assert legacy_trigger_to_phase("result") == "RESULT"
    # Hot-path callers opt into a fail-soft default instead of an exception.
    assert legacy_trigger_to_phase("nope", default="RESULT") == "RESULT"
    assert legacy_trigger_to_phase("", default="UPDATE") == "UPDATE"


def test_mode_whitelist() -> None:
    assert WIRE_MODES == {"PRACTICE", "QUALIFYING", "RACE", "GENERIC", "unknown"}
    for mode in WIRE_MODES:
        assert validate_envelope(make_envelope(event_type="X", mode=mode)) == []
    bad = make_envelope(event_type="X").to_dict()
    bad["mode"] = "HOTLAP"
    assert any("invalid mode" in e for e in validate_envelope(bad))


def test_unknown_mode_is_normalized_not_rejected() -> None:
    assert make_envelope(event_type="X", mode="hotlap").mode == "unknown"
    assert make_envelope(event_type="X", mode="race").mode == "RACE"
    assert normalize_mode(None) == "unknown"


def test_confidence_lower_bound_and_non_numeric() -> None:
    assert validate_envelope(make_envelope(event_type="X", confidence=0.0)) == []
    assert any(
        "confidence out of range" in e
        for e in validate_envelope(make_envelope(event_type="X", confidence=-0.1))
    )
    bad = make_envelope(event_type="X").to_dict()
    bad["confidence"] = "high"
    assert any("confidence not numeric" in e for e in validate_envelope(bad))


def test_camel_case_kwargs_match_snake_case() -> None:
    assert make_envelope(eventType="X", monotonicMs=10, sessionId="s") == make_envelope(
        event_type="X", monotonic_ms=10, session_id="s"
    )
