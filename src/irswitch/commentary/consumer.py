"""Commentary peer consumer for the immutable N12 event stream."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import fields
from typing import Any

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.tts import ProcessTtsSink
from irswitch.events.async_fanout import EventSubscription
from irswitch.events.envelope import EventEnvelope
from irswitch.events.stream import (
    ConfigUpdate,
    FillerRequest,
    FillerResult,
    FrozenAcceptedEventBatch,
    SessionReset,
    StreamItem,
    thaw_config,
    thaw_context,
    thaw_envelope,
    thaw_story_payload,
)
from irswitch.overlay.models import BioState
from irswitch.overlay.settings import CommentarySchedulerSettings, CommentarySettings
from irswitch.race.ministory import MiniStoryRegistry


class CommentaryConsumer:
    """Own director/scheduler/TTS in an independently scheduled execution lane."""

    def __init__(
        self,
        subscription: EventSubscription,
        director: CommentaryDirector,
        get_settings: Callable[[], tuple[CommentarySettings, str]],
        *,
        decision_hook: Callable[[dict[str, Any], float], None] | None = None,
        story_registry: MiniStoryRegistry | None = None,
    ) -> None:
        self.subscription = subscription
        self.director = director
        self._settings, self._language = get_settings()
        self._decision_hook = decision_hook
        self._filler_requests: asyncio.Queue[FillerRequest] = asyncio.Queue(maxsize=1)
        self._filler_results: asyncio.Queue[FillerResult] = asyncio.Queue(maxsize=1)
        self._outstanding_filler: FillerRequest | None = None
        self.running = False
        self.processed = 0
        self.failures = 0
        self.duplicates = 0
        self.expired = 0
        self.last_error: str | None = None
        self.last_stream_sequence = 0
        self._processed_ids: set[str] = set()
        self._processed_order: list[str] = []
        self.story_registry = story_registry or MiniStoryRegistry()
        self._seen_hero_order_revision = self.story_registry.hero_order_revision
        self.director.story_registry = self.story_registry
        if hasattr(self.director.sink, "story_registry"):
            self.director.sink.story_registry = self.story_registry
        self.director.filler_provider = self._request_filler
        self.director.on_decision = self._forward_decision

    async def run(self) -> None:
        self.running = True
        try:
            while True:
                try:
                    item = await asyncio.wait_for(self.subscription.get(), timeout=0.2)
                except TimeoutError:
                    self._idle_tick()
                    continue
                try:
                    await self.handle(item)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.failures += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    __import__("logging").getLogger(__name__).warning(
                        "commentary consumer failed for one item", exc_info=True
                    )
        finally:
            self.running = False
            self.director.sink.interrupt()

    async def handle(self, item: StreamItem) -> None:
        self.last_stream_sequence = item.stream_sequence
        if isinstance(item, SessionReset):
            self.story_registry.reset(session_id=item.new_session_id)
            self._seen_hero_order_revision = 0
            self.director.reset()
            self._processed_ids.clear()
            self._processed_order.clear()
            self._outstanding_filler = None
            self._drain_queue(self._filler_requests)
            self._drain_queue(self._filler_results)
            self.processed += 1
            return
        if isinstance(item, ConfigUpdate):
            self._apply_config_update(item)
            self.processed += 1
            return
        self._observe_batch(item)
        self.processed += 1

    def take_filler_request(self) -> FillerRequest | None:
        try:
            return self._filler_requests.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def complete_filler(self, result: FillerResult) -> None:
        outstanding = self._outstanding_filler
        if outstanding is None or outstanding.request_id != result.request_id:
            return
        self._outstanding_filler = None
        try:
            self._filler_results.put_nowait(result)
        except asyncio.QueueFull:
            self._drain_queue(self._filler_results)
            self._filler_results.put_nowait(result)

    def note_stream_start_accepted(self, now: float) -> None:
        """Preserve opener mutex at producer acceptance before async dequeue."""
        self.director.opener.note("STREAM_START", now)

    def status_snapshot(self, now: float | None = None) -> dict[str, Any]:
        settings, _ = self._settings_snapshot()
        return {
            **self.director.status_snapshot(
                time.monotonic() if now is None else now,
                enabled=bool(settings.enabled),
            ),
            "running": self.running,
            "processed": self.processed,
            "duplicates": self.duplicates,
            "expired": self.expired,
            "failures": self.failures,
            "lastError": self.last_error,
            "lastStreamSequence": self.last_stream_sequence,
            "fillerOutstanding": self._outstanding_filler is not None,
        }

    def _observe_batch(self, batch: FrozenAcceptedEventBatch) -> None:
        now = time.monotonic()
        context = thaw_context(batch.context_payload)
        latest_payload = self.subscription.latest_context
        latest = thaw_context(latest_payload) if latest_payload is not None else context
        if latest.get("session_id") != batch.session_id:
            self._record_skip("session_context_stale", now)
            return
        self._apply_settings()
        self.story_registry.observe_context(latest)
        if self.story_registry.hero_order_revision > self._seen_hero_order_revision:
            self._seen_hero_order_revision = self.story_registry.hero_order_revision
            self.director.hero_order_changed(now)
        self._apply_story_context(context)
        bio = self._bio_from_context(context)
        envelopes: list[EventEnvelope] = []
        for accepted in batch.events:
            if "commentary" not in accepted.audiences:
                continue
            if accepted.source == "filler":
                self._outstanding_filler = None
            if accepted.event_id in self._processed_ids:
                self.duplicates += 1
                self._record_skip("duplicate_event", now, accepted.event_id)
                continue
            envelope = thaw_envelope(accepted.envelope)
            self._apply_context_bindings(envelope, context, latest)
            if self._situation_no_longer_current(context, latest):
                self._strip_situation_slots(envelope)
                self._record_skip("situation_context_stale", now, envelope.event_type)
            age_s = max(0.0, now - (batch.accepted_monotonic_ms / 1000.0))
            ttl_s = self.director.event_ttl_s(envelope.event_type)
            if age_s > ttl_s:
                self.expired += 1
                self._record_skip("event_expired", now, envelope.event_type)
                self._remember(accepted.event_id)
                continue
            if age_s > 3.0:
                had_situation = any(
                    key in envelope.metrics
                    for key in ("current_lap", "lap_context", "race_phase", "remaining_context")
                )
                self._remove_stale_dynamic_bindings(envelope)
                if had_situation:
                    self._record_skip("situation_context_stale", now, envelope.event_type)
            if accepted.story_payload is not None:
                story_payload = thaw_story_payload(accepted.story_payload)
                self.story_registry.adopt(envelope, story_payload)
                narrate = accepted.phase != "EXIT"
            else:
                observation = self.story_registry.observe(envelope)
                narrate = observation.narrate
            if not narrate:
                self._remember(accepted.event_id)
                continue
            envelopes.append(envelope)
            self._remember(accepted.event_id)
        if not envelopes:
            return
        envelopes = self._prefer_two_front(envelopes, latest, now)
        if not envelopes:
            return
        settings, language = self._settings_snapshot()
        self.director.observe(
            envelopes,
            bio,
            now,
            enabled=settings.enabled,
            language=language,
        )

    def _prefer_two_front(
        self,
        envelopes: list[EventEnvelope],
        latest_context: dict[str, Any],
        now: float,
    ) -> list[EventEnvelope]:
        composite = next(
            (
                envelope
                for envelope in envelopes
                if envelope.event_type == "BATTLE_FOR_POSITION"
                and envelope.phase in {"ENTER", "ACTIVE", "UPDATE"}
            ),
            None,
        )
        if composite is None:
            return envelopes
        race = latest_context.get("race")
        race = race if isinstance(race, dict) else {}
        ahead = race.get("opponent_ahead")
        behind = race.get("opponent_behind")
        ahead = ahead if isinstance(ahead, dict) else {}
        behind = behind if isinstance(behind, dict) else {}
        front = composite.metrics.get("frontTargetCarIdx")
        rear = composite.metrics.get("rearTargetCarIdx")
        if ahead.get("car_idx") != front or behind.get("car_idx") != rear:
            self._record_skip("stale_two_front_relation", now, composite.event_type)
            return [envelope for envelope in envelopes if envelope is not composite]
        parents = {
            "HUNTING",
            "APPROACH",
            "ATTACK_RANGE",
            "SIDE_BY_SIDE",
            "HUNTED",
        }
        filtered: list[EventEnvelope] = []
        for envelope in envelopes:
            if envelope.event_type in parents and envelope.phase in {"ENTER", "ACTIVE"}:
                self._record_skip("covered_by_two_front", now, envelope.event_type)
                continue
            filtered.append(envelope)
        return filtered

    def _apply_context_bindings(
        self,
        envelope: EventEnvelope,
        embedded: dict[str, Any],
        latest: dict[str, Any],
    ) -> None:
        _, language = self._settings_snapshot()
        race = embedded.get("race")
        race = race if isinstance(race, dict) else {}
        story = embedded.get("story")
        story = story if isinstance(story, dict) else {}
        profiles = story.get("driver_profiles")
        profiles = profiles if isinstance(profiles, dict) else {}
        latest_story = latest.get("story")
        latest_story = latest_story if isinstance(latest_story, dict) else {}
        latest_profiles = latest_story.get("driver_profiles")
        latest_profiles = latest_profiles if isinstance(latest_profiles, dict) else {}
        hero_idx = race.get("player_car_idx")
        self._bind_profile(
            envelope,
            prefix="hero",
            profile=profiles.get(str(hero_idx)),
            latest_profile=latest_profiles.get(str(hero_idx)),
            language=language,
        )
        target_idx: object | None = None
        if envelope.target is not None and envelope.target.car_id not in {"", "unknown"}:
            target_idx = envelope.target.car_id
        if target_idx is None:
            target_idx = envelope.metrics.get("targetCarIdx")
        self._bind_profile(
            envelope,
            prefix="target",
            profile=profiles.get(str(target_idx)),
            latest_profile=latest_profiles.get(str(target_idx)),
            language=language,
        )
        situation = embedded.get("situation")
        situation = situation if isinstance(situation, dict) else {}
        envelope.metrics.setdefault("current_lap", situation.get("current_lap"))
        envelope.metrics.setdefault("lap_context", _lap_context(situation, language=language))
        envelope.metrics.setdefault(
            "race_phase", _race_phase_label(situation.get("race_phase"), language=language)
        )
        envelope.metrics.setdefault(
            "remaining_context", _remaining_context(situation, language=language)
        )

    @staticmethod
    def _bind_profile(
        envelope: EventEnvelope,
        *,
        prefix: str,
        profile: object,
        latest_profile: object,
        language: str,
    ) -> None:
        if not isinstance(profile, dict) or not isinstance(latest_profile, dict):
            return
        identity = ("session_id", "car_idx", "user_id", "identity_epoch")
        if any(profile.get(key) != latest_profile.get(key) for key in identity):
            return
        envelope.metrics.setdefault(
            f"{prefix}_irating", _spoken_irating(profile.get("i_rating"), language)
        )
        envelope.metrics.setdefault(f"{prefix}_safety_rating", profile.get("safety_rating"))
        envelope.metrics.setdefault(f"{prefix}_car", profile.get("car_name"))
        envelope.metrics.setdefault(f"{prefix}_nationality", profile.get("nationality"))
        envelope.metrics.setdefault(f"{prefix}_start_position", profile.get("start_position"))

    def _idle_tick(self) -> None:
        latest_payload = self.subscription.latest_context
        if latest_payload is None:
            return
        try:
            context = thaw_context(latest_payload)
            self._apply_settings()
            self.story_registry.observe_context(context)
            if self.story_registry.hero_order_revision > self._seen_hero_order_revision:
                self._seen_hero_order_revision = self.story_registry.hero_order_revision
                self.director.hero_order_changed(time.monotonic())
            self.director.tick(time.monotonic(), self._bio_from_context(context))
        except Exception as exc:
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"

    def _request_filler(self, now: float) -> EventEnvelope | None:
        context_payload = self.subscription.latest_context
        if context_payload is None:
            return None
        context = thaw_context(context_payload)
        session_id = str(context.get("session_id") or "")
        settings, language = self._settings_snapshot()
        if not settings.enabled or not session_id:
            return None
        if self._outstanding_filler is not None:
            return None
        request = FillerRequest(
            request_id=uuid.uuid4().hex,
            session_id=session_id,
            requested_monotonic_ms=int(now * 1000),
            locale=language,
            last_spoken_event_id=(self._processed_order[-1] if self._processed_order else None),
        )
        try:
            self._filler_requests.put_nowait(request)
        except asyncio.QueueFull:
            return None
        self._outstanding_filler = request
        return None

    def _apply_settings(self) -> None:
        settings, language = self._settings_snapshot()
        self.director.settings = settings
        self.director.language = language
        sink = self.director.sink
        if isinstance(sink, ProcessTtsSink):
            sink.settings = settings

    def _apply_config_update(self, item: ConfigUpdate) -> None:
        payload = thaw_config(item.frozen_config)
        raw = payload.get("commentary")
        if isinstance(raw, dict):
            self._settings = _commentary_settings_from_dict(raw, self._settings)
        language = payload.get("language")
        if isinstance(language, str) and language.strip():
            self._language = language
        self._apply_settings()

    def _settings_snapshot(self) -> tuple[CommentarySettings, str]:
        return self._settings, self._language

    def _apply_story_context(self, context: dict[str, Any]) -> None:
        self.director.note_composition_context(context)
        story = context.get("story")
        story = story if isinstance(story, dict) else {}
        hero = story.get("hero")
        hero = hero if isinstance(hero, dict) else {}
        names = hero.get("speakable_names")
        self.director.note_hero_names(names if isinstance(names, list) else ())
        config = context.get("config")
        config = config if isinstance(config, dict) else {}
        self.director.grid_story = bool(story.get("grid_story") or config.get("grid_story"))
        self.director.quali_bag_ready = bool(story.get("quali_bag"))

    @staticmethod
    def _bio_from_context(context: dict[str, Any]) -> BioState:
        bio = context.get("bio")
        data = bio if isinstance(bio, dict) else {}
        return BioState(
            connected=bool(data.get("connected")),
            status=str(data.get("status") or "disconnected"),
            device_name=(str(data["device_name"]) if data.get("device_name") else None),
            bpm=(int(data["bpm"]) if isinstance(data.get("bpm"), int) else None),
            baseline_bpm=(
                float(data["baseline_bpm"])
                if isinstance(data.get("baseline_bpm"), (int, float))
                else None
            ),
            delta_bpm=(
                float(data["delta_bpm"])
                if isinstance(data.get("delta_bpm"), (int, float))
                else None
            ),
            state=str(data.get("hr_state") or "unknown"),
        )

    @staticmethod
    def _situation_no_longer_current(embedded: dict[str, Any], latest: dict[str, Any]) -> bool:
        sit = embedded.get("situation")
        latest_sit = latest.get("situation")
        if not isinstance(sit, dict) or not isinstance(latest_sit, dict) or not sit:
            return False
        if sit.get("current_lap") != latest_sit.get("current_lap"):
            return True
        return sit.get("race_phase") != latest_sit.get("race_phase")

    @staticmethod
    def _strip_situation_slots(envelope: EventEnvelope) -> None:
        for key in ("current_lap", "lap_context", "race_phase", "remaining_context"):
            envelope.metrics.pop(key, None)

    @staticmethod
    def _remove_stale_dynamic_bindings(envelope: EventEnvelope) -> None:
        for key in (
            "gap",
            "gapBehind",
            "frontGap",
            "rearGap",
            "frontTargetName",
            "rearTargetName",
            "target_name",
            "targetName",
            "position",
            "classPosition",
            "current_lap",
            "lap_context",
            "race_phase",
            "remaining_context",
        ):
            envelope.metrics.pop(key, None)
        envelope.target = None

    def _remember(self, event_id: str) -> None:
        if event_id in self._processed_ids:
            return
        self._processed_ids.add(event_id)
        self._processed_order.append(event_id)
        if len(self._processed_order) > 2_048:
            expired = self._processed_order.pop(0)
            self._processed_ids.discard(expired)

    def _record_skip(self, reason: str, now: float, event_type: str = "") -> None:
        self.director.record_external_skip(reason=reason, now=now, event_type=event_type)

    def _forward_decision(self, entry: dict[str, Any], now: float) -> None:
        if self._decision_hook is None:
            return
        self._decision_hook(entry, now)

    @staticmethod
    def _drain_queue(queue: asyncio.Queue[Any]) -> None:
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return


def _spoken_irating(value: object, language: str) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    if value < 1_000:
        return str(value)
    decimal = f"{value / 1000:.1f}".replace(".0", "")
    if language.lower().startswith("cs"):
        return f"{decimal.replace('.', ',')} tisíce"
    return f"{decimal} thousand"


def _commentary_settings_from_dict(
    raw: dict[str, Any], fallback: CommentarySettings
) -> CommentarySettings:
    values = {
        field.name: raw.get(field.name, getattr(fallback, field.name))
        for field in fields(CommentarySettings)
        if field.name != "scheduler"
    }
    scheduler_raw = raw.get("scheduler")
    if isinstance(scheduler_raw, dict):
        scheduler = CommentarySchedulerSettings(
            **{
                field.name: scheduler_raw.get(field.name, getattr(fallback.scheduler, field.name))
                for field in fields(CommentarySchedulerSettings)
            }
        )
    else:
        scheduler = fallback.scheduler
    mode = str(values.get("graph_runtime_mode", fallback.graph_runtime_mode)).strip().lower()
    values["graph_runtime_mode"] = mode if mode in {"legacy", "shadow", "active"} else "legacy"
    return CommentarySettings(**values, scheduler=scheduler)


def _lap_context(situation: dict[str, Any], *, language: str) -> str | None:
    current = situation.get("current_lap")
    total = situation.get("total_laps")
    if not isinstance(current, int) or current <= 0:
        return None
    if language.lower().startswith("cs"):
        return f"{current}. kolo z {total}" if isinstance(total, int) else f"{current}. kolo"
    return f"lap {current} of {total}" if isinstance(total, int) else f"lap {current}"


def _race_phase_label(value: object, *, language: str) -> str | None:
    key = str(value or "")
    if language.lower().startswith("cs"):
        return {
            "opening": "úvodní fáze",
            "middle": "střední fáze",
            "closing": "závěrečná fáze",
            "final_lap": "poslední kolo",
            "checkered": "šachovnicová vlajka",
            "finished": "cíl",
        }.get(key)
    return {
        "opening": "opening phase",
        "middle": "middle phase",
        "closing": "closing phase",
        "final_lap": "final lap",
        "checkered": "checkered phase",
        "finished": "finish",
    }.get(key)


def _remaining_context(situation: dict[str, Any], *, language: str) -> str | None:
    laps = situation.get("laps_remaining")
    if isinstance(laps, (int, float)) and not isinstance(laps, bool) and laps >= 0:
        count = int(laps)
        return (
            f"zbývá {count} kol" if language.lower().startswith("cs") else f"{count} laps remaining"
        )
    seconds = situation.get("session_time_remaining_s")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
        minutes = max(1, round(float(seconds) / 60))
        return (
            f"zbývá {minutes} minut"
            if language.lower().startswith("cs")
            else f"{minutes} minutes remaining"
        )
    return None
