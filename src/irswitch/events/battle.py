"""HUNTING / HUNTED state machines with hysteresis. No duration/cooldown."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.events.battle_intensity import resolve_hunting_intensity
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, HuntingSettings


@dataclass
class _Track:
    state: str = "NONE"  # NONE | CANDIDATE | ACTIVE
    since: float = 0.0
    fail_since: float | None = None
    target_car_idx: int | None = None
    intensity: str = "hunting"


@dataclass
class BattleEmitter:
    hunting_cfg: HuntingSettings
    hunted_cfg: HuntingSettings
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    hunting: _Track = field(default_factory=_Track)
    hunted: _Track = field(default_factory=_Track)
    _battle_for_position_active: bool = False
    _hunting_peak: str = "hunting"

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if state.session_finished:
            return self._abort_active(state, now)
        events: list[CandidateEvent] = []
        events.extend(
            self._tick_direction(
                track=self.hunting,
                cfg=self.hunting_cfg,
                now=now,
                state=state,
                connected=state.connected,
                target=state.opponent_ahead,
                gap=state.gap_ahead,
                closing=state.closing_rate_ahead,
                event_name="battle",
                battle_state="hunting",
                priority=self.priorities.hunting,
                intensity_ladder=True,
            )
        )
        events.extend(
            self._tick_direction(
                track=self.hunted,
                cfg=self.hunted_cfg,
                now=now,
                state=state,
                connected=state.connected,
                target=state.opponent_behind,
                gap=state.gap_behind,
                closing=state.closing_rate_behind,
                event_name="battle",
                battle_state="hunted",
                priority=self.priorities.hunted,
                intensity_ladder=False,
            )
        )
        events.extend(self._meta_battle_events(state, now))
        return events

    def _meta_battle_events(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        both = self.hunting.state == "ACTIVE" and self.hunted.state == "ACTIVE"
        if both and not self._battle_for_position_active:
            self._battle_for_position_active = True
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="enter",
                    data={
                        "state": "battle_for_position",
                        "position": state.position,
                        "gap": state.gap_ahead,
                        "targetCarIdx": getattr(state.opponent_ahead, "car_idx", None),
                        "targetPosition": getattr(state.opponent_ahead, "position", None),
                        **(
                            {"targetName": state.opponent_ahead.display_name}
                            if state.opponent_ahead is not None
                            and state.opponent_ahead.display_name
                            else {}
                        ),
                    },
                )
            )
        elif not both and self._battle_for_position_active:
            self._battle_for_position_active = False
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="exit",
                    data={"state": "battle_for_position"},
                )
            )
        if self.hunting.state == "ACTIVE" and self.hunting.intensity in {
            "attack_range",
            "side_by_side",
        }:
            self._hunting_peak = self.hunting.intensity
        return events

    def _maybe_battle_won(self, exit_intensity: str, state: RaceState) -> CandidateEvent | None:
        if exit_intensity not in {"attack_range", "side_by_side"}:
            return None
        self._hunting_peak = "hunting"
        return CandidateEvent(
            name="battle",
            channel="battle",
            priority=self.priorities.battle_start,
            phase="trigger",
            data={
                "state": "battle_won",
                "position": state.position,
                "oldPosition": (state.position + 1) if state.position else None,
                "newPosition": state.position,
            },
            duration=4.0,
        )

    def reset(self) -> None:
        self.hunting = _Track()
        self.hunted = _Track()
        self._battle_for_position_active = False
        self._hunting_peak = "hunting"

    def _abort_active(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        for track, name, priority, intensity_ladder, battle_state in (
            (self.hunting, "battle", self.priorities.hunting, True, "hunting"),
            (self.hunted, "battle", self.priorities.hunted, False, "hunted"),
        ):
            if track.state != "ACTIVE":
                track.state = "NONE"
                track.fail_since = None
                track.target_car_idx = None
                continue
            exit_state = track.intensity if intensity_ladder else battle_state
            events.append(
                CandidateEvent(
                    name=name,
                    channel="battle",
                    priority=priority,
                    phase="exit",
                    data={"state": exit_state, "reason": "session_finished"},
                )
            )
            track.state = "NONE"
            track.intensity = battle_state
            track.fail_since = None
            track.target_car_idx = None
        events.extend(self._meta_battle_events(state, now))
        return events

    def _tick_direction(
        self,
        track: _Track,
        cfg: HuntingSettings,
        now: float,
        state: RaceState,
        connected: bool,
        target: object,
        gap: float | None,
        closing: float | None,
        event_name: str,
        battle_state: str,
        priority: int,
        *,
        intensity_ladder: bool,
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        car_idx = getattr(target, "car_idx", None) if target is not None else None
        position = getattr(target, "position", None) if target is not None else None
        enter_ok = (
            connected
            and car_idx is not None
            and gap is not None
            and gap < cfg.enter_gap
            and closing is not None
            and closing > cfg.min_closing_rate
        )
        stay_ok = (
            connected
            and car_idx is not None
            and track.target_car_idx == car_idx
            and gap is not None
            and gap <= cfg.exit_gap
            and closing is not None
            and closing >= 0.0
        )

        active_state = (
            resolve_hunting_intensity(gap, closing, track.intensity, cfg)
            if intensity_ladder and track.state == "ACTIVE"
            else battle_state
        )

        payload = {
            "state": active_state,
            "targetCarIdx": car_idx,
            "targetPosition": position,
            "gap": gap,
            "closingRate": closing,
        }
        target_name = getattr(target, "display_name", None) if target is not None else None
        if target_name:
            payload["targetName"] = target_name

        if track.target_car_idx is not None and car_idx != track.target_car_idx:
            if track.state == "ACTIVE":
                events.append(
                    CandidateEvent(
                        name=event_name,
                        channel="battle",
                        priority=priority,
                        phase="exit",
                        data={
                            **payload,
                            "state": track.intensity if intensity_ladder else battle_state,
                            "reason": "target_change",
                        },
                    )
                )
            track.state = "NONE"
            track.intensity = battle_state
            track.target_car_idx = car_idx
            track.since = now
            track.fail_since = None

        if track.state == "NONE":
            if enter_ok:
                track.state = "CANDIDATE"
                track.since = now
                track.target_car_idx = car_idx
                track.intensity = battle_state
                track.fail_since = None
                if cfg.activation_delay <= 0:
                    track.state = "ACTIVE"
                    events.append(
                        CandidateEvent(
                            name=event_name,
                            channel="battle",
                            priority=priority,
                            phase="enter",
                            data=payload,
                        )
                    )
        elif track.state == "CANDIDATE":
            if not enter_ok:
                track.state = "NONE"
                track.intensity = battle_state
                track.fail_since = None
            elif now - track.since >= cfg.activation_delay:
                track.state = "ACTIVE"
                track.intensity = battle_state
                track.fail_since = None
                events.append(
                    CandidateEvent(
                        name=event_name,
                        channel="battle",
                        priority=priority,
                        phase="enter",
                        data=payload,
                    )
                )
        elif track.state == "ACTIVE":
            if stay_ok:
                track.fail_since = None
                if intensity_ladder:
                    events.extend(
                        self._apply_intensity_change(
                            track=track,
                            event_name=event_name,
                            priority=priority,
                            payload=payload,
                            next_state=active_state,
                        )
                    )
                else:
                    events.append(
                        CandidateEvent(
                            name=event_name,
                            channel="battle",
                            priority=priority,
                            phase="update",
                            data=payload,
                        )
                    )
            else:
                if track.fail_since is None:
                    track.fail_since = now
                elif now - track.fail_since >= cfg.exit_delay:
                    exit_state = track.intensity if intensity_ladder else battle_state
                    if intensity_ladder and battle_state == "hunting":
                        won = self._maybe_battle_won(exit_state, state)
                        if won is not None:
                            events.append(won)
                    events.append(
                        CandidateEvent(
                            name=event_name,
                            channel="battle",
                            priority=priority,
                            phase="exit",
                            data={**payload, "state": exit_state},
                        )
                    )
                    track.state = "NONE"
                    track.intensity = battle_state
                    track.fail_since = None
                    track.target_car_idx = None
        return events

    @staticmethod
    def _apply_intensity_change(
        *,
        track: _Track,
        event_name: str,
        priority: int,
        payload: dict,
        next_state: str,
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        if next_state != track.intensity:
            events.append(
                CandidateEvent(
                    name=event_name,
                    channel="battle",
                    priority=priority,
                    phase="exit",
                    data={**payload, "state": track.intensity},
                )
            )
            track.intensity = next_state
            events.append(
                CandidateEvent(
                    name=event_name,
                    channel="battle",
                    priority=priority,
                    phase="enter",
                    data={**payload, "state": next_state},
                )
            )
            return events
        events.append(
            CandidateEvent(
                name=event_name,
                channel="battle",
                priority=priority,
                phase="update",
                data={**payload, "state": track.intensity},
            )
        )
        return events
