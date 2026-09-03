"""Thread-safe editorial lifecycle between live events, LLM polish and TTS."""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from irswitch.events.envelope import EventEnvelope

_POSITION_EVENTS = frozenset({"POSITION_GAINED", "POSITION_LOST"})


class MiniStoryState(StrEnum):
    READY = "ready"
    RESOLVED = "resolved"
    COMMITTED = "committed"
    SPEAKING = "speaking"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    INTERRUPTED = "interrupted"


class CommitStatus(StrEnum):
    UNCHANGED = "unchanged"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class MiniStoryToken:
    story_id: str
    revision: int
    run_epoch: int
    hero_order_revision: int
    correlation_id: str
    event_type: str

    def to_dict(self, *, state: MiniStoryState | str) -> dict[str, Any]:
        return {
            "storyId": self.story_id,
            "storyRevision": self.revision,
            "runEpoch": self.run_epoch,
            "heroOrderRevision": self.hero_order_revision,
            "correlationId": self.correlation_id,
            "eventType": self.event_type,
            "state": str(state),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MiniStoryToken:
        return cls(
            story_id=str(payload.get("storyId") or ""),
            revision=max(1, _integer(payload.get("storyRevision")) or 1),
            run_epoch=max(0, _integer(payload.get("runEpoch")) or 0),
            hero_order_revision=max(0, _integer(payload.get("heroOrderRevision")) or 0),
            correlation_id=str(payload.get("correlationId") or ""),
            event_type=str(payload.get("eventType") or ""),
        )


@dataclass(frozen=True)
class MiniStoryObservation:
    token: MiniStoryToken | None
    narrate: bool = True
    state: MiniStoryState | None = None

    def to_dict(self) -> dict[str, Any] | None:
        if self.token is None or self.state is None:
            return None
        return self.token.to_dict(state=self.state)


@dataclass(frozen=True)
class CommitDecision:
    status: CommitStatus
    canonical: str = ""
    fact_pack: dict[str, Any] | None = None


@dataclass
class _MiniStory:
    story_id: str
    correlation_id: str
    event_type: str
    run_epoch: int
    hero_order_revision: int
    revision: int
    identity: tuple[object, ...]
    metrics: dict[str, Any]
    state: MiniStoryState = MiniStoryState.READY
    resolved_after_commit: bool = False


@dataclass
class MiniStoryRegistry:
    """Owns live story truth while Qwen and TTS run on another thread."""

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _stories: dict[str, _MiniStory] = field(default_factory=dict, repr=False)
    _session_id: str = ""
    _run_epoch: int = 0
    _hero_position: int | None = None
    _hero_order_revision: int = 0
    _next_story: int = 0
    _active_story_id: str | None = None

    @property
    def hero_order_revision(self) -> int:
        with self._lock:
            return self._hero_order_revision

    def reset(self, *, session_id: str = "", run_epoch: int = 0) -> None:
        with self._lock:
            for story in self._stories.values():
                if story.state not in {MiniStoryState.COMPLETED, MiniStoryState.INTERRUPTED}:
                    story.state = MiniStoryState.INVALIDATED
            self._stories.clear()
            self._session_id = session_id
            self._run_epoch = max(0, int(run_epoch))
            self._hero_position = None
            self._hero_order_revision = 0
            self._active_story_id = None

    def adopt(self, envelope: EventEnvelope, payload: dict[str, Any]) -> MiniStoryToken | None:
        """Restore producer-assigned identity when consuming a frozen/replayed event."""
        token = MiniStoryToken.from_dict(payload)
        if not token.story_id or not token.correlation_id:
            return None
        try:
            state = MiniStoryState(str(payload.get("state") or MiniStoryState.READY))
        except ValueError:
            state = MiniStoryState.READY
        with self._lock:
            existing = self._story_for_token(token)
            if existing is not None:
                existing.metrics.update(deepcopy(envelope.metrics))
                if state == MiniStoryState.RESOLVED:
                    if existing.state in {MiniStoryState.COMMITTED, MiniStoryState.SPEAKING}:
                        existing.resolved_after_commit = True
                    elif (
                        existing.state
                        not in {
                            MiniStoryState.COMPLETED,
                            MiniStoryState.INVALIDATED,
                            MiniStoryState.INTERRUPTED,
                        }
                        and token.revision >= existing.revision
                    ):
                        existing.state = MiniStoryState.RESOLVED
                        existing.revision = token.revision
                return _token(existing)
            story = _MiniStory(
                story_id=token.story_id,
                correlation_id=token.correlation_id,
                event_type=token.event_type or envelope.event_type,
                run_epoch=token.run_epoch,
                hero_order_revision=token.hero_order_revision,
                revision=token.revision,
                identity=_identity(envelope),
                metrics=deepcopy(envelope.metrics),
                state=state,
            )
            self._stories[_story_key(envelope)] = story
            self._run_epoch = max(self._run_epoch, token.run_epoch)
            self._hero_order_revision = max(self._hero_order_revision, token.hero_order_revision)
            try:
                self._next_story = max(self._next_story, int(token.story_id.rsplit(":", 1)[-1]))
            except (TypeError, ValueError):
                pass
            return _token(story)

    def observe_context(self, context: dict[str, Any]) -> bool:
        """Return True only for an authoritative hero class-position change."""
        identity = context.get("identity")
        identity = identity if isinstance(identity, dict) else {}
        race = context.get("race")
        race = race if isinstance(race, dict) else {}
        session_id = str(context.get("session_id") or "")
        run_epoch = _integer(identity.get("run_epoch")) or _integer(race.get("run_epoch")) or 0
        position = _positive_integer(race.get("class_position"))
        with self._lock:
            if session_id and self._session_id and session_id != self._session_id:
                self.reset(session_id=session_id, run_epoch=run_epoch)
            elif run_epoch != self._run_epoch:
                self.reset(session_id=session_id or self._session_id, run_epoch=run_epoch)
            else:
                self._session_id = session_id or self._session_id
            changed = (
                position is not None
                and self._hero_position is not None
                and position != self._hero_position
            )
            if position is not None:
                self._hero_position = position
            if changed:
                self._hero_order_revision += 1
                self._invalidate_for_order_change()
            return changed

    def observe(self, envelope: EventEnvelope) -> MiniStoryObservation:
        """Update the fact ledger and issue a token for a narratable revision."""
        key = _story_key(envelope)
        run_epoch = _integer(envelope.metrics.get("runEpoch")) or self._run_epoch
        identity = _identity(envelope)
        with self._lock:
            if envelope.event_type in _POSITION_EVENTS and envelope.phase in {"ENTER", "RESULT"}:
                new_position = _positive_integer(
                    envelope.metrics.get("classPosition") or envelope.metrics.get("position")
                )
                if new_position is not None and new_position != self._hero_position:
                    self._hero_position = new_position
                    self._hero_order_revision += 1
                    self._invalidate_for_order_change()
            story = self._stories.get(key)
            if envelope.phase == "EXIT" and story is not None:
                if story.run_epoch != run_epoch or _identity_conflicts(story.identity, identity):
                    return MiniStoryObservation(None, narrate=False)
                story.metrics.update(deepcopy(envelope.metrics))
                if story.state in {MiniStoryState.COMMITTED, MiniStoryState.SPEAKING}:
                    story.resolved_after_commit = True
                elif story.state not in {
                    MiniStoryState.COMPLETED,
                    MiniStoryState.INVALIDATED,
                    MiniStoryState.INTERRUPTED,
                }:
                    story.state = MiniStoryState.RESOLVED
                    story.revision += 1
                # The editorial lease may remain SPEAKING internally, while the
                # presentation must still move to its resolved/result state.
                return MiniStoryObservation(
                    _token(story), narrate=False, state=MiniStoryState.RESOLVED
                )

            if story is not None and (
                story.run_epoch != run_epoch or _identity_conflicts(story.identity, identity)
            ):
                if story.state not in {MiniStoryState.COMPLETED, MiniStoryState.INTERRUPTED}:
                    story.state = MiniStoryState.INVALIDATED
                story = None

            if story is not None and story.state in {
                MiniStoryState.COMPLETED,
                MiniStoryState.INVALIDATED,
                MiniStoryState.INTERRUPTED,
            }:
                story = None

            if story is None:
                self._next_story += 1
                story = _MiniStory(
                    story_id=f"story:{run_epoch}:{self._next_story}",
                    correlation_id=envelope.correlation_id,
                    event_type=envelope.event_type,
                    run_epoch=run_epoch,
                    hero_order_revision=self._hero_order_revision,
                    revision=1,
                    identity=identity,
                    metrics=deepcopy(envelope.metrics),
                )
                self._stories[key] = story
            else:
                # Live metric changes update the ledger without making a still-valid
                # relation draft stale. Semantic resolution/identity changes do.
                story.metrics.update(deepcopy(envelope.metrics))
                story.event_type = envelope.event_type

            token = _token(story)
            return MiniStoryObservation(token, narrate=True, state=story.state)

    def token_for(self, envelope: EventEnvelope) -> MiniStoryToken | None:
        with self._lock:
            story = self._stories.get(_story_key(envelope))
            if story is None:
                return None
            return _token(story)

    def commit(
        self,
        token: MiniStoryToken,
        fact_pack: dict[str, Any] | None,
        *,
        locale: str,
    ) -> CommitDecision:
        """Atomic READY→COMMITTED gate, called after LLM returns."""
        with self._lock:
            story = self._story_for_token(token)
            if story is None or story.state in {
                MiniStoryState.INVALIDATED,
                MiniStoryState.INTERRUPTED,
                MiniStoryState.COMPLETED,
            }:
                return CommitDecision(CommitStatus.INVALIDATED)
            if (
                token.run_epoch != self._run_epoch
                or token.hero_order_revision != self._hero_order_revision
                or story.hero_order_revision != self._hero_order_revision
            ):
                story.state = MiniStoryState.INVALIDATED
                return CommitDecision(CommitStatus.INVALIDATED)
            if story.state == MiniStoryState.RESOLVED:
                story.state = MiniStoryState.COMMITTED
                self._active_story_id = story.story_id
                resolved = _resolved_fact_pack(story, fact_pack, locale=locale)
                return CommitDecision(
                    CommitStatus.RESOLVED,
                    canonical=str(resolved.get("canonical") or ""),
                    fact_pack=resolved,
                )
            if story.revision != token.revision:
                story.state = MiniStoryState.INVALIDATED
                return CommitDecision(CommitStatus.INVALIDATED)
            story.state = MiniStoryState.COMMITTED
            self._active_story_id = story.story_id
            return CommitDecision(CommitStatus.UNCHANGED)

    def mark_speaking(self, token: MiniStoryToken) -> bool:
        with self._lock:
            story = self._story_for_token(token)
            if story is None or story.state != MiniStoryState.COMMITTED:
                return False
            story.state = MiniStoryState.SPEAKING
            return True

    def complete(self, token: MiniStoryToken) -> None:
        with self._lock:
            story = self._story_for_token(token)
            if story is None:
                return
            if story.state not in {MiniStoryState.INTERRUPTED, MiniStoryState.INVALIDATED}:
                story.state = MiniStoryState.COMPLETED
            if self._active_story_id == story.story_id:
                self._active_story_id = None

    def invalidate(self, token: MiniStoryToken, *, interrupted: bool = False) -> bool:
        """Close an unspoken/queued story so presentation cannot be orphaned."""
        with self._lock:
            story = self._story_for_token(token)
            if story is None or story.state in {
                MiniStoryState.COMPLETED,
                MiniStoryState.INTERRUPTED,
                MiniStoryState.INVALIDATED,
            }:
                return False
            story.state = MiniStoryState.INTERRUPTED if interrupted else MiniStoryState.INVALIDATED
            if self._active_story_id == story.story_id:
                self._active_story_id = None
            return True

    def state_of(self, token: MiniStoryToken) -> MiniStoryState | None:
        with self._lock:
            story = self._story_for_token(token)
            return story.state if story is not None else None

    def current_token(self, token: MiniStoryToken) -> MiniStoryToken | None:
        with self._lock:
            story = self._story_for_token(token)
            return _token(story) if story is not None else None

    def _story_for_token(self, token: MiniStoryToken) -> _MiniStory | None:
        return next((s for s in self._stories.values() if s.story_id == token.story_id), None)

    def _invalidate_for_order_change(self) -> None:
        for story in self._stories.values():
            if story.story_id == self._active_story_id and story.state in {
                MiniStoryState.COMMITTED,
                MiniStoryState.SPEAKING,
            }:
                story.state = MiniStoryState.INTERRUPTED
            elif story.state not in {
                MiniStoryState.COMPLETED,
                MiniStoryState.INTERRUPTED,
            }:
                story.state = MiniStoryState.INVALIDATED
        self._active_story_id = None


def _story_key(envelope: EventEnvelope) -> str:
    return envelope.correlation_id or envelope.story_key or envelope.event_id or envelope.event_type


def _identity(envelope: EventEnvelope) -> tuple[object, ...]:
    target = envelope.target.car_id if envelope.target is not None else None
    return (
        envelope.subject.car_id,
        target,
        envelope.metrics.get("targetCarIdx"),
        envelope.metrics.get("frontTargetCarIdx"),
        envelope.metrics.get("rearTargetCarIdx"),
        envelope.metrics.get("direction"),
    )


def _identity_conflicts(stored: tuple[object, ...], incoming: tuple[object, ...]) -> bool:
    return any(
        old is not None and new is not None and old != new
        for old, new in zip(stored, incoming, strict=True)
    )


def _token(story: _MiniStory) -> MiniStoryToken:
    return MiniStoryToken(
        story_id=story.story_id,
        revision=story.revision,
        run_epoch=story.run_epoch,
        hero_order_revision=story.hero_order_revision,
        correlation_id=story.correlation_id,
        event_type=story.event_type,
    )


def _resolved_fact_pack(
    story: _MiniStory,
    fact_pack: dict[str, Any] | None,
    *,
    locale: str,
) -> dict[str, Any]:
    pack = deepcopy(fact_pack) if isinstance(fact_pack, dict) else {}
    micro = pack.get("microplan")
    micro = deepcopy(micro) if isinstance(micro, dict) else {}
    roles = dict(micro.get("actor_roles") or ())
    relation = str(micro.get("relation") or "")
    target = roles.get("target") or roles.get("front") or ""
    cs = locale.lower().startswith("cs")
    if story.event_type == "FINISH" or relation == "session_result":
        canonical = str(
            pack.get("canonical") or ("Jeho závod skončil." if cs else "His race is complete.")
        )
        micro.update(story_state="resolved", canonical=canonical, source_revision=story.revision)
        pack.update(canonical=canonical, microplan=micro)
        return pack
    if relation == "hero_under_pressure":
        canonical = (
            f"Tlak od jezdce {target} pro tuto chvíli polevil."
            if cs and target
            else (
                "Tlak zezadu pro tuto chvíli polevil."
                if cs
                else (
                    f"The pressure from {target} has eased for now."
                    if target
                    else "The pressure from behind has eased for now."
                )
            )
        )
    elif relation == "hero_between_two_fronts":
        canonical = (
            "Souboj na obou frontách se pro tuto chvíli rozpadl."
            if cs
            else "That two-front battle has broken up for now."
        )
    elif relation in {"hero_attacks_target", "hero_closing_on_target"}:
        canonical = (
            f"Útočné okno na jezdce {target} se pro tuto chvíli zavřelo."
            if cs and target
            else (
                "Útočné okno se pro tuto chvíli zavřelo."
                if cs
                else (
                    f"The attacking window on {target} has closed for now."
                    if target
                    else "The attacking window has closed for now."
                )
            )
        )
    else:
        canonical = str(
            pack.get("canonical")
            or (
                "Původní situace už není aktuální."
                if cs
                else "The earlier situation is no longer current."
            )
        )
    micro.update(story_state="resolved", canonical=canonical, source_revision=story.revision)
    forbidden = list(pack.get("forbidden_claims") or ())
    for claim in ("a pass", "a position change", "a crash", "a cause"):
        if claim not in forbidden:
            forbidden.append(claim)
    pack.update(
        version="commentary-facts/3",
        canonical=canonical,
        microplan=micro,
        required_facts=[{"id": "resolution:source_exit", "text": canonical}],
        optional_facts=[],
        forbidden_claims=forbidden,
        style_card={
            "id": "resolved_window",
            "guidance": "State the supplied resolution with concise broadcast cadence.",
            "example": "",
        },
    )
    return pack


def _integer(value: object) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _positive_integer(value: object) -> int | None:
    parsed = _integer(value)
    return parsed if parsed is not None and parsed > 0 else None
