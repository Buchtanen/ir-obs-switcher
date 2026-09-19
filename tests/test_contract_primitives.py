"""Focused contract tests for the shared v2 narrative vocabulary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import (
    MAX_SIGNED_INT64,
    BroadcastEpoch,
    Confidence,
    ContractViolation,
    CorrelationId,
    CycleAttemptOrdinal,
    FactQuality,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    PlanningSeedMaterial,
    ProcessMonotonicTime,
    ScalarType,
    SchemaVersion,
    SessionClock,
    SourceSequence,
    Stage,
    StreamClock,
    StreamEpoch,
    ValidityWindow,
    canonical_json,
    canonical_sha256,
    deterministic_planning_seed,
    validate_occurrence_lineage,
    validate_scalar,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
PACKAGED_SCHEMAS = ROOT / "src" / "irswitch" / "contracts" / "schemas" / "v2"


def test_occurrence_id_round_trip_is_canonical() -> None:
    occurrence = OccurrenceId.parse("3:qualifying:12")

    assert occurrence == OccurrenceId(StreamEpoch(3), Stage.QUALIFYING, 12)
    assert str(occurrence) == "3:qualifying:12"
    assert OccurrenceId.parse(str(occurrence)) == occurrence


@pytest.mark.parametrize(
    "raw",
    [
        "0:race:0",
        "03:race:0",
        "3:RACE:0",
        "3:r:0",
        "3:race:00",
        "3/race/0",
        "３:race:0",
    ],
)
def test_occurrence_id_rejects_noncanonical_values(raw: str) -> None:
    with pytest.raises(ContractViolation):
        OccurrenceId.parse(raw)


def test_lineage_id_round_trip_requires_canonical_stage_order() -> None:
    lineage = LineageId.parse("3:practice:0>3:qualifying:1>3:race:2")

    assert tuple(item.stage for item in lineage.occurrences) == (
        Stage.PRACTICE,
        Stage.QUALIFYING,
        Stage.RACE,
    )
    assert str(lineage) == "3:practice:0>3:qualifying:1>3:race:2"
    assert LineageId.parse(str(lineage)) == lineage


@pytest.mark.parametrize(
    "raw",
    [
        "3:race:0>3:qualifying:0",
        "3:practice:0>4:race:0",
        "3:practice:0>3:practice:1",
        "3:practice:0>3:qualifying:0>3:race:0>3:race:1",
    ],
)
def test_lineage_id_rejects_incoherent_values(raw: str) -> None:
    with pytest.raises(ContractViolation):
        LineageId.parse(raw)


@pytest.mark.parametrize("raw", ["battle:car.17", "source_1", "A-b"])
def test_correlation_id_uses_shared_ascii_id_contract(raw: str) -> None:
    assert str(CorrelationId(raw)) == raw


@pytest.mark.parametrize("raw", ["", "-bad", "with space", "řidič", "a" * 129])
def test_correlation_id_rejects_invalid_ids(raw: str) -> None:
    with pytest.raises(ContractViolation):
        CorrelationId(raw)


def test_distinct_epoch_and_sequence_primitives_enforce_bounds() -> None:
    assert int(BroadcastEpoch(0)) == 0
    assert int(StreamEpoch(0)) == 0
    assert int(SourceSequence(1)) == 1
    assert int(MonotonicMs(MAX_SIGNED_INT64)) == MAX_SIGNED_INT64

    for constructor, value in (
        (BroadcastEpoch, -1),
        (StreamEpoch, -1),
        (SourceSequence, 0),
        (MonotonicMs, -1),
        (MonotonicMs, MAX_SIGNED_INT64 + 1),
    ):
        with pytest.raises(ContractViolation):
            constructor(value)


def test_live_epochs_are_positive_but_zero_remains_serializable_status() -> None:
    assert BroadcastEpoch(0).is_allocated is False
    assert StreamEpoch(0).is_allocated is False
    assert BroadcastEpoch(4).require_active() == BroadcastEpoch(4)
    assert StreamEpoch(7).require_active() == StreamEpoch(7)

    with pytest.raises(ContractViolation):
        BroadcastEpoch(0).require_active()
    with pytest.raises(ContractViolation):
        StreamEpoch(0).require_active()


def test_process_monotonic_time_never_crosses_process_origins() -> None:
    start = ProcessMonotonicTime("proc-a", MonotonicMs(1_000))
    end = ProcessMonotonicTime("proc-a", MonotonicMs(1_250))

    assert end.elapsed_since(start) == 250
    with pytest.raises(ContractViolation):
        start.elapsed_since(end)
    with pytest.raises(ContractViolation):
        end.elapsed_since(ProcessMonotonicTime("proc-b", MonotonicMs(900)))


def test_stream_and_session_clocks_are_process_and_identity_scoped() -> None:
    stream_clock = StreamClock("proc-a", StreamEpoch(2), MonotonicMs(7_000))
    clock = SessionClock("proc-a", OccurrenceId.parse("2:race:0"), MonotonicMs(8_000))

    assert stream_clock.elapsed_at("proc-a", StreamEpoch(2), MonotonicMs(8_450)) == 1_450
    assert clock.elapsed_at("proc-a", OccurrenceId.parse("2:race:0"), MonotonicMs(8_450)) == 450
    with pytest.raises(ContractViolation):
        stream_clock.elapsed_at("proc-b", StreamEpoch(2), MonotonicMs(8_450))
    with pytest.raises(ContractViolation):
        clock.elapsed_at("proc-a", OccurrenceId.parse("2:race:1"), MonotonicMs(8_450))


def test_occurrence_and_lineage_are_coherent_or_jointly_null() -> None:
    occurrence = OccurrenceId.parse("3:race:2")
    lineage = LineageId.parse("3:practice:0>3:qualifying:1>3:race:2")

    assert validate_occurrence_lineage(occurrence, lineage) == (occurrence, lineage)
    assert validate_occurrence_lineage(None, None, allow_stream_scope=True) == (None, None)
    with pytest.raises(ContractViolation):
        validate_occurrence_lineage(occurrence, None)
    with pytest.raises(ContractViolation):
        validate_occurrence_lineage(None, None)
    with pytest.raises(ContractViolation):
        validate_occurrence_lineage(
            OccurrenceId.parse("3:qualifying:2"),
            lineage,
        )


@pytest.mark.parametrize(
    ("scalar_type", "value"),
    [
        (ScalarType.BOOLEAN, True),
        (ScalarType.ID, "car:17"),
        (ScalarType.TEXT, "Driver seventeen"),
        (ScalarType.SECONDS, -0.25),
        (ScalarType.SECONDS_PER_SECOND, -0.12),
        (ScalarType.FRACTION, 0.75),
        (ScalarType.COUNT, 0),
        (ScalarType.SIGNED_COUNT, -2),
        (ScalarType.ORDINAL, 1),
        (ScalarType.LAP_NUMBER, 0),
        (ScalarType.CELSIUS, 23.5),
        (ScalarType.METERS_PER_SECOND, 0.0),
        (ScalarType.BEATS_PER_MINUTE, 120),
        (ScalarType.STAGE, "race"),
        (ScalarType.FACT_QUALITY, "measured"),
    ],
)
def test_registered_scalar_units_accept_valid_values(
    scalar_type: ScalarType, value: object
) -> None:
    assert validate_scalar(scalar_type, value) == value


@pytest.mark.parametrize(
    ("scalar_type", "value"),
    [
        ("laps", 1),
        (ScalarType.BOOLEAN, 1),
        (ScalarType.SECONDS, float("nan")),
        (ScalarType.FRACTION, 1.01),
        (ScalarType.COUNT, -1),
        (ScalarType.ORDINAL, 0),
        (ScalarType.METERS_PER_SECOND, -0.1),
        (ScalarType.BEATS_PER_MINUTE, 261),
        (ScalarType.STAGE, "warmup"),
        (ScalarType.FACT_QUALITY, "fresh"),
        (ScalarType.TEXT, " stale "),
    ],
)
def test_invalid_or_unknown_scalar_units_fail(scalar_type: ScalarType | str, value: object) -> None:
    with pytest.raises(ContractViolation):
        validate_scalar(scalar_type, value)


def test_unknown_and_stale_are_not_coerced_to_values() -> None:
    assert FactQuality.UNKNOWN.is_active_claim is False
    assert FactQuality.DEGRADED.is_active_claim is True
    with pytest.raises(ContractViolation):
        validate_scalar(ScalarType.SECONDS, None)


def test_confidence_and_half_open_validity_have_one_shared_semantics() -> None:
    assert float(Confidence(0.0)) == 0.0
    assert float(Confidence(1.0)) == 1.0
    window = ValidityWindow(MonotonicMs(100), MonotonicMs(200))

    assert window.is_current(MonotonicMs(100)) is True
    assert window.is_current(MonotonicMs(199)) is True
    assert window.is_current(MonotonicMs(200)) is False
    with pytest.raises(ContractViolation):
        Confidence(float("nan"))
    with pytest.raises(ContractViolation):
        Confidence(1.1)
    with pytest.raises(ContractViolation):
        ValidityWindow(MonotonicMs(100), MonotonicMs(100))


def test_schema_versions_are_closed_and_round_trip() -> None:
    version = SchemaVersion("atomic-fact/2")

    assert str(version) == "atomic-fact/2"
    assert SchemaVersion.parse(str(version)) == version
    with pytest.raises(ContractViolation):
        SchemaVersion("atomic-fact/3")
    with pytest.raises(ContractViolation):
        SchemaVersion("Atomic-Fact/2")


def test_typed_registries_match_the_packaged_machine_registry() -> None:
    registry = json.loads((PACKAGED_SCHEMAS / "freeze-registry.json").read_text())

    assert {item["schemaVersion"] for item in registry["schemaVersions"]} == set(
        SchemaVersion.supported()
    )
    assert {item["id"] for item in registry["scalarTypes"]} == {
        scalar_type.value for scalar_type in ScalarType
    }


def test_canonical_json_and_hash_are_deterministic_and_finite() -> None:
    left = {"z": [3, 2, 1], "a": {"é": True, "n": None}}
    right = {"a": {"n": None, "é": True}, "z": [3, 2, 1]}

    assert canonical_json(left) == canonical_json(right)
    assert canonical_json(left) == '{"a":{"n":null,"é":true},"z":[3,2,1]}'
    assert canonical_sha256(left) == canonical_sha256(right)
    assert canonical_sha256(left).startswith("sha256:")
    with pytest.raises(ContractViolation):
        canonical_json({"bad": float("inf")})
    with pytest.raises(ContractViolation):
        canonical_json({1: "ambiguous key"})
    with pytest.raises(ContractViolation):
        canonical_json({"notJsonArray": (1, 2)})


def test_deterministic_planning_seed_matches_the_frozen_golden() -> None:
    material = PlanningSeedMaterial(
        stream_epoch=StreamEpoch(3),
        opportunity_id=CorrelationId("opp:401"),
        episode_id=CorrelationId("battle-ahead:3:17:22:4"),
        episode_revision=4,
        beat_id=CorrelationId("battle.approach"),
        cycle_attempt_ordinal=CycleAttemptOrdinal(1),
    )

    assert material.to_dict() == {
        "streamEpoch": 3,
        "opportunityId": "opp:401",
        "episodeId": "battle-ahead:3:17:22:4",
        "episodeRevision": 4,
        "beatId": "battle.approach",
        "cycleAttemptOrdinal": 1,
    }
    assert deterministic_planning_seed(material) == 16041955996680716084
    assert PlanningSeedMaterial.from_dict(material.to_dict()) == material


def test_planning_seed_material_preserves_null_and_attempt_bounds() -> None:
    material = PlanningSeedMaterial(
        stream_epoch=StreamEpoch(1),
        opportunity_id=None,
        episode_id=CorrelationId("episode:1"),
        episode_revision=0,
        beat_id=CorrelationId("session.open"),
        cycle_attempt_ordinal=CycleAttemptOrdinal(2),
    )

    assert material.to_dict()["opportunityId"] is None
    assert 0 <= deterministic_planning_seed(material) <= 2**64 - 1
    with pytest.raises(ContractViolation):
        CycleAttemptOrdinal(0)
    with pytest.raises(ContractViolation):
        CycleAttemptOrdinal(3)


def test_v4_golden_hash_uses_the_shared_canonical_hash() -> None:
    golden = json.loads((FROZEN_MACHINE / "v4-event-envelope.golden.json").read_text())

    assert canonical_sha256(golden["eventEnvelope"]) == golden["canonicalSha256"]


@pytest.mark.parametrize("name", ["freeze-registry.json", "dto-contracts.schema.json"])
def test_packaged_contract_artifacts_are_byte_equivalent(name: str) -> None:
    assert (PACKAGED_SCHEMAS / name).read_bytes() == (FROZEN_MACHINE / name).read_bytes()
