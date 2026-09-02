"""HUNTING / HUNTED state machines with hysteresis. No duration/cooldown."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import TypeGuard

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
    intensity_since: float = 0.0
    last_update_at: float = 0.0
    last_update_gap: float | None = None
    relation_epoch: int = 0
    last_payload: dict = field(default_factory=dict)
    entry_position: int | None = None
    entry_class_position: int | None = None


def _payload_gap(payload: dict) -> float | None:
    gap = payload.get("gap")
    if isinstance(gap, bool) or not isinstance(gap, (int, float)):
        return None
    return float(gap) if isfinite(gap) and gap >= 0 else None


def _finite_number(value: object) -> TypeGuard[int | float]:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def _direction_valid(state: RaceState, target: object, direction: str) -> bool:
    """Compare like-for-like standings; never mix class and overall positions."""
    hero_pos = state.class_position
    target_pos = getattr(target, "class_position", None)
    if hero_pos is None or target_pos is None:
        hero_pos, target_pos = state.position, getattr(target, "position", None)
    if not isinstance(hero_pos, int) or not isinstance(target_pos, int):
        return False
    if (
        isinstance(hero_pos, bool)
        or isinstance(target_pos, bool)
        or hero_pos <= 0
        or target_pos <= 0
    ):
        return False
    return bool(target_pos < hero_pos if direction == "hunting" else target_pos > hero_pos)


@dataclass
class BattleEmitter:
    hunting_cfg: HuntingSettings
    hunted_cfg: HuntingSettings
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    hunting: _Track = field(default_factory=_Track)
    hunted: _Track = field(default_factory=_Track)
    _battle_for_position_active: bool = False
    _battle_for_position_key: tuple[int, int, int, int] | None = None
    _battle_for_position_payload: dict = field(default_factory=dict)
    _hunting_peak: str = "hunting"

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if state.session_finished or state.mute_field:
            return self._abort_active(state, now, reason="session_finished")
        if state.on_pit_road:
            return self._abort_active(state, now, reason="pit_cycle")
        if state.data_quality == "stale" or (
            state.stale_for_ms is not None and state.stale_for_ms > 3_000
        ):
            return self._abort_active(state, now, reason="stale_relation")
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
        events.extend(self._meta_battle_events(state, now, parents_changed=bool(events)))
        return events

    def _meta_battle_events(
        self, state: RaceState, now: float, *, parents_changed: bool = False
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        both = self.hunting.state == "ACTIVE" and self.hunted.state == "ACTIVE"
        front_idx = self.hunting.target_car_idx
        rear_idx = self.hunted.target_car_idx
        key = (
            front_idx if front_idx is not None else -1,
            self.hunting.relation_epoch,
            rear_idx if rear_idx is not None else -1,
            self.hunted.relation_epoch,
        )
        payload = {
            "state": "battle_for_position",
            "heroCarIdx": state.player_car_idx,
            "heroPosition": state.position,
            "position": state.position,
            "frontTargetCarIdx": front_idx,
            "frontTargetName": getattr(state.opponent_ahead, "display_name", None),
            "frontTargetPosition": getattr(state.opponent_ahead, "position", None),
            "frontGap": state.gap_ahead,
            "frontRelationEpoch": self.hunting.relation_epoch,
            "rearTargetCarIdx": rear_idx,
            "rearTargetName": getattr(state.opponent_behind, "display_name", None),
            "rearTargetPosition": getattr(state.opponent_behind, "position", None),
            "rearGap": state.gap_behind,
            "rearRelationEpoch": self.hunted.relation_epoch,
        }
        if both and not self._battle_for_position_active:
            self._battle_for_position_active = True
            self._battle_for_position_key = key
            self._battle_for_position_payload = dict(payload)
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="enter",
                    data=payload,
                )
            )
        elif both and self._battle_for_position_key != key:
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="exit",
                    data={**self._battle_for_position_payload, "reason": "target_change"},
                )
            )
            self._battle_for_position_key = key
            self._battle_for_position_payload = dict(payload)
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="enter",
                    data=payload,
                )
            )
        elif both and parents_changed:
            self._battle_for_position_payload = dict(payload)
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="update",
                    data=payload,
                )
            )
        elif not both and self._battle_for_position_active:
            self._battle_for_position_active = False
            self._battle_for_position_key = None
            events.append(
                CandidateEvent(
                    name="battle",
                    channel="battle",
                    priority=self.priorities.battle_start,
                    phase="exit",
                    data=dict(self._battle_for_position_payload),
                )
            )
            self._battle_for_position_payload = {}
        if self.hunting.state == "ACTIVE" and self.hunting.intensity in {
            "attack_range",
            "side_by_side",
        }:
            self._hunting_peak = self.hunting.intensity
        return events

    def _maybe_battle_won(
        self, exit_intensity: str, state: RaceState, track: _Track
    ) -> CandidateEvent | None:
        if exit_intensity not in {"attack_range", "side_by_side"}:
            return None
        current = state.class_position if track.entry_class_position is not None else state.position
        entered = (
            track.entry_class_position
            if track.entry_class_position is not None
            else track.entry_position
        )
        former_target = state.opponent_behind
        target_id = track.target_car_idx
        target_position = (
            getattr(former_target, "class_position", None)
            if track.entry_class_position is not None
            else getattr(former_target, "position", None)
        )
        if (
            not isinstance(current, int)
            or isinstance(current, bool)
            or not isinstance(entered, int)
            or isinstance(entered, bool)
            or current >= entered
            or former_target is None
            or getattr(former_target, "car_idx", None) != target_id
            or not isinstance(target_position, int)
            or isinstance(target_position, bool)
            or target_position <= current
        ):
            return None
        self._hunting_peak = "hunting"
        target_name = getattr(former_target, "display_name", None)
        return CandidateEvent(
            name="battle",
            channel="battle",
            priority=self.priorities.battle_start,
            phase="trigger",
            data={
                "state": "battle_won",
                "position": current,
                "oldPosition": entered,
                "newPosition": current,
                "targetCarIdx": target_id,
                **({"targetName": target_name} if target_name else {}),
            },
            duration=4.0,
        )

    def reset(self) -> None:
        self.hunting = _Track()
        self.hunted = _Track()
        self._battle_for_position_active = False
        self._battle_for_position_key = None
        self._battle_for_position_payload = {}
        self._hunting_peak = "hunting"

    def _abort_active(self, state: RaceState, now: float, *, reason: str) -> list[CandidateEvent]:
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
                    data={**track.last_payload, "state": exit_state, "reason": reason},
                )
            )
            track.state = "NONE"
            track.intensity = battle_state
            track.fail_since = None
            track.target_car_idx = None
        events.extend(self._meta_battle_events(state, now, parents_changed=bool(events)))
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
        source_valid = (
            _finite_number(gap)
            and gap >= 0
            and _finite_number(closing)
            and _direction_valid(state, target, battle_state)
        )
        enter_ok = (
            connected
            and car_idx is not None
            and source_valid
            and gap is not None
            and gap < cfg.enter_gap
            and closing is not None
            and closing > cfg.min_closing_rate
        )
        stay_ok = (
            connected
            and car_idx is not None
            and track.target_car_idx == car_idx
            and source_valid
            and gap is not None
            and gap <= cfg.exit_gap
            and closing is not None
            and closing >= 0.0
        )
        if battle_state == "hunted":
            hero_cp = state.class_position if state.class_position is not None else state.position
            field_n = state.class_field_size
            behind_cp = getattr(target, "class_position", None) if target is not None else None
            last = (
                hero_cp is not None
                and field_n is not None
                and int(field_n) > 0
                and int(hero_cp) >= int(field_n)
            )
            inverted = (
                hero_cp is not None and behind_cp is not None and int(behind_cp) <= int(hero_cp)
            )
            if last or inverted or target is None:
                enter_ok = False
                stay_ok = False

        active_state = (
            resolve_hunting_intensity(gap, closing, track.intensity, cfg)
            if intensity_ladder and track.state == "ACTIVE" and source_valid
            else battle_state
        )

        payload = {
            "state": active_state,
            "direction": "front" if battle_state == "hunting" else "rear",
            "heroCarIdx": state.player_car_idx,
            "relationEpoch": track.relation_epoch,
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
                if intensity_ladder and battle_state == "hunting":
                    won = self._maybe_battle_won(track.intensity, state, track)
                    if won is not None:
                        events.append(won)
                events.append(
                    CandidateEvent(
                        name=event_name,
                        channel="battle",
                        priority=priority,
                        phase="exit",
                        data={
                            **track.last_payload,
                            "state": track.intensity if intensity_ladder else battle_state,
                            "reason": "target_change",
                            "targetCarIdx": track.target_car_idx,
                            "relationEpoch": track.relation_epoch,
                        },
                    )
                )
            track.state = "NONE"
            track.intensity = battle_state
            track.target_car_idx = car_idx
            track.relation_epoch += 1
            payload["relationEpoch"] = track.relation_epoch
            track.since = now
            track.fail_since = None

        if track.state == "NONE":
            if enter_ok:
                if track.target_car_idx != car_idx:
                    track.relation_epoch += 1
                    payload["relationEpoch"] = track.relation_epoch
                track.state = "CANDIDATE"
                track.since = now
                track.target_car_idx = car_idx
                track.intensity = battle_state
                track.fail_since = None
                if cfg.activation_delay <= 0:
                    track.state = "ACTIVE"
                    track.intensity_since = now
                    track.last_update_at = now
                    track.last_update_gap = _payload_gap(payload)
                    track.entry_position = state.position
                    track.entry_class_position = state.class_position
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
                track.intensity_since = now
                track.last_update_at = now
                track.last_update_gap = _payload_gap(payload)
                track.entry_position = state.position
                track.entry_class_position = state.class_position
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
                            now=now,
                            cfg=cfg,
                        )
                    )
                else:
                    update = self._maybe_update(
                        track=track,
                        event_name=event_name,
                        priority=priority,
                        payload=payload,
                        now=now,
                        cfg=cfg,
                    )
                    if update is not None:
                        events.append(update)
            else:
                if track.fail_since is None:
                    track.fail_since = now
                if not source_valid or now - track.fail_since >= cfg.exit_delay:
                    exit_state = track.intensity if intensity_ladder else battle_state
                    if intensity_ladder and battle_state == "hunting":
                        won = self._maybe_battle_won(exit_state, state, track)
                        if won is not None:
                            events.append(won)
                    events.append(
                        CandidateEvent(
                            name=event_name,
                            channel="battle",
                            priority=priority,
                            phase="exit",
                            data={
                                **(payload if source_valid else track.last_payload),
                                "state": exit_state,
                                **({"reason": "invalid_relation"} if not source_valid else {}),
                            },
                        )
                    )
                    track.state = "NONE"
                    track.intensity = battle_state
                    track.fail_since = None
                    track.target_car_idx = None
        for event in events:
            if event.phase in {"enter", "update"}:
                track.last_payload = dict(event.data)
        return events

    @staticmethod
    def _maybe_update(
        *,
        track: _Track,
        event_name: str,
        priority: int,
        payload: dict,
        now: float,
        cfg: HuntingSettings,
    ) -> CandidateEvent | None:
        gap_f = _payload_gap(payload)
        interval = max(0.25, float(cfg.update_min_interval_s))
        epsilon = max(0.0, float(cfg.update_gap_epsilon_s))
        gap_moved = (
            gap_f is not None
            and track.last_update_gap is not None
            and abs(gap_f - track.last_update_gap) >= epsilon
        )
        due = track.last_update_at <= 0.0 or (now - track.last_update_at) >= interval
        if not due and not gap_moved:
            return None
        track.last_update_at = now
        track.last_update_gap = gap_f
        return CandidateEvent(
            name=event_name,
            channel="battle",
            priority=priority,
            phase="update",
            data=payload,
        )

    @staticmethod
    def _apply_intensity_change(
        *,
        track: _Track,
        event_name: str,
        priority: int,
        payload: dict,
        next_state: str,
        now: float,
        cfg: HuntingSettings,
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        hold = max(0.0, float(cfg.min_intensity_hold_s))
        if next_state != track.intensity:
            held = now - track.intensity_since if track.intensity_since > 0 else hold
            if held < hold:
                update = BattleEmitter._maybe_update(
                    track=track,
                    event_name=event_name,
                    priority=priority,
                    payload={**payload, "state": track.intensity},
                    now=now,
                    cfg=cfg,
                )
                if update is not None:
                    events.append(update)
                return events
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
            track.intensity_since = now
            track.last_update_at = now
            track.last_update_gap = _payload_gap(payload)
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
        update = BattleEmitter._maybe_update(
            track=track,
            event_name=event_name,
            priority=priority,
            payload={**payload, "state": track.intensity},
            now=now,
            cfg=cfg,
        )
        if update is not None:
            events.append(update)
        return events
