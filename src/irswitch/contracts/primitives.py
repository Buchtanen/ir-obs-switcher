"""Validated value objects shared by all v2 narrative domains."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Self

MAX_SIGNED_INT64 = 2**63 - 1

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", re.ASCII)
_OCCURRENCE_RE = re.compile(r"([1-9][0-9]*):(practice|qualifying|race):(0|[1-9][0-9]*)", re.ASCII)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class ContractViolation(ValueError):
    """Raised when a value cannot be represented by the frozen v2 contract."""


class Stage(StrEnum):
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    RACE = "race"


class VehiclePhase(StrEnum):
    GARAGE = "garage"
    PIT_LANE = "pit_lane"
    OUT_LAP = "out_lap"
    TIMED_LAP = "timed_lap"
    IN_LAP = "in_lap"
    PARADE_LAP = "parade_lap"
    RACING = "racing"
    UNKNOWN = "unknown"


class BroadcastContext(StrEnum):
    ON_TRACK = "on_track"
    GARAGE = "garage"
    LOBBY = "lobby"
    REPLAY = "replay"
    TRANSITION = "transition"
    UNKNOWN = "unknown"


class FactQuality(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

    @property
    def is_active_claim(self) -> bool:
        """Unknown is audit state, never a current factual claim."""
        return self is not FactQuality.UNKNOWN


class ScalarType(StrEnum):
    """Closed scalar/unit vocabulary from the frozen fact/feature registry."""

    BOOLEAN = "boolean"
    ID = "id"
    TEXT = "text"
    SECONDS = "seconds"
    SECONDS_PER_SECOND = "seconds_per_second"
    FRACTION = "fraction"
    COUNT = "count"
    SIGNED_COUNT = "signed_count"
    ORDINAL = "ordinal"
    LAP_NUMBER = "lap_number"
    CELSIUS = "celsius"
    METERS_PER_SECOND = "meters_per_second"
    BEATS_PER_MINUTE = "beats_per_minute"
    STAGE = "stage"
    VEHICLE_PHASE = "vehicle_phase"
    BROADCAST_CONTEXT = "broadcast_context"
    FACT_QUALITY = "fact_quality"


class _BoundedInt(int):
    minimum: ClassVar[int] = 0
    maximum: ClassVar[int] = MAX_SIGNED_INT64
    contract_name: ClassVar[str] = "integer"

    def __new__(cls, value: int) -> Self:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractViolation(f"{cls.contract_name} must be an integer")
        if not cls.minimum <= value <= cls.maximum:
            raise ContractViolation(f"{cls.contract_name} must be in {cls.minimum}..{cls.maximum}")
        return int.__new__(cls, value)


class BroadcastEpoch(_BoundedInt):
    """Debounced OBS-output epoch; zero means not allocated yet."""

    contract_name = "broadcastEpoch"

    @property
    def is_allocated(self) -> bool:
        return self > 0

    def require_active(self) -> Self:
        if not self.is_allocated:
            raise ContractViolation("active broadcastEpoch must be positive")
        return self


class StreamEpoch(_BoundedInt):
    """Narrative-run epoch; distinct from BroadcastEpoch."""

    contract_name = "streamEpoch"

    @property
    def is_allocated(self) -> bool:
        return self > 0

    def require_active(self) -> Self:
        if not self.is_allocated:
            raise ContractViolation("active streamEpoch must be positive")
        return self


class SourceSequence(_BoundedInt):
    """Positive process-local source publication sequence."""

    minimum = 1
    contract_name = "sourceSequence"


class CycleAttemptOrdinal(_BoundedInt):
    """One of the two bounded planning attempts allowed per director cycle."""

    minimum = 1
    maximum = 2
    contract_name = "cycleAttemptOrdinal"


class MonotonicMs(_BoundedInt):
    """Nonnegative process-local monotonic milliseconds."""

    contract_name = "monotonic milliseconds"


class Confidence(float):
    """Finite evidence confidence in the inclusive range 0..1."""

    def __new__(cls, value: float) -> Self:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContractViolation("confidence must be a finite number")
        normalized = float(value)
        if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
            raise ContractViolation("confidence must be in 0..1")
        return float.__new__(cls, normalized)


class _AsciiId(str):
    contract_name: ClassVar[str] = "ID"

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
            raise ContractViolation(
                f"{cls.contract_name} must match {_ID_RE.pattern!r} using ASCII characters"
            )
        return str.__new__(cls, value)


class Identifier(_AsciiId):
    """Generic frozen ASCII identifier used by versioned DTO fields."""


class CorrelationId(Identifier):
    contract_name = "correlationId"


class ProcessInstanceId(_AsciiId):
    contract_name = "processInstanceId"


_SCHEMA_VERSIONS = frozenset(
    {
        "1.0",
        "narrative-command/2",
        "narrative-event/2",
        "feature-frame/2",
        "detector-observation/2",
        "event-candidate-tap/2",
        "timeline-snapshot/2",
        "session-plan/2",
        "atomic-fact/2",
        "fact-view/2",
        "episode/2",
        "event-opportunity/2",
        "beat-plan/2",
        "prompt-options/2",
        "realization-bundle/2",
        "compiled-prompt/2",
        "realization-request/2",
        "realization-result/2",
        "llm-attempt/2",
        "tts-utterance/2",
        "tts-callback/2",
        "speech-exposure/2",
        "narrative-catalog/2",
        "narrative-tape-manifest/2",
        "narrative-tape-record/2",
        "commentary-runtime/2",
        "commentary-config/2",
    }
)


class SchemaVersion(str):
    """One of the explicitly frozen wire/schema versions."""

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or value not in _SCHEMA_VERSIONS:
            raise ContractViolation(f"unknown schemaVersion: {value!r}")
        return str.__new__(cls, value)

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(value)

    @classmethod
    def supported(cls) -> frozenset[str]:
        """Return the complete immutable version registry."""
        return _SCHEMA_VERSIONS


class Sha256Hash(str):
    """Canonical lower-case SHA-256 field representation."""

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ContractViolation("hash must be 'sha256:' plus 64 lower-case hexadecimal digits")
        return str.__new__(cls, value)


@dataclass(frozen=True, slots=True, init=False)
class PlanningSeedMaterial:
    """Exact lower-camel identity object used for deterministic prompt seeds."""

    stream_epoch: StreamEpoch
    opportunity_id: Identifier | None
    episode_id: Identifier
    episode_revision: int
    beat_id: Identifier
    cycle_attempt_ordinal: CycleAttemptOrdinal

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "streamEpoch",
            "opportunityId",
            "episodeId",
            "episodeRevision",
            "beatId",
            "cycleAttemptOrdinal",
        }
    )

    def __init__(
        self,
        *,
        stream_epoch: StreamEpoch | int,
        opportunity_id: Identifier | str | None,
        episode_id: Identifier | str,
        episode_revision: int,
        beat_id: Identifier | str,
        cycle_attempt_ordinal: CycleAttemptOrdinal | int,
    ) -> None:
        if (
            isinstance(episode_revision, bool)
            or not isinstance(episode_revision, int)
            or not 0 <= episode_revision <= MAX_SIGNED_INT64
        ):
            raise ContractViolation("episodeRevision must be a nonnegative signed 64-bit integer")
        object.__setattr__(self, "stream_epoch", StreamEpoch(stream_epoch).require_active())
        object.__setattr__(
            self,
            "opportunity_id",
            None if opportunity_id is None else Identifier(opportunity_id),
        )
        object.__setattr__(self, "episode_id", Identifier(episode_id))
        object.__setattr__(self, "episode_revision", episode_revision)
        object.__setattr__(self, "beat_id", Identifier(beat_id))
        object.__setattr__(
            self, "cycle_attempt_ordinal", CycleAttemptOrdinal(cycle_attempt_ordinal)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "streamEpoch": int(self.stream_epoch),
            "opportunityId": (None if self.opportunity_id is None else str(self.opportunity_id)),
            "episodeId": str(self.episode_id),
            "episodeRevision": self.episode_revision,
            "beatId": str(self.beat_id),
            "cycleAttemptOrdinal": int(self.cycle_attempt_ordinal),
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict) or frozenset(value) != cls._FIELDS:
            raise ContractViolation("planning seed material has invalid fields")
        return cls(
            stream_epoch=value["streamEpoch"],
            opportunity_id=value["opportunityId"],
            episode_id=value["episodeId"],
            episode_revision=value["episodeRevision"],
            beat_id=value["beatId"],
            cycle_attempt_ordinal=value["cycleAttemptOrdinal"],
        )


@dataclass(frozen=True, slots=True)
class OccurrenceId:
    stream_epoch: StreamEpoch
    stage: Stage
    ordinal: int

    def __post_init__(self) -> None:
        epoch = StreamEpoch(self.stream_epoch).require_active()
        try:
            stage = Stage(self.stage)
        except (TypeError, ValueError) as exc:
            raise ContractViolation(f"invalid occurrence stage: {self.stage!r}") from exc
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ContractViolation("occurrence ordinal must be a nonnegative integer")
        if self.ordinal > MAX_SIGNED_INT64:
            raise ContractViolation(f"occurrence ordinal must not exceed {MAX_SIGNED_INT64}")
        object.__setattr__(self, "stream_epoch", epoch)
        object.__setattr__(self, "stage", stage)

    @classmethod
    def parse(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise ContractViolation("occurrenceId must be a string")
        match = _OCCURRENCE_RE.fullmatch(value)
        if match is None:
            raise ContractViolation("invalid canonical occurrenceId")
        return cls(StreamEpoch(int(match.group(1))), Stage(match.group(2)), int(match.group(3)))

    def __str__(self) -> str:
        return f"{int(self.stream_epoch)}:{self.stage.value}:{self.ordinal}"


_STAGE_ORDER = {Stage.PRACTICE: 0, Stage.QUALIFYING: 1, Stage.RACE: 2}


@dataclass(frozen=True, slots=True)
class LineageId:
    occurrences: tuple[OccurrenceId, ...]

    def __post_init__(self) -> None:
        occurrences = tuple(self.occurrences)
        if not 1 <= len(occurrences) <= 3:
            raise ContractViolation("lineageId must contain one to three occurrences")
        epochs = {item.stream_epoch for item in occurrences}
        if len(epochs) != 1:
            raise ContractViolation("lineageId occurrences must share one streamEpoch")
        order = [_STAGE_ORDER[item.stage] for item in occurrences]
        if order != sorted(set(order)):
            raise ContractViolation("lineageId occurrences must use unique canonical stage order")
        object.__setattr__(self, "occurrences", occurrences)

    @classmethod
    def parse(cls, value: str) -> Self:
        if not isinstance(value, str) or not value:
            raise ContractViolation("lineageId must be a nonempty string")
        try:
            return cls(tuple(OccurrenceId.parse(item) for item in value.split(">")))
        except ContractViolation as exc:
            raise ContractViolation(f"invalid canonical lineageId: {value!r}") from exc

    def __str__(self) -> str:
        return ">".join(str(item) for item in self.occurrences)


def validate_occurrence_lineage(
    occurrence_id: OccurrenceId | None,
    lineage_id: LineageId | None,
    *,
    allow_stream_scope: bool = False,
) -> tuple[OccurrenceId | None, LineageId | None]:
    """Require a coherent pair, allowing joint null only for registered stream scope."""

    if occurrence_id is None or lineage_id is None:
        if occurrence_id is not None or lineage_id is not None:
            raise ContractViolation("occurrenceId and lineageId must be jointly present or null")
        if not allow_stream_scope:
            raise ContractViolation("occurrenceId and lineageId are required outside stream scope")
        return None, None
    if lineage_id.occurrences[-1] != occurrence_id:
        raise ContractViolation("occurrenceId must be the active tail of lineageId")
    return occurrence_id, lineage_id


@dataclass(frozen=True, slots=True, init=False)
class ProcessMonotonicTime:
    """A monotonic timestamp tagged with the only process where it is comparable."""

    process_instance_id: ProcessInstanceId
    value_ms: MonotonicMs

    def __init__(
        self, process_instance_id: ProcessInstanceId | str, value_ms: MonotonicMs | int
    ) -> None:
        object.__setattr__(self, "process_instance_id", ProcessInstanceId(process_instance_id))
        object.__setattr__(self, "value_ms", MonotonicMs(value_ms))

    def elapsed_since(self, earlier: ProcessMonotonicTime) -> int:
        if self.process_instance_id != earlier.process_instance_id:
            raise ContractViolation("monotonic times from different processes are incomparable")
        elapsed = int(self.value_ms) - int(earlier.value_ms)
        if elapsed < 0:
            raise ContractViolation("monotonic time cannot move backwards")
        return elapsed


@dataclass(frozen=True, slots=True, init=False)
class StreamClock:
    """A monotonic origin scoped to one process and narrative run."""

    process_instance_id: ProcessInstanceId
    stream_epoch: StreamEpoch
    origin_ms: MonotonicMs

    def __init__(
        self,
        process_instance_id: ProcessInstanceId | str,
        stream_epoch: StreamEpoch | int,
        origin_ms: MonotonicMs | int,
    ) -> None:
        object.__setattr__(self, "process_instance_id", ProcessInstanceId(process_instance_id))
        object.__setattr__(self, "stream_epoch", StreamEpoch(stream_epoch).require_active())
        object.__setattr__(self, "origin_ms", MonotonicMs(origin_ms))

    def elapsed_at(
        self,
        process_instance_id: ProcessInstanceId | str,
        stream_epoch: StreamEpoch | int,
        now_ms: MonotonicMs | int,
    ) -> int:
        if ProcessInstanceId(process_instance_id) != self.process_instance_id:
            raise ContractViolation("stream clocks from different processes are incomparable")
        if StreamEpoch(stream_epoch) != self.stream_epoch:
            raise ContractViolation("stream clocks from different narrative runs are incomparable")
        return _elapsed(self.origin_ms, MonotonicMs(now_ms), "stream")


@dataclass(frozen=True, slots=True, init=False)
class SessionClock:
    """A monotonic origin scoped to one process and session occurrence."""

    process_instance_id: ProcessInstanceId
    occurrence_id: OccurrenceId
    origin_ms: MonotonicMs

    def __init__(
        self,
        process_instance_id: ProcessInstanceId | str,
        occurrence_id: OccurrenceId,
        origin_ms: MonotonicMs | int,
    ) -> None:
        if not isinstance(occurrence_id, OccurrenceId):
            raise ContractViolation("session clock requires an OccurrenceId")
        object.__setattr__(self, "process_instance_id", ProcessInstanceId(process_instance_id))
        object.__setattr__(self, "occurrence_id", occurrence_id)
        object.__setattr__(self, "origin_ms", MonotonicMs(origin_ms))

    def elapsed_at(
        self,
        process_instance_id: ProcessInstanceId | str,
        occurrence_id: OccurrenceId,
        now_ms: MonotonicMs | int,
    ) -> int:
        if ProcessInstanceId(process_instance_id) != self.process_instance_id:
            raise ContractViolation("session clocks from different processes are incomparable")
        if occurrence_id != self.occurrence_id:
            raise ContractViolation("session clocks from different occurrences are incomparable")
        return _elapsed(self.origin_ms, MonotonicMs(now_ms), "session")


def _elapsed(origin_ms: MonotonicMs, now_ms: MonotonicMs, scope: str) -> int:
    elapsed = int(now_ms) - int(origin_ms)
    if elapsed < 0:
        raise ContractViolation(f"{scope} monotonic time cannot move backwards")
    return elapsed


@dataclass(frozen=True, slots=True)
class ValidityWindow:
    """Shared half-open monotonic validity interval."""

    observed_ms: MonotonicMs
    valid_until_ms: MonotonicMs | None = None

    def __post_init__(self) -> None:
        observed = MonotonicMs(self.observed_ms)
        valid_until = None if self.valid_until_ms is None else MonotonicMs(self.valid_until_ms)
        if valid_until is not None and valid_until <= observed:
            raise ContractViolation("validUntilMonoMs must be later than observedMonoMs")
        object.__setattr__(self, "observed_ms", observed)
        object.__setattr__(self, "valid_until_ms", valid_until)

    def is_current(self, now_ms: MonotonicMs | int) -> bool:
        now = MonotonicMs(now_ms)
        return now >= self.observed_ms and (
            self.valid_until_ms is None or now < self.valid_until_ms
        )


def _finite_float(value: object, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, float) or not math.isfinite(value):
        raise ContractViolation(f"{name} must be a finite float")
    if minimum is not None and value < minimum:
        raise ContractViolation(f"{name} must be at least {minimum}")
    return value


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ContractViolation(f"{name} must be at least {minimum}")
    if not -MAX_SIGNED_INT64 - 1 <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{name} must fit a signed 64-bit integer")
    return value


def _enum_value(enum_type: type[StrEnum], value: object, name: str) -> object:
    if not isinstance(value, str):
        raise ContractViolation(f"invalid {name}: {value!r}")
    try:
        enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ContractViolation(f"invalid {name}: {value!r}") from exc
    return value


def validate_scalar(scalar_type: ScalarType | str, value: object) -> object:
    """Validate a value against the closed v2 scalar/unit registry.

    Missing, stale and otherwise unknown inputs are represented by absence at
    their owner boundary. ``None`` is therefore never silently converted into
    zero, false or an empty value here.
    """

    try:
        kind = ScalarType(scalar_type)
    except (TypeError, ValueError) as exc:
        raise ContractViolation(f"unknown scalar/unit: {scalar_type!r}") from exc
    if value is None:
        raise ContractViolation(f"{kind.value} has no active value")
    if kind is ScalarType.BOOLEAN:
        if not isinstance(value, bool):
            raise ContractViolation("boolean must be a JSON boolean")
        return value
    if kind is ScalarType.ID:
        if not isinstance(value, str):
            raise ContractViolation("id must be an ASCII string")
        return str(_AsciiId(value))
    if kind is ScalarType.TEXT:
        if not isinstance(value, str) or not 1 <= len(value) <= 160 or value.strip() != value:
            raise ContractViolation("text must be trimmed and contain 1..160 code points")
        if any(unicodedata.category(char) == "Cc" for char in value):
            raise ContractViolation("text must not contain control characters")
        return value
    if kind in {ScalarType.SECONDS, ScalarType.SECONDS_PER_SECOND, ScalarType.CELSIUS}:
        return _finite_float(value, kind.value)
    if kind is ScalarType.FRACTION:
        number = _finite_float(value, kind.value, minimum=0.0)
        if number > 1.0:
            raise ContractViolation("fraction must not exceed 1")
        return number
    if kind is ScalarType.METERS_PER_SECOND:
        return _finite_float(value, kind.value, minimum=0.0)
    if kind in {ScalarType.COUNT, ScalarType.LAP_NUMBER}:
        return _integer(value, kind.value, minimum=0)
    if kind is ScalarType.SIGNED_COUNT:
        return _integer(value, kind.value)
    if kind is ScalarType.ORDINAL:
        return _integer(value, kind.value, minimum=1)
    if kind is ScalarType.BEATS_PER_MINUTE:
        integer = _integer(value, kind.value, minimum=20)
        if integer > 260:
            raise ContractViolation("beats_per_minute must not exceed 260")
        return integer
    enum_types: dict[ScalarType, type[StrEnum]] = {
        ScalarType.STAGE: Stage,
        ScalarType.VEHICLE_PHASE: VehiclePhase,
        ScalarType.BROADCAST_CONTEXT: BroadcastContext,
        ScalarType.FACT_QUALITY: FactQuality,
    }
    return _enum_value(enum_types[kind], value, kind.value)


def _validate_json_value(value: object, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractViolation(f"{path} is not finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractViolation(f"{path} contains a non-string object key")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ContractViolation(f"{path} is not a JSON value")


def canonical_json(value: Any) -> str:
    """Return canonical UTF-8 JSON text with recursively sorted object keys."""

    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractViolation("value is not finite canonical JSON") from exc


def canonical_sha256(value: Any) -> Sha256Hash:
    """Hash canonical UTF-8 JSON using the frozen v2 field representation."""

    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return Sha256Hash(f"sha256:{digest}")


def deterministic_planning_seed(material: PlanningSeedMaterial) -> int:
    """Return the frozen unsigned big-endian seed from the first eight SHA-256 bytes."""

    if not isinstance(material, PlanningSeedMaterial):
        raise ContractViolation("planning seed requires PlanningSeedMaterial")
    digest = hashlib.sha256(canonical_json(material.to_dict()).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")
