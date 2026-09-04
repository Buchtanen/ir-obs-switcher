"""Bounded deterministic atomic FSM kernel; no IO, narration, or event publication.

Bindings are reviewed pure Python functions. Loading a JSON name does not bind
an implementation: construction fails until every guard/action is supplied.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from irswitch.events.scenarios.model import (
    EpisodeScope,
    GuardResult,
    ScenarioBeat,
    ScenarioDefinition,
    ScenarioTransition,
    freeze_mapping,
)


@dataclass(frozen=True)
class ScenarioFrame:
    now: float
    scope: EpisodeScope
    mode: str
    connected: bool
    observations: Mapping[str, object]

    def __post_init__(self) -> None:
        if not math.isfinite(self.now) or self.now < 0:
            raise ValueError("frame time must be finite and non-negative")
        object.__setattr__(self, "observations", freeze_mapping(self.observations))


@dataclass(frozen=True)
class EpisodeMemory:
    state: str
    entered_at: float
    episode_id: str = ""
    episode_started_at: float | None = None
    facts: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", freeze_mapping(self.facts))


@dataclass(frozen=True)
class ActionEffect:
    """Facts replace episode memory when provided; beats commit with the transition."""

    facts: Mapping[str, object] | None = None
    beats: tuple[ScenarioBeat, ...] = ()

    def __post_init__(self) -> None:
        if self.facts is not None:
            object.__setattr__(self, "facts", freeze_mapping(self.facts))
        object.__setattr__(self, "beats", tuple(self.beats))


@dataclass(frozen=True)
class ScenarioTrace:
    at: float
    transition_id: str
    state: str
    target: str
    reason: str
    episode_id: str = ""


GuardFn = Callable[
    [ScenarioFrame, EpisodeMemory, ScenarioDefinition, ScenarioTransition], GuardResult
]
ActionFn = Callable[
    [ScenarioFrame, EpisodeMemory, ScenarioDefinition, ScenarioTransition], ActionEffect
]


class ScenarioEngine:
    """One atomic scenario instance. Composite regions will own separate instances.

    All transitions are scanned once in declared order per tick. This permits
    declared same-tick chains without loops. Action failure discards the entire
    tick and quarantines this instance until its identity scope changes.
    """

    def __init__(
        self,
        definition: ScenarioDefinition,
        *,
        guards: Mapping[str, GuardFn],
        actions: Mapping[str, ActionFn],
        max_trace_records: int = 128,
        max_transitions: int = 64,
        max_facts: int = 64,
        max_beats_per_tick: int = 16,
    ) -> None:
        if any(
            value < 1
            for value in (max_trace_records, max_transitions, max_facts, max_beats_per_tick)
        ):
            raise ValueError("scenario capacities must be positive")
        if len(definition.transitions) > max_transitions:
            raise ValueError("scenario transition capacity exceeded")
        needed_guards = {item.guard for item in definition.transitions}
        needed_actions = {action for item in definition.transitions for action in item.actions}
        missing = (needed_guards - guards.keys()) | (
            needed_actions - actions.keys() - {"create_episode"}
        )
        if missing:
            raise ValueError(f"unbound scenario handlers: {sorted(missing)}")
        self.definition = definition
        self.guards = MappingProxyType(dict(guards))
        self.actions = MappingProxyType(dict(actions))
        self.max_facts = max_facts
        self.max_beats_per_tick = max_beats_per_tick
        self._trace: deque[ScenarioTrace] = deque(maxlen=max_trace_records)
        self._terminal_states = {state.id for state in definition.states if state.terminal}
        self._scope: EpisodeScope | None = None
        self._last_now: float | None = None
        self._disconnected_since: float | None = None
        self._holds: dict[str, float] = {}
        self._sequence = 0
        self._disabled = False
        self._memory = EpisodeMemory(definition.initial_state, 0.0)

    @property
    def memory(self) -> EpisodeMemory:
        return self._memory

    @property
    def traces(self) -> tuple[ScenarioTrace, ...]:
        return tuple(self._trace)

    @property
    def disabled(self) -> bool:
        return self._disabled

    def tick(self, frame: ScenarioFrame) -> tuple[ScenarioBeat, ...]:
        if frame.scope.scenario_id != self.definition.scenario_id:
            return ()
        if frame.scope != self._scope:
            self._reset_scope(frame)
        if self._disabled or (self._last_now is not None and frame.now <= self._last_now):
            return ()
        self._last_now = frame.now
        if self.definition.requires_connected and not frame.connected:
            if self._disconnected_since is None:
                self._disconnected_since = frame.now
            self._holds.clear()
            if frame.now - self._disconnected_since >= self._disconnect_grace():
                self._invalidate(frame.now, "disconnect_grace_exceeded")
            return ()
        if self._disconnected_since is not None:
            if frame.now - self._disconnected_since >= self._disconnect_grace():
                self._invalidate(frame.now, "disconnect_grace_exceeded")
            self._disconnected_since = None
        if frame.mode not in self.definition.scope_modes:
            # No hold may bridge a disconnected or out-of-scope observation.
            self._holds.clear()
            return ()
        if self._memory.state in self._terminal_states:
            policy = self.definition.document.get("terminalPolicy")
            if not isinstance(policy, Mapping):
                return ()
            retain = policy.get("retainForS")
            if not isinstance(retain, (int, float)) or frame.now < self._memory.entered_at + retain:
                return ()
            self._invalidate(frame.now, "terminal_retention_elapsed")
        memory, sequence = self._memory, self._sequence
        holds = dict(self._holds)
        traces: list[ScenarioTrace] = []
        beats: list[ScenarioBeat] = []
        try:
            for transition in self.definition.transitions:
                if memory.state not in transition.sources:
                    holds.pop(transition.id, None)
                    continue
                anchor = (
                    memory.entered_at if transition.clock == "state" else memory.episode_started_at
                )
                if anchor is None:
                    continue
                age = frame.now - anchor
                if transition.after_s is not None and age < transition.after_s:
                    continue
                if transition.within_s is not None and age > transition.within_s:
                    holds.pop(transition.id, None)
                    continue
                result = self.guards[transition.guard](frame, memory, self.definition, transition)
                if not isinstance(result, GuardResult):
                    raise ValueError("guard returned an invalid result")
                if not result.matched or result.confidence < transition.enter_confidence:
                    holds.pop(transition.id, None)
                    continue
                since = holds.setdefault(transition.id, frame.now)
                if frame.now < since + transition.hold_s:
                    continue
                previous = memory.state
                for action in transition.actions:
                    if action == "create_episode":
                        if memory.episode_id:
                            raise ValueError("cannot create an episode while one is active")
                        sequence += 1
                        memory = replace(
                            memory,
                            episode_id=frame.scope.episode_id(sequence),
                            episode_started_at=frame.now,
                        )
                        continue
                    effect = self.actions[action](frame, memory, self.definition, transition)
                    if not isinstance(effect, ActionEffect):
                        raise ValueError("action returned an invalid effect")
                    if effect.facts is not None:
                        if len(effect.facts) > self.max_facts:
                            raise ValueError("episode fact capacity exceeded")
                        memory = replace(memory, facts=effect.facts)
                    for beat in effect.beats:
                        self._validate_beat(beat, memory)
                        beats.append(beat)
                    if len(beats) > self.max_beats_per_tick:
                        raise ValueError("beat capacity exceeded")
                if transition.target != "SAME":
                    memory = replace(memory, state=transition.target, entered_at=frame.now)
                    holds.clear()
                else:
                    holds.pop(transition.id, None)
                traces.append(
                    ScenarioTrace(
                        frame.now,
                        transition.id,
                        previous,
                        memory.state,
                        transition.reason,
                        memory.episode_id,
                    )
                )
                if memory.state in self._terminal_states:
                    break
        except Exception:
            # Handlers are an extension boundary. Do not publish a partial tick.
            self._disabled = True
            self._holds.clear()
            self._trace.append(
                ScenarioTrace(
                    frame.now,
                    "",
                    self._memory.state,
                    self._memory.state,
                    "scenario_execution_failed",
                    self._memory.episode_id,
                )
            )
            return ()
        self._memory, self._sequence, self._holds = memory, sequence, holds
        self._trace.extend(traces)
        return tuple(beats)

    def _validate_beat(self, beat: ScenarioBeat, memory: EpisodeMemory) -> None:
        if not isinstance(beat, ScenarioBeat) or (
            not memory.episode_id
            or beat.episode_id != memory.episode_id
            or beat.parent_story_id != memory.episode_id
            or beat.scenario_id != self.definition.scenario_id
            or beat.scenario_version != self.definition.scenario_version
        ):
            raise ValueError("beat has incompatible episode identity")
        if not any(
            spec.beat_id == beat.beat_id
            and spec.event_type == beat.event_type
            and spec.phase == beat.phase
            for spec in self.definition.emissions.values()
        ):
            raise ValueError("beat does not match a declared emission")

    def _reset_scope(self, frame: ScenarioFrame) -> None:
        prior = self._memory
        self._scope = frame.scope
        self._memory = EpisodeMemory(self.definition.initial_state, frame.now)
        self._last_now = None
        self._disconnected_since = None
        # Do not reuse an ID if the camera/hero later returns to a prior scope.
        self._holds.clear()
        self._disabled = False
        if prior.episode_id:
            self._trace.append(
                ScenarioTrace(
                    frame.now,
                    "",
                    prior.state,
                    self._memory.state,
                    "scope_changed",
                    prior.episode_id,
                )
            )

    def _disconnect_grace(self) -> float:
        value = self.definition.parameters.get("disconnectGraceS", 1.0)
        return float(value) if isinstance(value, (int, float)) else 1.0

    def _invalidate(self, now: float, reason: str) -> None:
        prior = self._memory
        self._memory = EpisodeMemory(self.definition.initial_state, now)
        self._holds.clear()
        if prior.episode_id:
            self._trace.append(
                ScenarioTrace(now, "", prior.state, self._memory.state, reason, prior.episode_id)
            )
