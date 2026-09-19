"""Freshness commit gate immediately before TTS (v2 #265).

Not live-wired and not exported from ``events/__init__.py``. Owns an immutable
commit token and current/stale/invalidated verdict. Does not import commentary
or overlay packages, rebuild surfaces, or dispatch TTS.
"""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.events.opportunity_queue import OpportunityQueue

SCHEMA_VERSION = "commit-token/2"
CURRENT_FACT = frozenset({"active", "provisional"})
LIVE_EPISODES = frozenset({"active"})
VERDICTS = frozenset({"current", "freshness_stale", "invalidated", "not_reached"})


@dataclass(frozen=True, slots=True)
class BoundFactCopy:
    fact_id: str
    predicate: str
    subject_id: str | None
    object_id: str | None
    attributes: tuple[tuple[str, object], ...]
    polarity: str
    revision: int
    status: str
    occurrence_id: str | None
    lineage_id: str | None
    valid_from_mono_ms: int
    valid_until_mono_ms: int | None

    def canonical(self) -> tuple[object, ...]:
        return (
            self.fact_id,
            self.predicate,
            self.subject_id,
            self.object_id,
            self.attributes,
            self.polarity,
            self.revision,
            self.occurrence_id,
            self.lineage_id,
        )

    def is_current(self, now_ms: int) -> bool:
        if self.status not in CURRENT_FACT:
            return False
        if now_ms < self.valid_from_mono_ms:
            return False
        if self.valid_until_mono_ms is None:
            return True
        return now_ms < self.valid_until_mono_ms


@dataclass(frozen=True, slots=True)
class CommitToken:
    schema_version: str
    token_id: str
    plan_id: str
    beat_id: str
    episode_id: str
    episode_revision: int
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    target_identity: tuple[str, ...]
    selected_facts: tuple[BoundFactCopy, ...]
    opportunity_id: str | None
    reservation_token: str | None
    opportunity_material_revision: int | None
    opportunity_expires_mono_ms: int | None
    planned_mono_ms: int
    fact_view_revision: int


@dataclass(frozen=True, slots=True)
class CommitWorld:
    now_ms: int
    lane: str
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    episode_id: str
    episode_revision: int
    episode_state: str
    target_identity: tuple[str, ...]
    facts: tuple[BoundFactCopy, ...]
    fact_view_revision: int
    opportunity_state: str | None
    opportunity_material_revision: int | None
    opportunity_expires_mono_ms: int | None
    reservation_token: str | None
    critical_conflict: bool


@dataclass(frozen=True, slots=True)
class CommitStep:
    reason: str
    verdict: str
    token: CommitToken
    suppressed: bool
    opportunity_effect: str | None
    same_revision_retry: bool
    rebuilt_surfaces: bool
    schema_version: str
    evidence: tuple[str, ...]
    latency_ms: dict[str, int] | None = None


class FreshnessGate:
    """Atomic reducer-turn freshness check. Failure discards that beat revision."""

    def __init__(self, queue: OpportunityQueue | None = None) -> None:
        self.queue = queue
        self.evaluate_count = 0
        self.pass_count = 0
        self.fail_count = 0
        self._suppressed: set[tuple[str, int]] = set()

    def evaluate(self, token: CommitToken, world: CommitWorld) -> CommitStep:
        self.evaluate_count += 1
        key = (token.beat_id, token.episode_revision)
        if key in self._suppressed:
            return self._fail(token, world, "freshness_stale", "suppressed_revision")
        if world.lane != "building":
            return self._step(token, world, "not_reached", ())
        evidence = _identity_failure(token, world)
        if evidence is not None:
            return self._fail(token, world, "invalidated", evidence)
        if token.episode_revision != world.episode_revision:
            return self._fail(token, world, "freshness_stale", "episode_revision")
        if world.critical_conflict:
            return self._fail(token, world, "invalidated", "critical_conflict")
        opportunity = _opportunity_failure(token, world)
        if opportunity is not None:
            return self._fail(token, world, "freshness_stale", opportunity)
        fact = _fact_failure(token, world)
        if fact is not None:
            return self._fail(token, world, "freshness_stale", fact)
        self.pass_count += 1
        return self._step(token, world, "current", ())

    def _fail(
        self, token: CommitToken, world: CommitWorld, verdict: str, evidence: str
    ) -> CommitStep:
        self.fail_count += 1
        self._suppressed.add((token.beat_id, token.episode_revision))
        effect = self._release(token, world)
        return self._step(token, world, verdict, (evidence,), suppressed=True, effect=effect)

    def _release(self, token: CommitToken, world: CommitWorld) -> str | None:
        if self.queue is None or token.reservation_token is None:
            return None
        released = self.queue.reject_attempt(
            token.reservation_token, beat_id=token.beat_id, now_ms=world.now_ms
        )
        return released.reason if released.reason == "attempt_released" else None

    def _step(
        self,
        token: CommitToken,
        world: CommitWorld,
        verdict: str,
        evidence: tuple[str, ...],
        *,
        suppressed: bool = False,
        effect: str | None = None,
    ) -> CommitStep:
        if verdict not in VERDICTS:
            raise ValueError(f"unknown commit verdict: {verdict}")
        latency = world.now_ms - token.planned_mono_ms
        return CommitStep(
            reason=verdict,
            verdict=verdict,
            token=token,
            suppressed=suppressed,
            opportunity_effect=effect,
            same_revision_retry=False,
            rebuilt_surfaces=False,
            schema_version=SCHEMA_VERSION,
            evidence=evidence,
            latency_ms={"plan_to_commit": latency},
        )


def _identity_failure(token: CommitToken, world: CommitWorld) -> str | None:
    if world.stream_epoch != token.stream_epoch:
        return "stream_mismatch"
    if world.occurrence_id != token.occurrence_id:
        return "occurrence_mismatch"
    if world.lineage_id != token.lineage_id:
        return "lineage_mismatch"
    if world.target_identity != token.target_identity:
        return "target_changed"
    if world.episode_id != token.episode_id or world.episode_state not in LIVE_EPISODES:
        return "episode_invalid"
    return None


def _opportunity_failure(token: CommitToken, world: CommitWorld) -> str | None:
    if token.opportunity_id is None:
        return None
    if world.opportunity_state == "superseded":
        return "opportunity_superseded"
    expires = world.opportunity_expires_mono_ms
    if expires is None or not (token.planned_mono_ms <= world.now_ms < expires):
        return "opportunity_expired"
    if world.opportunity_state != "reserved":
        return "reservation_invalid"
    if world.reservation_token != token.reservation_token:
        return "reservation_invalid"
    if world.opportunity_material_revision != token.opportunity_material_revision:
        return "opportunity_superseded"
    return None


def _fact_failure(token: CommitToken, world: CommitWorld) -> str | None:
    live = {item.fact_id: item for item in world.facts}
    for bound in token.selected_facts:
        current = live.get(bound.fact_id)
        if current is None:
            return "fact_missing"
        if current.status not in CURRENT_FACT:
            return "fact_not_current"
        if not current.is_current(world.now_ms):
            return "fact_expired"
        if current.canonical() != bound.canonical():
            return "fact_changed"
    return None
