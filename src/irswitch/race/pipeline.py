"""N12 producer boundary: context capture, identity, freeze, and publication."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, is_dataclass
from typing import Any, NamedTuple, cast

from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.audience import audiences_for_event
from irswitch.events.envelope import EventEnvelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    FrozenAcceptedEventBatch,
    FrozenContextSnapshot,
    SessionReset,
    SessionSequenceAllocator,
    freeze_accepted_event,
    freeze_context,
)
from irswitch.iracing.sdk_units import (
    as_elapsed_seconds,
    as_session_laps_remain,
    as_session_time_remain,
)
from irswitch.overlay.models import BioState, RaceState
from irswitch.race.story import StoryContext

logger = logging.getLogger(__name__)


class RacePipeline:
    """Single producer for accepted identities and immutable stream batches."""

    def __init__(
        self,
        fanout: AsyncEventFanout,
        *,
        sequence_allocator: SessionSequenceAllocator | None = None,
    ) -> None:
        self.fanout = fanout
        self.sequence_allocator = sequence_allocator or SessionSequenceAllocator()
        self._context_version = 0
        self._batch_sequence = 0
        self._context_payload: FrozenContextSnapshot | None = None
        self._captured_monotonic_ms = 0
        self._session_id = self.sequence_allocator.session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def context_payload(self) -> FrozenContextSnapshot | None:
        return self._context_payload

    def reset_session(self, session_id: str, *, reason: str) -> SessionReset | None:
        normalized = session_id or "session:unknown"
        if normalized == self._session_id:
            return None
        old = self._session_id
        self._session_id = normalized
        self.sequence_allocator.reset(normalized)
        self._context_version = 0
        self._batch_sequence = 0
        self._context_payload = None
        self._captured_monotonic_ms = 0
        reset = SessionReset(old, normalized, reason, self.fanout.next_stream_sequence())
        self.fanout.publish(reset)
        return reset

    def capture_context(
        self,
        *,
        race: RaceState,
        bio: BioState,
        story: StoryContext | None,
        telemetry_data: dict[str, object] | None,
        captured_monotonic_ms: int,
        language: str,
        commentary_enabled: bool,
        config_generation: int = 0,
        driver_profiles: dict[str, object] | None = None,
        system: Any | None = None,
        hud: dict[str, Any] | None = None,
        grid_story: bool = False,
    ) -> FrozenContextSnapshot:
        self._context_version += 1
        payload = build_context_payload(
            version=self._context_version,
            session_id=self._session_id,
            captured_monotonic_ms=captured_monotonic_ms,
            race=race,
            bio=bio,
            story=story,
            telemetry_data=telemetry_data,
            language=language,
            commentary_enabled=commentary_enabled,
            config_generation=config_generation,
            driver_profiles=driver_profiles,
            system=system,
            hud=hud,
            grid_story=grid_story,
        )
        self._context_payload = freeze_context(payload)
        self._captured_monotonic_ms = captured_monotonic_ms
        self.fanout.publish_context(self._context_payload)
        return self._context_payload

    def publish_envelopes(
        self,
        envelopes: list[EventEnvelope],
        *,
        source: str,
        accepted_monotonic_ms: int,
        overlay_wires: list[dict[str, Any] | None] | None = None,
        poll_interval_ms: int = 200,
    ) -> FrozenAcceptedEventBatch | None:
        if overlay_wires is not None and len(overlay_wires) != len(envelopes):
            raise ValueError("overlay_wires must align with envelopes")
        wires = overlay_wires or [None] * len(envelopes)
        return self.publish_records(
            [
                AcceptedRecord(envelope, source, wire)
                for envelope, wire in zip(envelopes, wires, strict=True)
            ],
            accepted_monotonic_ms=accepted_monotonic_ms,
            poll_interval_ms=poll_interval_ms,
        )

    def publish_records(
        self,
        records: list[AcceptedRecord],
        *,
        accepted_monotonic_ms: int,
        poll_interval_ms: int = 200,
    ) -> FrozenAcceptedEventBatch | None:
        if not records:
            return None
        if self._context_payload is None:
            raise RuntimeError("capture_context must run before publishing events")
        accepted = []
        source_ordinals: dict[str, int] = {}
        for record in records:
            envelope = record.envelope
            source_ordinal = source_ordinals.get(record.source, 0)
            source_ordinals[record.source] = source_ordinal + 1
            if envelope.sequence <= 0 or envelope.session_id != self._session_id:
                self.sequence_allocator.stamp(envelope)
            accepted.append(
                freeze_accepted_event(
                    envelope,
                    audiences=audiences_for_event(envelope.event_type),
                    source=record.source,
                    source_ordinal=source_ordinal,
                    coalesce_key=coalesce_key_for(envelope, self._session_id),
                    overlay_payload=record.overlay_wire,
                )
            )
        self._batch_sequence += 1
        batch = FrozenAcceptedEventBatch(
            stream_sequence=self.fanout.next_stream_sequence(),
            session_id=self._session_id,
            batch_sequence=self._batch_sequence,
            accepted_monotonic_ms=accepted_monotonic_ms,
            context_version=self._context_version,
            context_payload=self._context_payload,
            events=tuple(accepted),
        )
        if context_stale_at_accept(
            captured_ms=self._captured_monotonic_ms,
            accepted_ms=accepted_monotonic_ms,
            poll_interval_ms=poll_interval_ms,
        ):
            logger.warning(
                "context_stale_at_accept captured_ms=%s accepted_ms=%s age_ms=%s poll_interval_ms=%s",
                self._captured_monotonic_ms,
                accepted_monotonic_ms,
                accepted_monotonic_ms - self._captured_monotonic_ms,
                poll_interval_ms,
            )
        self.fanout.publish(batch)
        return batch


class AcceptedRecord(NamedTuple):
    envelope: EventEnvelope
    source: str
    overlay_wire: dict[str, Any] | None = None


def build_context_payload(
    *,
    version: int,
    session_id: str,
    captured_monotonic_ms: int,
    race: RaceState,
    bio: BioState,
    story: StoryContext | None,
    telemetry_data: dict[str, object] | None,
    language: str,
    commentary_enabled: bool,
    config_generation: int,
    driver_profiles: dict[str, object] | None,
    system: Any | None = None,
    hud: dict[str, Any] | None = None,
    grid_story: bool = False,
) -> dict[str, Any]:
    story_payload = _jsonable(asdict(story)) if story is not None else {}
    story_payload["driver_profiles"] = driver_profiles or {}
    story_payload["grid_story"] = grid_story
    situation = build_situation_payload(race, telemetry_data, captured_monotonic_ms)
    system_payload = _jsonable(system.to_dict()) if system is not None else {}
    hud_payload = {
        "active_events": list((hud or {}).get("active_events") or []),
        "active_stories_v4": list((hud or {}).get("active_stories_v4") or []),
    }
    return {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "version": version,
        "session_id": session_id,
        "captured_monotonic_ms": captured_monotonic_ms,
        "identity": {
            "overlay_mode": race.overlay_mode,
            "session_type": race.session_type,
            "session_num": race.session_num,
            "subsession_id": race.subsession_id,
            "track_id": race.track_id,
        },
        "race": race.to_dict(),
        "bio": {
            "status": bio.status,
            "connected": bio.connected,
            "device_name": bio.device_name,
            "bpm": bio.bpm,
            "baseline_bpm": bio.baseline_bpm,
            "delta_bpm": bio.delta_bpm,
            "hr_state": bio.state,
            "sample_monotonic_ms": captured_monotonic_ms,
        },
        "story": story_payload,
        "situation": situation,
        "system": system_payload,
        "hud": hud_payload,
        "config": {
            "generation": config_generation,
            "language": language,
            "commentary_enabled": commentary_enabled,
            "grid_story": grid_story,
        },
    }


def context_stale_at_accept(
    *,
    captured_ms: int,
    accepted_ms: int,
    poll_interval_ms: int,
) -> bool:
    """True when publish/accept lagged capture by more than one producer poll."""
    if poll_interval_ms <= 0:
        return False
    return max(0, accepted_ms - captured_ms) > poll_interval_ms


def build_situation_payload(
    race: RaceState,
    telemetry_data: dict[str, object] | None,
    captured_monotonic_ms: int,
) -> dict[str, object]:
    data = telemetry_data or {}
    current_lap = _positive_int(race.lap)
    completed_lap = _non_negative_int(race.lap_completed)
    total_laps = _active_session_total_laps(data, race.session_num)
    laps_remaining = as_session_laps_remain(data.get("SessionLapsRemain"))
    elapsed = as_elapsed_seconds(race.session_time)
    remaining = as_session_time_remain(data.get("SessionTimeRemain"))
    total_time = _active_session_total_time(data, race.session_num)
    progress: float | None = None
    source: str | None = None
    if total_laps and completed_lap is not None:
        progress = _clamp(completed_lap / total_laps)
        source = "laps"
    elif total_time and elapsed is not None:
        progress = _clamp(elapsed / total_time)
        source = "time"
    elif total_time and remaining is not None:
        progress = _clamp(1.0 - (remaining / total_time))
        source = "time"

    racing = race.session_state == 4 or race.flag_green
    if race.player_finished:
        phase = "finished"
    elif race.session_checkered:
        phase = "checkered"
    elif race.is_final_lap:
        phase = "final_lap"
    elif race.overlay_mode != "RACE" or progress is None:
        phase = "unknown"
    elif race.session_state is not None and not racing:
        phase = "opening"
    elif progress < 0.2:
        phase = "opening"
    elif progress < 0.7:
        phase = "middle"
    else:
        phase = "closing"
    return {
        "session_type": race.session_type,
        "current_lap": current_lap,
        "lap_completed": completed_lap,
        "total_laps": total_laps,
        "laps_remaining": laps_remaining,
        "session_time_elapsed_s": elapsed,
        "session_time_total_s": total_time,
        "session_time_remaining_s": remaining,
        "progress_ratio": progress,
        "progress_source": source,
        "race_phase": phase,
        "is_final_lap": race.is_final_lap,
        "session_checkered": race.session_checkered,
        "player_finished": race.player_finished,
        "captured_monotonic_ms": captured_monotonic_ms,
    }


def coalesce_key_for(envelope: EventEnvelope, session_id: str) -> tuple[str, ...] | None:
    if envelope.phase not in {"ACTIVE", "UPDATE"}:
        return None
    event_type = envelope.event_type
    metrics = envelope.metrics
    hero = envelope.subject.car_id or "player"
    target = envelope.target.car_id if envelope.target is not None else metrics.get("targetCarIdx")
    epoch = metrics.get("relationEpoch", metrics.get("relation_epoch", 0))
    if event_type in {"HUNTING", "APPROACH", "ATTACK_RANGE", "SIDE_BY_SIDE"}:
        if target is None:
            return None
        return (session_id, "front", str(hero), str(target), str(epoch), event_type)
    if event_type == "HUNTED":
        if target is None:
            return None
        return (session_id, "rear", str(hero), str(target), str(epoch))
    if event_type == "BATTLE_FOR_POSITION":
        required = (
            metrics.get("frontTargetCarIdx"),
            metrics.get("frontRelationEpoch"),
            metrics.get("rearTargetCarIdx"),
            metrics.get("rearRelationEpoch"),
        )
        if any(value is None for value in required):
            return None
        return (session_id, "two_front", str(hero), *(str(value) for value in required))
    if event_type in {"SECTOR_SPLIT", "SECTOR_BEST", "PACE_HUNT"}:
        lap = metrics.get("lap")
        sector = metrics.get("sectorId", metrics.get("sector"))
        if lap is None or sector is None:
            return None
        return (session_id, event_type, str(hero), str(lap), str(sector))
    if event_type.startswith("PIT_") and envelope.correlation_id:
        return (session_id, event_type, envelope.correlation_id)
    if event_type in {"HR_PRESSURE", "LINK_DROP"} and envelope.correlation_id:
        return (session_id, event_type, str(hero), envelope.correlation_id)
    return None


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _active_session(data: dict[str, object], session_num: int | None) -> dict[str, object]:
    info = data.get("SessionInfo")
    if not isinstance(info, dict):
        return {}
    sessions = info.get("Sessions")
    if not isinstance(sessions, list) or session_num is None:
        return {}
    for raw in sessions:
        if not isinstance(raw, dict):
            continue
        try:
            if int(raw.get("SessionNum", -1)) == session_num:
                return raw
        except (TypeError, ValueError):
            continue
    if 0 <= session_num < len(sessions) and isinstance(sessions[session_num], dict):
        return cast(dict[str, object], sessions[session_num])
    return {}


def _active_session_total_laps(data: dict[str, object], session_num: int | None) -> int | None:
    raw = _active_session(data, session_num).get("SessionLaps")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if 0 < value < 32_767 else None


def _active_session_total_time(data: dict[str, object], session_num: int | None) -> float | None:
    raw = _active_session(data, session_num).get("SessionTime")
    if isinstance(raw, str):
        raw = raw.strip().split()[0] if raw.strip() else None
    value = as_elapsed_seconds(raw)
    return value if value is not None and value < 604_800 else None


def _positive_int(value: object) -> int | None:
    normalized = _non_negative_int(value)
    return normalized if normalized is not None and normalized > 0 else None


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _clamp(value: float) -> float | None:
    if not math.isfinite(value):
        return None
    return min(1.0, max(0.0, value))
