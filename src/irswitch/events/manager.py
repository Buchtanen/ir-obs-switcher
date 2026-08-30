"""EventManager: channels, priority, lifecycle, cooldown. O(active events)."""

from __future__ import annotations

from irswitch.overlay.display import ActiveSlot, place
from irswitch.overlay.protocol import CandidateEvent, RaceEvent
from irswitch.overlay.settings import EventSettings


class EventManager:
    def __init__(self, settings: EventSettings | None = None) -> None:
        self._settings = settings or EventSettings()
        self._active: list[RaceEvent] = []
        self._cooldowns: dict[str, float] = {}  # name -> ready_at

    def active_events(self) -> list[dict]:
        return [event.to_active_dict() for event in self._active]

    def submit(self, candidate: CandidateEvent, now: float) -> RaceEvent | None:
        if not candidate.overlay:
            return None
        if candidate.phase == "update":
            for event in self._active:
                if event.name == candidate.name and event.channel == candidate.channel:
                    if candidate.data.get("state") == event.data.get("state"):
                        event.data = candidate.data
                        event.phase = "update"
                        event.timestamp = now
                        return event
            return None
        if candidate.phase == "exit":
            remaining: list[RaceEvent] = []
            exited: RaceEvent | None = None
            for event in self._active:
                match = event.name == candidate.name and event.data.get(
                    "state"
                ) == candidate.data.get("state")
                if match:
                    event.phase = "exit"
                    event.timestamp = now
                    event.data = candidate.data
                    exited = event
                else:
                    remaining.append(event)
            self._active = remaining
            return exited

        ready_at = self._cooldowns.get(candidate.name, 0.0)
        if now < ready_at and candidate.phase == "trigger":
            return None

        duration = candidate.duration
        if duration is None:
            duration = self._default_duration(candidate.channel)
        cooldown = candidate.cooldown if candidate.cooldown is not None else 0.0

        slots = [
            ActiveSlot(channel=e.channel, name=self._slot_key(e), priority=e.priority)
            for e in self._active
        ]
        incoming = ActiveSlot(
            channel=candidate.channel,
            name=self._slot_key_candidate(candidate),
            priority=candidate.priority,
        )
        placed = place(slots, incoming)
        if incoming not in placed and not any(
            slot.name == incoming.name and slot.channel == incoming.channel for slot in placed
        ):
            return None

        # Evict events that lost their slot.
        allowed = {(slot.channel, slot.name) for slot in placed}
        self._active = [
            event
            for event in self._active
            if (event.channel, self._slot_key(event)) in allowed
            and self._slot_key(event) != incoming.name
        ]

        race_event = RaceEvent(
            name=candidate.name,
            channel=candidate.channel,
            priority=candidate.priority,
            phase=candidate.phase,
            timestamp=now,
            data=candidate.data,
            duration=duration,
            cooldown=cooldown,
            expires_at=now + duration if candidate.phase != "enter" else 0.0,
            overlay=candidate.overlay,
        )
        # Persistent battle widgets stay until EXIT.
        if candidate.phase == "enter":
            race_event.expires_at = 0.0
        self._active.append(race_event)
        if cooldown > 0 and candidate.phase in {"trigger", "enter"}:
            self._cooldowns[candidate.name] = now + cooldown
        return race_event

    def tick(self, now: float) -> list[RaceEvent]:
        """Expire timed events. Returns EXIT envelopes for the overlay."""
        still: list[RaceEvent] = []
        expired: list[RaceEvent] = []
        for event in self._active:
            if event.expires_at > 0 and now >= event.expires_at:
                event.phase = "exit"
                event.timestamp = now
                expired.append(event)
            else:
                still.append(event)
        self._active = still
        return expired

    def inject(self, name: str, now: float, data: dict | None = None) -> RaceEvent | None:
        catalog = _DEBUG_CATALOG.get(name)
        if catalog is None:
            return None
        candidate = CandidateEvent(
            name=catalog["name"],
            channel=catalog["channel"],
            priority=catalog["priority"],
            phase=catalog["phase"],
            data=data or catalog["data"],
            duration=catalog.get("duration"),
        )
        return self.submit(candidate, now)

    def _default_duration(self, channel: str) -> float:
        if channel == "lap":
            return self._settings.lap_duration
        if channel == "session":
            return self._settings.session_duration
        if channel == "alert":
            return self._settings.alert_duration
        return 4.0

    @staticmethod
    def _slot_key(event: RaceEvent) -> str:
        state = event.data.get("state")
        if state:
            return f"{event.name}:{state}"
        return event.name

    @staticmethod
    def _slot_key_candidate(candidate: CandidateEvent) -> str:
        state = candidate.data.get("state")
        if state:
            return f"{candidate.name}:{state}"
        return candidate.name


