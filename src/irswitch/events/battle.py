"""HUNTING / HUNTED state machines with hysteresis. No duration/cooldown."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, HuntingSettings


@dataclass
class _Track:
    state: str = "NONE"  # NONE | CANDIDATE | ACTIVE
    since: float = 0.0
    fail_since: float | None = None
    target_car_idx: int | None = None


@dataclass
class BattleEmitter:
    hunting_cfg: HuntingSettings
    hunted_cfg: HuntingSettings
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    hunting: _Track = field(default_factory=_Track)
    hunted: _Track = field(default_factory=_Track)

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        events.extend(
            self._tick_direction(
                track=self.hunting,
                cfg=self.hunting_cfg,
                now=now,
                connected=state.connected,
                target=state.opponent_ahead,
                gap=state.gap_ahead,
                closing=state.closing_rate_ahead,
                name="hunting",
                event_name="battle",
                battle_state="hunting",
                priority=self.priorities.hunting,
            )
        )
        events.extend(
            self._tick_direction(
                track=self.hunted,
                cfg=self.hunted_cfg,
                now=now,
                connected=state.connected,
                target=state.opponent_behind,
                gap=state.gap_behind,
                closing=state.closing_rate_behind,
                name="hunted",
                event_name="battle",
                battle_state="hunted",
                priority=self.priorities.hunted,
            )
        )
        return events

    def _tick_direction(
        self,
        track: _Track,
        cfg: HuntingSettings,
        now: float,
        connected: bool,
        target: object,
        gap: float | None,
        closing: float | None,
        name: str,
        event_name: str,
        battle_state: str,
        priority: int,
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

        payload = {
            "state": battle_state,
            "targetCarIdx": car_idx,
            "targetPosition": position,
            "gap": gap,
            "closingRate": closing,
        }

        if track.target_car_idx is not None and car_idx != track.target_car_idx:
            if track.state == "ACTIVE":
                events.append(
                    CandidateEvent(
                        name=event_name,
                        channel="battle",
                        priority=priority,
                        phase="exit",
                        data={**payload, "state": battle_state, "reason": "target_change"},
                    )
                )
            track.state = "NONE"
            track.target_car_idx = car_idx
            track.since = now
            track.fail_since = None

        if track.state == "NONE":
            if enter_ok:
                track.state = "CANDIDATE"
                track.since = now
                track.target_car_idx = car_idx
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
                track.fail_since = None
            elif now - track.since >= cfg.activation_delay:
                track.state = "ACTIVE"
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
                    events.append(
                        CandidateEvent(
                            name=event_name,
                            channel="battle",
                            priority=priority,
                            phase="exit",
                            data=payload,
                        )
                    )
                    track.state = "NONE"
                    track.fail_since = None
                    track.target_car_idx = None
        return events
