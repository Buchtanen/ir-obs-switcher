"""Overlay runtime: sampling tasks, event engine, mock/replay. Fail-soft."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any, Literal

from irswitch.commentary.bridge import merge_speech_envelopes, speech_envelope_from_race_event
from irswitch.commentary.consumer import CommentaryEventConsumer
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.in_car import InCarDetector
from irswitch.commentary.session_briefs import SessionBriefsDetector
from irswitch.commentary.tts import ProcessTtsSink, build_tts_sink
from irswitch.config import AppConfig
from irswitch.events.engine import EventEngine
from irswitch.events.envelope import EventEnvelope
from irswitch.events.fanout import EventFanout
from irswitch.events.manager import EventManager
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.iracing.sectors import resolve_sector_points_from_pcts
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.mock import mock_bio_state, mock_race_state, mock_system_state
from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.overlay.session import (
    SessionCoordinator,
    build_session_key,
    overlay_mode_from_session_type,
)
from irswitch.overlay.settings import OverlaySettings
from irswitch.overlay.tape import OverlaySessionTape
from irswitch.race.context import RaceContextAnalyzer
from irswitch.race.timing import CrossingDetector, SegmentReferenceTracker, TimingStore
from irswitch.race.timing.points import default_sectors
from irswitch.sampling.scheduler import SamplingScheduler, resolve_component_hz
from irswitch.server.task_registry import TaskRegistry
from irswitch.util.logging import get_runtime_log_level

logger = logging.getLogger(__name__)

OverlayMode = Literal["live", "mock", "replay"]


class OverlayRuntime:
    def __init__(
        self,
        get_config: Callable[[], AppConfig | None],
        reader: Any,
        bus: OverlayBus,
        *,
        mode: OverlayMode = "live",
        replay_path: str | None = None,
        registry: TaskRegistry | None = None,
    ) -> None:
        self._get_config = get_config
        self._reader = reader
        self.bus = bus
        self.mode = mode
        self._replay_path = replay_path
        self._registry = registry or TaskRegistry()
        self.manager: EventManager = EventManager()
        self.manager_v2: EventManagerV2 | None = None
        overlay = self._overlay_settings()
        self._init_managers(overlay)
        self.engine = EventEngine(overlay)
        self._timing_detector = CrossingDetector(points=default_sectors())
        self._timing_store = TimingStore()
        self._segment_ref = SegmentReferenceTracker()
        self._sector_sig: tuple[str, ...] | None = None
        self._register_timing_emitters(overlay)
        self._register_t4_emitters(overlay)
        self.analyzer = RaceContextAnalyzer(overlay.battle)
        self.session = SessionCoordinator()
        self.session.add_reset_hook(self.analyzer.reset)
        self.session.add_reset_hook(self._reset_event_pipeline)
        self.session.add_reset_hook(self._reset_timing)
        self.session.add_reset_hook(self._segment_ref.reset)
        self._bio: Any = None
        self._system: Any = None
        self._origin = time.monotonic()
        self._prev_bio_status: str | None = None
        self._pending_envelopes: list[dict[str, Any]] = []
        self._tape = OverlaySessionTape()
        self._tape_decision_cursor = 0
        self._commentary_tape_cursor = 0
        self._stories_sig: tuple[tuple[object, ...], ...] | None = None
        self._last_race = RaceState()
        self._hud_live = False
        self._running = False
        self._event_fanout = EventFanout()
        self.commentary = self._build_commentary(overlay)
        self.in_car = InCarDetector()
        self.session_briefs = SessionBriefsDetector()
        self._rebuild_event_fanout()
        self.session.add_reset_hook(self._reset_commentary)
        self.session.add_reset_hook(self.in_car.reset)
        self.session.add_reset_hook(self.session_briefs.reset)

    def _init_managers(self, overlay: OverlaySettings) -> None:
        if overlay.event_engine.v2_payload:
            self.manager_v2 = EventManagerV2(overlay.events)
            self.manager = self.manager_v2.legacy
        else:
            self.manager_v2 = None
            self.manager = EventManager(overlay.events)

    def _session_id(self, state: RaceState) -> str:
        sid = state.subsession_id or "unknown"
        num = state.session_num if state.session_num is not None else 0
        return f"{sid}:{num}"

    def _reset_event_pipeline(self) -> None:
        """Drop active overlay stories on session/track change (Spec §21)."""
        overlay = self._overlay_settings()
        self._init_managers(overlay)
        self.engine = EventEngine(overlay)
        self._register_timing_emitters(overlay)
        self._register_t4_emitters(overlay)
        self.bus.set_active_events([])
        self.bus.set_active_stories_v4([])
        self._tape_decision_cursor = 0
        self._commentary_tape_cursor = 0
        self._stories_sig = None

    def _register_timing_emitters(self, overlay: OverlaySettings) -> None:
        """Attach T2 practice/quali emitters when feature flags are enabled."""
        if overlay.event_engine.practice or overlay.event_engine.quali_projection:
            from irswitch.events.sector_split import SectorBestEmitter, SectorSplitEmitter

            self.engine.register(
                SectorSplitEmitter(
                    self._timing_store,
                    overlay.events,
                    overlay.events.priorities,
                )
            )
            self.engine.register(
                SectorBestEmitter(
                    self._timing_store,
                    overlay.events,
                    overlay.events.priorities,
                )
            )
        if overlay.event_engine.practice:
            from irswitch.events.practice import PracticeEmitter
            from irswitch.events.target_locked import TargetLockedEmitter

            self.engine.register(
                PracticeEmitter(
                    self._timing_store,
                    self._segment_ref,
                    overlay.events,
                    overlay.events.priorities,
                )
            )
            self.engine.register(
                TargetLockedEmitter(overlay.events, overlay.events.priorities),
            )
        if overlay.event_engine.quali_projection:
            from irswitch.events.quali import QualiEmitter

            self.engine.register(
                QualiEmitter(
                    self._timing_store,
                    self._segment_ref,
                    overlay.events,
                    overlay.events.priorities,
                )
            )

    def _register_t4_emitters(self, overlay: OverlaySettings) -> None:
        """Attach T4 pit story / HR pressure emitters when feature flags are enabled."""
        pri = overlay.events.priorities
        if overlay.event_engine.pit_story:
            from irswitch.events.pit_story import PitStoryEmitter

            self.engine.register(PitStoryEmitter(pri))
        if overlay.event_engine.hr_pressure:
            from irswitch.events.hr_pressure import HrPressureEmitter

            self.engine.register(HrPressureEmitter(pri))

    def _reset_timing(self) -> None:
        self._timing_detector.reset()
        self._timing_store.reset()
        self._sector_sig = None

    def _apply_sector_points(self, snap: TelemetrySnapshot) -> None:
        points = resolve_sector_points_from_pcts(snap.sector_start_pcts)
        sig = tuple(f"{p.id}:{p.lap_dist_pct:.6f}" for p in points)
        if sig == self._sector_sig:
            return
        self._timing_detector = CrossingDetector(points=points)
        self._timing_store.reset()
        self._sector_sig = sig

    def _tape_debug_enabled(self) -> bool:
        """Commentary / LLM polish tape rows only while runtime log level is DEBUG."""
        return get_runtime_log_level() == "DEBUG"

    def _llm_polish_tape_hook(self, record: dict[str, Any]) -> None:
        if not self._tape_debug_enabled() or self.mode == "replay":
            return
        self._tape.record_llm_polish(record, time.monotonic(), self._last_race)

    def _build_commentary(self, overlay: OverlaySettings) -> CommentaryDirector | None:
        """Load the sequence graph once. Fail-soft if the JSON is broken."""
        try:
            return CommentaryDirector.from_defaults(
                overlay.commentary,
                language=overlay.language,
                sink=build_tts_sink(
                    overlay.commentary,
                    on_polish_debug=self._llm_polish_tape_hook,
                ),
            )
        except Exception:
            logger.warning("commentary graph failed to load", exc_info=True)
            return None

    def _apply_commentary_sink_settings(self, overlay: OverlaySettings) -> None:
        if self.commentary is None:
            return
        sink = self.commentary.sink
        if isinstance(sink, ProcessTtsSink):
            sink.settings = overlay.commentary
            sink.on_polish_debug = (
                self._llm_polish_tape_hook if overlay.commentary.llm_polish else None
            )

    def _rebuild_event_fanout(self) -> None:
        """Register peer consumers after accepted envelopes (commentary today)."""
        self._event_fanout.clear()
        if self.commentary is not None:
            self._event_fanout.register(CommentaryEventConsumer(self._observe_commentary))

    def _dispatch_speech_envelopes(self, envelopes: list[EventEnvelope], now: float) -> None:
        """Fan-out speech envelopes to peer consumers (not a HUD→commentary chain)."""
        self._event_fanout.emit(envelopes, now=now)

    def _reset_commentary(self) -> None:
        overlay = self._overlay_settings()
        if self.commentary is None:
            self.commentary = self._build_commentary(overlay)
            self._rebuild_event_fanout()
            return
        self.commentary.settings = overlay.commentary
        self.commentary.language = overlay.language
        self.commentary.sink = build_tts_sink(
            overlay.commentary,
            on_polish_debug=self._llm_polish_tape_hook,
        )
        self.commentary.reset()
        self._commentary_tape_cursor = 0
        self.in_car.reset()
        self.session_briefs.reset()
        self._rebuild_event_fanout()

    def _tick_commentary_scheduler(self, now: float) -> None:
        """Flush deferred speech / silence watchdog once per race frame."""
        if self.commentary is None:
            return
        overlay = self._overlay_settings()
        if not overlay.commentary.enabled:
            return
        try:
            self.commentary.settings = overlay.commentary
            self.commentary.tick(now, self.bus.bio)
        except Exception:
            logger.warning("commentary scheduler tick failed", exc_info=True)

    def _observe_commentary(self, envelopes: list[EventEnvelope], now: float):
        """Observe envelopes; return the newest decision dict if any were recorded."""
        if not envelopes or self.commentary is None:
            return None
        overlay = self._overlay_settings()
        self._apply_commentary_sink_settings(overlay)
        before = len(self.commentary.decisions())
        try:
            self.commentary.observe(
                envelopes,
                self.bus.bio,
                now,
                enabled=overlay.commentary.enabled,
                language=overlay.language,
            )
        except Exception:
            logger.warning("commentary observe failed", exc_info=True)
            return None
        if len(self.commentary.decisions()) == before:
            return None
        # Tape rows are drained via _drain_commentary_tape (DEBUG-gated).
        decisions = self.commentary.decisions(1)
        return decisions[-1] if decisions else None

    def _observe_in_car(self, state: RaceState, now: float) -> None:
        try:
            envelope = self.in_car.tick(state, now)
        except Exception:
            logger.warning("in-car detector failed", exc_info=True)
            return
        if envelope is not None:
            self._observe_commentary([envelope], now)

    def _observe_session_briefs(self, state: RaceState, now: float) -> bool:
        """Emit at most one session brief. True when spoken (defer in_car)."""
        overlay = self._overlay_settings()
        data = self._session_brief_data()
        try:
            envelope = self.session_briefs.tick(
                state,
                data,
                now,
                locale=overlay.language,
            )
        except Exception:
            logger.warning("session briefs detector failed", exc_info=True)
            return False
        if envelope is None:
            return False
        decision = self._observe_commentary([envelope], now)
        if decision is None:
            # No decision row (commentary object missing) — consume to avoid spin.
            self.session_briefs.acknowledge(envelope.event_type)
            return False
        reason = str(decision.get("reason") or "")
        # Retry next frame when the voice path was only temporarily busy.
        if reason in {"busy", "global_cooldown"}:
            return False
        self.session_briefs.acknowledge(envelope.event_type)
        return str(decision.get("action") or "") == "spoken"

    def _session_brief_data(self) -> dict[str, object] | None:
        """Raw SessionInfo/telemetry mapping for H1/H2/H3 extractors."""
        reader = self._reader
        getter = getattr(reader, "last_telemetry_data", None)
        if not callable(getter):
            return None
        try:
            data = getter()
        except Exception:
            logger.debug("last_telemetry_data failed", exc_info=True)
            return None
        if isinstance(data, dict) and data:
            return data
        return None

    def _observe_commentary_sidecars(self, state: RaceState, now: float) -> None:
        """Run session briefs then in_car without starving either path.

        Prefer speaking an early session intro before seating. When a brief
        speaks this frame, defer ``ENTER_CAR`` to the next tick so in_car is
        not marked announced while the director is busy.
        """
        spoken_brief = self._observe_session_briefs(state, now)
        if spoken_brief:
            return
        self._observe_in_car(state, now)

    def _observe_timing(self, snap: TelemetrySnapshot) -> None:
        """Ingest player crossings into the timing store (Practice/Quali only)."""
        if snap.session_state in (5, 6):
            return
        mode = overlay_mode_from_session_type(snap.session_type)
        if mode not in {"PRACTICE", "QUALIFYING"}:
            return
        self._apply_sector_points(snap)
        if snap.player_car_idx is None or snap.player_lap_dist_pct is None:
            return
        lap_number = snap.lap_completed if snap.lap_completed is not None else snap.lap
        quality = snap.data_quality if snap.data_quality else "ok"
        valid = quality == "ok" and snap.connected
        for event in self._timing_detector.update(
            car_id="player",
            lap_number=lap_number,
            lap_dist_pct=snap.player_lap_dist_pct,
            timestamp=snap.timestamp,
        ):
            self._timing_store.ingest_crossing(
                event,
                cumulative_lap_time=snap.current_lap_time,
                valid_at_crossing=valid,
                data_quality=quality,
            )

    def _overlay_settings(self) -> OverlaySettings:
        cfg = self._get_config()
        if cfg is None:
            return OverlaySettings()
        return cfg.overlay

    def _idle_when_disconnected(self, state: RaceState) -> bool:
        """Blank live HUD when iRacing telemetry is gone. True → skip emitters."""
        if state.connected:
            self._hud_live = True
            return False
        if self._hud_live:
            self._reset_event_pipeline()
            self._hud_live = False
        else:
            self.bus.set_active_events([])
            self.bus.set_active_stories_v4([])
        return True

    def _race_hz(self) -> float:
        s = self._overlay_settings().sampling
        return resolve_component_hz(s.default_hz, s.race_hz)

    def _system_hz(self) -> float:
        s = self._overlay_settings().sampling
        return resolve_component_hz(s.default_hz, s.system_hz)

    async def run(self) -> None:
        overlay = self._overlay_settings()
        if not overlay.enabled:
            logger.info("Overlay pipeline disabled")
            while True:
                await asyncio.sleep(1.0)
                if self._overlay_settings().enabled:
                    break

        if self.mode == "replay" and self._replay_path:
            from irswitch.overlay.replay import OverlayReplayer

            logger.info("Overlay replay: %s", self._replay_path)
            self._running = True
            try:
                await OverlayReplayer(self._replay_path, self.bus).run()
            finally:
                self._running = False
            return

        self._running = True
        self._registry.spawn(
            "overlay_race", SamplingScheduler("race", self._race_hz, self._tick_race).run()
        )
        self._registry.spawn(
            "overlay_system", SamplingScheduler("system", self._system_hz, self._tick_system).run()
        )
        self._registry.spawn("overlay_flush", self._flush_loop())
        if self.mode != "mock":
            self._registry.spawn("overlay_bio", self._run_bio())
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self._running = False
            self._tape.close()
            await self._registry.cancel_all()
            raise

    async def _flush_loop(self) -> None:
        while True:
            try:
                for envelope in self._pending_envelopes:
                    await self._publish(envelope, time.monotonic())
                self._pending_envelopes.clear()
                await self.bus.flush_state()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Overlay flush failed", exc_info=True)
            await asyncio.sleep(0.15)

    async def _tick_race(self) -> None:
        now = time.monotonic()
        if self.mode == "mock":
            state = mock_race_state(now - self._origin)
            self.bus.set_bio(mock_bio_state(now - self._origin))
            self.session.observe(
                session_key=build_session_key(
                    subsession_id="mock",
                    session_num=0,
                    track_id="mock",
                ),
                connected=True,
                now=now,
            )
        else:
            snap = await self._read_telemetry()
            self.session.observe(
                session_key=build_session_key(
                    subsession_id=snap.subsession_id,
                    session_num=snap.session_num,
                    track_id=snap.track_id,
                ),
                connected=snap.connected,
                now=now,
            )
            self._observe_timing(snap)
            try:
                state = self.analyzer.analyze(snap)
            except Exception:
                logger.warning("RaceContextAnalyzer failed", exc_info=True)
                state = RaceState(connected=False)
        self.bus.set_race(state)
        self._last_race = state
        self._sync_tape(state, now)
        self._observe_commentary_sidecars(state, now)
        self._tick_commentary_scheduler(now)
        self._drain_commentary_tape(now)
        if self._idle_when_disconnected(state):
            return
        if self.session.in_warmup(now):
            # Suppress trend/semantic emitters during reconnect warm-up; still publish state.
            self.bus.set_active_events(self.manager.active_events())
            return
        await self._emit_from_race(state, now)

    async def _read_telemetry(self) -> TelemetrySnapshot:
        read_fn = getattr(self._reader, "read_telemetry", None)
        if not callable(read_fn):
            return TelemetrySnapshot.disconnected(time.monotonic())
        try:
            result = read_fn()
            if inspect.isawaitable(result):
                snap = await result
            else:
                snap = result
            if isinstance(snap, TelemetrySnapshot):
                return snap
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("read_telemetry failed", exc_info=True)
        return TelemetrySnapshot.disconnected(time.monotonic())

    async def _emit_from_race(self, state: RaceState, now: float) -> None:
        try:
            candidates = self.engine.tick(state, now, self.bus.bio)
        except Exception:
            logger.warning("EventEngine tick failed", exc_info=True)
            return
        if self.manager_v2 is not None:
            self.manager_v2.set_session_id(self._session_id(state))
            self.manager_v2.update_pit_state(bool(state.on_pit_road), now)
            for candidate in candidates:
                race_event, envelopes = self.manager_v2.submit(
                    candidate, now, mode=state.overlay_mode
                )
                for wire in self.manager_v2.publish_wire(envelopes, race_event):
                    await self._publish(wire, now)
                self._dispatch_speech_envelopes(
                    merge_speech_envelopes(race_event, envelopes, now=now, mode=state.overlay_mode),
                    now,
                )
            for race_event, envelopes in self.manager_v2.tick(now, mode=state.overlay_mode):
                for wire in self.manager_v2.publish_wire(envelopes, race_event):
                    await self._publish(wire, now)
                self._dispatch_speech_envelopes(envelopes, now)
            self.bus.set_active_events(self.manager_v2.active_events())
            self.bus.set_active_stories_v4(self.manager_v2.active_stories_v4())
            self._drain_tape_side(now)
            self._drain_commentary_tape(now)
            return
        for candidate in candidates:
            event = self.manager.submit(candidate, now)
            if event is not None:
                await self._publish(event.to_envelope(), now)
                speech = speech_envelope_from_race_event(event, now=now, mode=state.overlay_mode)
                if speech is not None:
                    self._dispatch_speech_envelopes([speech], now)
        for expired in self.manager.tick(now):
            await self._publish(expired.to_envelope(), now)
        self.bus.set_active_events(self.manager.active_events())
        self._drain_commentary_tape(now)

    def _sync_tape(self, state: RaceState, now: float) -> None:
        if self.mode == "replay":
            return
        self._tape.observe(state, now, self._overlay_settings())

    async def _publish(self, envelope: dict[str, Any], now: float) -> None:
        if self.mode != "replay":
            self._tape.record_event(envelope, now, self._last_race)
        await self.bus.publish_event(envelope)

    def _drain_tape_side(self, now: float) -> None:
        if self.mode == "replay" or self.manager_v2 is None:
            return
        entries = self.manager_v2.decisions.to_list()
        if len(entries) < self._tape_decision_cursor:
            self._tape_decision_cursor = 0
        for entry in entries[self._tape_decision_cursor :]:
            self._tape.record_decision(entry, now, self._last_race)
        self._tape_decision_cursor = len(entries)
        stories = self.manager_v2.active_stories_v4()
        sig = tuple(
            (item.get("eventType"), item.get("phase"), item.get("correlationId"))
            for item in stories
        )
        if sig != self._stories_sig:
            if self._stories_sig is None and not sig:
                self._stories_sig = sig
                return
            self._stories_sig = sig
            self._tape.record_stories(stories, now, self._last_race)

    def _drain_commentary_tape(self, now: float) -> None:
        if not self._tape_debug_enabled() or self.mode == "replay" or self.commentary is None:
            return
        decisions = self.commentary.decisions()
        if len(decisions) < self._commentary_tape_cursor:
            self._commentary_tape_cursor = 0
        for entry in decisions[self._commentary_tape_cursor :]:
            self._tape.record_commentary(entry, now, self._last_race)
        self._commentary_tape_cursor = len(decisions)

    async def _tick_system(self) -> None:
        overlay = self._overlay_settings()
        if self.mode == "mock":
            self.bus.set_system(mock_system_state(time.monotonic() - self._origin))
            return
        if not overlay.system_info.enabled:
            return
        if self._system is None:
            from irswitch.system.provider import SystemInfoProvider

            self._system = SystemInfoProvider(overlay.system_info, overlay.sampling)
        else:
            self._system.apply_settings(overlay.system_info, overlay.sampling)
        fps = self.bus.race.fps
        ft = self.bus.race.frametime_ms
        try:
            state = await asyncio.to_thread(self._system.sample, fps=fps, frametime_ms=ft)
        except Exception:
            logger.warning("System info sample failed", exc_info=True)
            return
        self.bus.set_system(state)

    async def _run_bio(self) -> None:
        overlay = self._overlay_settings()
        if not overlay.heart_rate.enabled:
            return
        from irswitch.bio.provider import BleHeartRateProvider

        def _on_state(bio_state: Any) -> None:
            prev = self._prev_bio_status
            self._prev_bio_status = bio_state.status
            self.bus.set_bio(bio_state)
            if prev in {"connected"} and bio_state.status in {"disconnected", "reconnecting"}:
                now = time.monotonic()
                if self.manager_v2 is not None:
                    race_event, envelopes = self.manager_v2.inject("ble_lost", now)
                    for wire in self.manager_v2.publish_wire(envelopes, race_event):
                        self._pending_envelopes.append(wire)
                    self.bus.set_active_events(self.manager_v2.active_events())
                    self.bus.set_active_stories_v4(self.manager_v2.active_stories_v4())
                else:
                    event = self.manager.inject("ble_lost", now)
                    if event is not None:
                        self._pending_envelopes.append(event.to_envelope())
                        self.bus.set_active_events(self.manager.active_events())

        self._bio = BleHeartRateProvider(overlay.heart_rate, overlay.sampling, on_state=_on_state)
        await self._bio.run()

    async def stop(self) -> None:
        self._running = False
        self._tape.close()
        await self._registry.cancel_all()
        if self._bio is not None:
            await self._bio.stop()

    def status_snapshot(self, now: float | None = None) -> dict[str, Any]:
        """Public read-only overlay status for dashboards. No side effects.

        Aggregates config (``enabled``) with live runtime facts and the nested
        commentary / tape / bio / system summaries, so callers never need
        ``_``-prefixed attributes. ``now`` is monotonic seconds. Sysinfo
        ``degraded`` needs LHM knowledge and stays with the sysinfo/admin lane.
        """
        now = time.monotonic() if now is None else now
        try:
            overlay = self._overlay_settings()
        except Exception:
            logger.debug("Overlay settings unavailable for snapshot", exc_info=True)
            overlay = OverlaySettings()
        enabled = bool(getattr(overlay, "enabled", False))
        running = self._running
        if not enabled:
            status = "disabled"
        elif running:
            status = "running"
        else:
            status = "idle"
        return {
            "enabled": enabled,
            "available": True,
            "running": running,
            "mode": self.mode,
            "status": status,
            "tasks": len(self._registry),
            "commentary": self._commentary_status(overlay, now),
            "tape": self._tape_status(overlay),
            "bio": self._bio_status(overlay),
            "system": self._system_status(overlay),
        }

    def _commentary_status(self, overlay: OverlaySettings, now: float) -> dict[str, Any]:
        enabled = False
        try:
            enabled = bool(overlay.commentary.enabled)
            director = self.commentary
            if director is not None:
                return director.status_snapshot(now, enabled=enabled)
        except Exception:
            logger.debug("Commentary status snapshot failed", exc_info=True)
        return {
            "enabled": enabled,
            "available": False,
            "busy": False,
            "busyUntil": 0.0,
            "status": "disabled" if not enabled else "idle",
            "lastSpokeAt": None,
        }

    def _tape_status(self, overlay: OverlaySettings) -> dict[str, Any]:
        enabled = False
        tape: dict[str, Any] = {
            "available": False,
            "pathOpen": False,
            "path": None,
            "sessionKey": None,
        }
        try:
            enabled = bool(overlay.tape.enabled)
            tape = self._tape.status_snapshot()
        except Exception:
            logger.debug("Tape status snapshot failed", exc_info=True)
        if not enabled:
            status = "disabled"
        elif tape.get("pathOpen"):
            status = "recording"
        else:
            status = "idle"
        return {"enabled": enabled, "status": status, **tape}

    def _bio_status(self, overlay: OverlaySettings) -> dict[str, Any]:
        enabled = False
        try:
            enabled = bool(overlay.heart_rate.enabled)
            provider = self._bio
            if provider is not None:
                snapshot = dict(provider.status_snapshot())
                snapshot["available"] = True
                if not enabled:
                    snapshot.update({"enabled": False, "status": "disabled", "connected": False})
                return snapshot
            state = self.bus.bio
            return {
                "enabled": enabled,
                "available": False,
                "status": str(state.status or "disconnected") if enabled else "disabled",
                "connected": bool(enabled and state.connected),
                "deviceName": state.device_name,
                "bpm": state.bpm,
                "hrState": state.state,
                "source": overlay.heart_rate.source,
                "deviceFilter": overlay.heart_rate.device,
            }
        except Exception:
            logger.debug("Bio status snapshot failed", exc_info=True)
        return {
            "enabled": enabled,
            "available": False,
            "status": "disabled" if not enabled else "disconnected",
            "connected": False,
            "deviceName": None,
            "bpm": None,
            "hrState": "unknown",
        }

    def _system_status(self, overlay: OverlaySettings) -> dict[str, Any]:
        try:
            settings = overlay.system_info
            enabled = bool(settings.enabled)
            available = self._system is not None
            if not enabled:
                status = "disabled"
            elif available:
                status = "sampling"
            else:
                status = "idle"
            return {
                "enabled": enabled,
                "available": available,
                "status": status,
                "cpuEnabled": bool(settings.cpu_enabled),
                "gpuEnabled": bool(settings.gpu_enabled),
                "memoryEnabled": bool(settings.memory_enabled),
            }
        except Exception:
            logger.debug("System status snapshot failed", exc_info=True)
        return {"enabled": False, "available": False, "status": "disabled"}