_DEBUG_CATALOG: dict[str, dict] = {
    "hunting": {
        "name": "battle",
        "channel": "battle",
        "priority": 20,
        "phase": "enter",
        "data": {
            "state": "hunting",
            "targetCarIdx": 17,
            "targetPosition": 6,
            "gap": 2.81,
            "closingRate": 0.34,
        },
    },
    "hunted": {
        "name": "battle",
        "channel": "battle",
        "priority": 20,
        "phase": "enter",
        "data": {
            "state": "hunted",
            "targetCarIdx": 23,
            "targetPosition": 8,
            "gap": 1.42,
            "closingRate": 0.21,
        },
    },
    "lap_complete": {
        "name": "lap_complete",
        "channel": "lap",
        "priority": 40,
        "phase": "trigger",
        "duration": 4.0,
        "data": {
            "lap": 12,
            "lapTime": 94.372,
            "bestLap": 94.690,
            "deltaToBest": -0.318,
            "personalBest": False,
        },
    },
    "personal_best": {
        "name": "personal_best",
        "channel": "lap",
        "priority": 60,
        "phase": "trigger",
        "duration": 4.0,
        "data": {
            "lap": 12,
            "lapTime": 94.372,
            "bestLap": 94.372,
            "deltaToBest": 0.0,
            "personalBest": True,
        },
    },
    "position_gain": {
        "name": "position_change",
        "channel": "alert",
        "priority": 70,
        "phase": "trigger",
        "data": {"direction": "gain", "oldPosition": 8, "newPosition": 7, "delta": 1},
    },
    "position_loss": {
        "name": "position_change",
        "channel": "alert",
        "priority": 70,
        "phase": "trigger",
        "data": {"direction": "loss", "oldPosition": 7, "newPosition": 8, "delta": -1},
    },
    "overtake": {
        "name": "overtake",
        "channel": "alert",
        "priority": 80,
        "phase": "trigger",
        "data": {"oldPosition": 7, "newPosition": 6},
    },
    "incident": {
        "name": "incident",
        "channel": "alert",
        "priority": 90,
        "phase": "trigger",
        "data": {"value": 2, "total": 5},
    },
    "final_lap": {
        "name": "final_lap",
        "channel": "session",
        "priority": 95,
        "phase": "trigger",
        "duration": 6.0,
        "data": {"lap": 20},
    },
    "finish": {
        "name": "finish",
        "channel": "session",
        "priority": 100,
        "phase": "trigger",
        "duration": 8.0,
        "data": {"position": 5, "classPosition": 3},
    },
    "hr_high": {
        "name": "heart_rate",
        "channel": "bio",
        "priority": 35,
        "phase": "enter",
        "data": {"bpm": 147, "delta": 28, "state": "high"},
    },
    "ble_lost": {
        "name": "ble_lost",
        "channel": "bio",
        "priority": 35,
        "phase": "trigger",
        "duration": 4.0,
        "data": {"status": "disconnected"},
    },
    "cpu_temp_high": {
        "name": "cpu_temp_high",
        "channel": "system",
        "priority": 15,
        "phase": "trigger",
        "duration": 4.0,
        "data": {"temperature": 96},
    },
    "gpu_temp_high": {
        "name": "gpu_temp_high",
        "channel": "system",
        "priority": 15,
        "phase": "trigger",
        "duration": 4.0,
        "data": {"temperature": 91},
    },
    "gain_found": {
        "name": "gain_found",
        "channel": "timing",
        "priority": 45,
        "phase": "trigger",
        "data": {"timingPointId": "MS05", "delta": -0.11, "lap": 4},
    },
    "projected_lap": {
        "name": "projected_lap",
        "channel": "timing",
        "priority": 42,
        "phase": "enter",
        "data": {"projectedTime": 91.774, "confidence": 0.78, "bestLap": 92.0, "position": 7},
    },
    "position_attack": {
        "name": "position_attack",
        "channel": "timing",
        "priority": 55,
        "phase": "trigger",
        "data": {"projectedTime": 91.6, "confidence": 0.82, "targetPosition": 6, "position": 7},
    },
    "sector_best": {
        "name": "sector_best",
        "channel": "timing",
        "priority": 45,
        "phase": "trigger",
        "data": {"timingPointId": "MS02", "delta": -0.24, "lap": 3},
    },
    "target_locked": {
        "name": "target_locked",
        "channel": "timing",
        "priority": 42,
        "phase": "enter",
        "data": {"targetTime": 91.9, "lap": 2},
    },
    "hot_lap": {
        "name": "hot_lap",
        "channel": "timing",
        "priority": 55,
        "phase": "enter",
        "data": {"hotLapIndex": 1, "position": 7, "sectorDelta": -0.117},
    },
    "clean_streak": {
        "name": "clean_streak",
        "channel": "timing",
        "priority": 45,
        "phase": "trigger",
        "data": {"streak": 5, "lap": 12},
    },
    "sector_split": {
        "name": "sector_split",
        "channel": "timing",
        "priority": 45,
        "phase": "trigger",
        "data": {"sector": "S1", "timingPointId": "S1", "segmentTime": 31.214, "lap": 2},
    },
    "invalid_lap": {
        "name": "invalid_lap",
        "channel": "alert",
        "priority": 90,
        "phase": "trigger",
        "data": {"lap": 4, "incidentDelta": 1},
    },
    "link_drop": {
        "name": "link_drop",
        "channel": "alert",
        "priority": 90,
        "phase": "enter",
        "data": {"quality": "stale", "staleForMs": 1200},
    },
    "battle_for_position": {
        "name": "battle",
        "channel": "battle",
        "priority": 25,
        "phase": "enter",
        "data": {"state": "battle_for_position", "position": 7, "gap": 0.5},
    },
    "battle_won": {
        "name": "battle",
        "channel": "battle",
        "priority": 30,
        "phase": "trigger",
        "data": {"state": "battle_won", "position": 6},
    },
    "rival_threat": {
        "name": "rival_threat",
        "channel": "alert",
        "priority": 65,
        "phase": "enter",
        "data": {"rivalPosition": 8, "projectedGap": 0.4},
    },
}


DEBUG_EVENT_NAMES: tuple[str, ...] = tuple(_DEBUG_CATALOG.keys())
