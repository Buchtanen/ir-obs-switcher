"""Spoken-only ExposureStore and base-2 fatigue (v2 issue #263).

Not live-wired and not exported from ``events/__init__.py``. Does not import
commentary, overlay, or the director package. Embeddings are never a fact
or successor gate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from irswitch.contracts.catalog_loader import PolicyProfile, load_narrative_catalog
from irswitch.contracts.primitives import ContractViolation, Identifier, MonotonicMs

SCHEMA_VERSION = "exposure-view/2"
SEMANTIC_HALF_LIFE_MS = 90_000
PATTERN_HALF_LIFE_MS = 180_000
GLOBAL_MIN_INTERVAL_MS = 4_000
LONG_SILENCE_MS = 33_000
EXPOSURE_CAP = 128
CHANNEL_PRESSURE_SCALE = 6.0
CHANNEL_PRESSURE_CAP = 3.0
TAIL_CONTENT_TOKENS = 4
RECORDING_PHASE = "speaking"
EN_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "from",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "as",
        "that",
        "this",
        "it",
        "its",
    }
)


def _id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID")
    return str(Identifier(value))


def _mono(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be monotonic milliseconds")
    return int(MonotonicMs(value))


def half_life_decay(age_ms: int, half_life_ms: int) -> float:
    """Single base-2 half-life: ``0.5 ** (age / half_life)``."""
    if isinstance(age_ms, bool) or not isinstance(age_ms, int):
        raise ContractViolation("age must be monotonic milliseconds")
    if isinstance(half_life_ms, bool) or not isinstance(half_life_ms, int) or half_life_ms <= 0:
        raise ContractViolation("half-life must be a positive millisecond span")
    age = max(0, int(age_ms))
    return float(0.5 ** (age / half_life_ms))


def normalize_tokens(text: str) -> tuple[str, ...]:
    chars: list[str] = []
    for char in str(text).casefold():
        chars.append(char if char.isalnum() or char.isspace() else " ")
    cleaned = " ".join("".join(chars).split())
    if not cleaned:
        return ()
    return tuple(cleaned.split(" "))


def content_tokens(text: str) -> frozenset[str]:
    return frozenset(token for token in normalize_tokens(text) if token not in EN_STOPWORDS)


def lexical_tail(text: str, *, n: int = TAIL_CONTENT_TOKENS) -> tuple[str, ...]:
    tokens = [token for token in normalize_tokens(text) if token not in EN_STOPWORDS]
    width = max(1, int(n))
    return tuple(tokens[-width:])


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union)


@runtime_checkable
class EmbeddingAdapter(Protocol):
    def similarity(self, left: str, right: str) -> float | None:
        """Optional soft similarity. Never a fact or successor gate."""


class NullEmbeddingAdapter:
    def similarity(self, left: str, right: str) -> float | None:
        return None


@dataclass(frozen=True, slots=True)
class ExposureIntent:
    phase: str
    utterance_id: str
    semantic_identity: tuple[str, ...]
    family: str
    pattern: str
    text: str
    tape_channel: str
    policy_id: str
    episode_id: str | None
    beat_role: str | None
    now_ms: int
    source_kind: str = "narrative"


@dataclass(frozen=True, slots=True)
class SpokenExposure:
    utterance_id: str
    semantic_identity: tuple[str, ...]
    family: str
    pattern: str
    text: str
    tape_channel: str
    policy_id: str
    episode_id: str | None
    beat_role: str | None
    accepted_mono_ms: int
    exposure_weight: float
    content_tokens: frozenset[str]
    tail: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FatigueView:
    schema_version: str
    now_ms: int
    semantic_fatigue: float
    pattern_fatigue: float
    lexical_jaccard: float
    lexical_tail_similar: bool
    channel_pressure: float
    event_penalty: float
    embedding_similarity: float | None
    embedding_is_gate: bool = False


@dataclass(frozen=True, slots=True)
class ChannelPressureView:
    schema_version: str
    now_ms: int
    by_channel: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class CadenceAudit:
    families: tuple[str, ...]
    roles: tuple[str, ...]
    filler_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExposureStep:
    reason: str
    record: SpokenExposure | None = None


@dataclass
class ExposureStore:
    """Record playback-accepted speech and expose decaying fatigue views."""

    capacity: int = EXPOSURE_CAP
    embedding: EmbeddingAdapter | None = None
    _rows: list[SpokenExposure] = field(default_factory=list, init=False, repr=False)
    _policies: dict[str, PolicyProfile] = field(default_factory=dict, init=False, repr=False)
    _adapter: EmbeddingAdapter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int):
            raise ContractViolation("capacity must be a positive integer")
        if self.capacity <= 0:
            raise ContractViolation("capacity must be a positive integer")
        catalog = load_narrative_catalog().require_catalog()
        self._policies = {row.id: row for row in catalog.policies}
        self._adapter = self.embedding or NullEmbeddingAdapter()

    @property
    def size(self) -> int:
        return len(self._rows)

    def record(self, intent: ExposureIntent) -> ExposureStep:
        if intent.source_kind == "manual":
            return ExposureStep(reason="ignored_manual")
        if intent.phase != RECORDING_PHASE:
            return ExposureStep(reason="ignored_not_spoken")
        existing = next(
            (row for row in self._rows if row.utterance_id == intent.utterance_id), None
        )
        if existing is not None:
            return ExposureStep(reason="deduped", record=existing)
        record = SpokenExposure(
            utterance_id=_id(intent.utterance_id, "utteranceId"),
            semantic_identity=tuple(
                _id(item, "semanticIdentity") for item in intent.semantic_identity
            ),
            family=_id(intent.family, "family"),
            pattern=_id(intent.pattern, "pattern"),
            text=str(intent.text),
            tape_channel=_id(intent.tape_channel, "tapeChannel"),
            policy_id=_id(intent.policy_id, "policyId"),
            episode_id=None if intent.episode_id is None else _id(intent.episode_id, "episodeId"),
            beat_role=None if intent.beat_role is None else _id(intent.beat_role, "beatRole"),
            accepted_mono_ms=_mono(intent.now_ms, "acceptedMonoMs"),
            exposure_weight=1.0,
            content_tokens=content_tokens(intent.text),
            tail=lexical_tail(intent.text),
        )
        self._rows.append(record)
        self._evict()
        return ExposureStep(reason="recorded", record=record)

    def reset_stream(self, now_ms: int) -> ExposureStep:
        _mono(now_ms, "nowMs")
        self._rows.clear()
        return ExposureStep(reason="reset")

    def query(
        self,
        *,
        semantic_identity: tuple[str, ...],
        pattern: str,
        text: str,
        tape_channel: str,
        policy_id: str,
        now_ms: int,
    ) -> FatigueView:
        now = _mono(now_ms, "nowMs")
        semantic = self._sum_decay(
            now,
            SEMANTIC_HALF_LIFE_MS,
            lambda row: row.semantic_identity == tuple(semantic_identity),
        )
        pattern_fatigue = self._sum_decay(
            now, PATTERN_HALF_LIFE_MS, lambda row: row.pattern == pattern
        )
        tokens = content_tokens(text)
        tail = lexical_tail(text)
        lexical = 0.0
        tail_hit = False
        for row in self._rows:
            lexical = max(lexical, jaccard(tokens, row.content_tokens))
            if tail and tail == row.tail:
                tail_hit = True
        pressure = self._channel_pressure(tape_channel, policy_id, now)
        policy = self._policy(policy_id)
        embedding = self._adapter.similarity(text, self._latest_text())
        return FatigueView(
            schema_version=SCHEMA_VERSION,
            now_ms=now,
            semantic_fatigue=semantic,
            pattern_fatigue=pattern_fatigue,
            lexical_jaccard=lexical,
            lexical_tail_similar=tail_hit,
            channel_pressure=pressure,
            event_penalty=policy.penalty_coefficient * pressure,
            embedding_similarity=embedding,
            embedding_is_gate=False,
        )

    def channel_pressure_view(self, *, now_ms: int) -> ChannelPressureView:
        now = _mono(now_ms, "nowMs")
        channels = sorted({row.tape_channel for row in self._rows})
        items = tuple(
            (channel, self._channel_pressure(channel, self._channel_policy(channel), now))
            for channel in channels
        )
        return ChannelPressureView(schema_version=SCHEMA_VERSION, now_ms=now, by_channel=items)

    def cadence_audit(self) -> CadenceAudit:
        families = tuple(dict.fromkeys(row.family for row in self._rows))
        roles = tuple(
            dict.fromkeys(row.beat_role for row in self._rows if row.beat_role is not None)
        )
        fillers = tuple(
            dict.fromkeys(row.pattern for row in self._rows if row.policy_id == "filler")
        )
        return CadenceAudit(families=families, roles=roles, filler_patterns=fillers)

    def _sum_decay(
        self, now_ms: int, half_life_ms: int, match: Callable[[SpokenExposure], bool]
    ) -> float:
        total = 0.0
        for row in self._rows:
            if not match(row):
                continue
            total += row.exposure_weight * half_life_decay(
                now_ms - row.accepted_mono_ms, half_life_ms
            )
        return total

    def _channel_pressure(self, tape_channel: str, policy_id: str, now_ms: int) -> float:
        half_life = self._cadence_half_life(policy_id)
        total = 0.0
        for row in self._rows:
            if row.tape_channel != tape_channel:
                continue
            total += row.exposure_weight * half_life_decay(now_ms - row.accepted_mono_ms, half_life)
        return CHANNEL_PRESSURE_SCALE * min(CHANNEL_PRESSURE_CAP, total)

    def _cadence_half_life(self, policy_id: str) -> int:
        policy = self._policy(policy_id)
        if policy.id == "filler":
            numeric = LONG_SILENCE_MS
        elif policy.cadence_minimum_ms is None:
            numeric = policy.ttl_ms
        else:
            numeric = policy.cadence_minimum_ms
        return max(GLOBAL_MIN_INTERVAL_MS, numeric)

    def _policy(self, policy_id: str) -> PolicyProfile:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise ContractViolation(f"unknown policy {policy_id}") from exc

    def _channel_policy(self, tape_channel: str) -> str:
        for row in self._rows:
            if row.tape_channel == tape_channel:
                return row.policy_id
        raise ContractViolation(f"no exposure on channel {tape_channel}")

    def _latest_text(self) -> str:
        if not self._rows:
            return ""
        return self._rows[-1].text

    def _evict(self) -> None:
        overflow = len(self._rows) - self.capacity
        if overflow <= 0:
            return
        ranked = sorted(self._rows, key=lambda row: (row.accepted_mono_ms, row.utterance_id))
        drop = {id(row) for row in ranked[:overflow]}
        self._rows = [row for row in self._rows if id(row) not in drop]
