"""Overlay runtime: sampling tasks, event engine, mock/replay. Fail-soft."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any, Literal

from irswitch.config import AppConfig
from irswitch.events.engine import EventEngine
from irswitch.events.manager import EventManager
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.mock import mock_bio_state, mock_race_state, mock_system_state
from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.overlay.session import SessionCoordinator, build_session_key
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.context import RaceContextAnalyzer
from irswitch.race.timing import CrossingDetector, SegmentReferenceTracker, TimingStore
from irswitch.sampling.scheduler import SamplingScheduler, resolve_component_hz
from irswitch.server.task_registry import TaskRegistry

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
        self._register_timing_emitters(overlay)
        self.analyzer = RaceContextAnalyzer(overlay.battle)
        self.session = SessionCoordinator()
        self.session.add_reset_hook(self.analyzer.reset)
        self.session.add_reset_hook(self._reset_event_pipeline)
        self.session.add_reset_hook(self._reset_timing)
        self._timing_detector = CrossingDetector()
        self._timing_store = TimingStore()
        self._segment_ref = SegmentReferenceTracker()
        self.session.add_reset_hook(self._segment_ref.reset)
        self._bio: Any = None
        self._system: Any = None
        self._origin = time.monotonic()
        self._prev_bio_status: str | None = None
        self._pending_envelopes: list[dict[str, Any]] = []

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
        self.bus.set_active_events([])
        self.bus.set_active_stories_v4([])

    def _register_timing_emitters(self, overlay: OverlaySettings) -> None:
        """Attach T2 practice/quali emitters when feature flags are enabled."""
        if overlay.event_engine.practice:
            from irswitch.events.practice import PracticeEmitter

            self.engine.register(
                PracticeEmitter(
                    self._timing_store,
                    self._segment_ref,
                    overlay.events,
                    overlay.events.priorities,
                )
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

    def _reset_timing(self) -> None:
        self._timing_detector.reset()
        self._timing_store.reset()

    def _observe_timing(self, snap: TelemetrySnapshot) -> None:
        """Ingest player crossings into the timing store (no semantic events yet)."""
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
            await OverlayReplayer(self._replay_path, self.bus).run()
            return

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
            await self._registry.cancel_all()
            raise

    async def _flush_loop(self) -> None:
        while True:
            try:
                for envelope in self._pending_envelopes:
                    await self.bus.publish_event(envelope)
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
            candidates = self.engine.tick(state, now)
        except Exception:
            logger.warning("EventEngine tick failed", exc_info=True)
            return
        if self.manager_v2 is not None:
            self.manager_v2.set_session_id(self._session_id(state))
            for candidate in candidates:
                race_event, envelope = self.manager_v2.submit(
                    candidate, now, mode=state.overlay_mode
                )
                wire = self.manager_v2.publish_wire(envelope, race_event)
                if wire is not None:
                    await self.bus.publish_event(wire)
            for race_event, envelope in self.manager_v2.tick(now, mode=state.overlay_mode):
                wire = self.manager_v2.publish_wire(envelope, race_event)
                if wire is not None:
                    await self.bus.publish_event(wire)
            self.bus.set_active_events(self.manager_v2.active_events())
            self.bus.set_active_stories_v4(self.manager_v2.active_stories_v4())
            return
        for candidate in candidates:
            event = self.manager.submit(candidate, now)
            if event is not None:
                await self.bus.publish_event(event.to_envelope())
        for expired in self.manager.tick(now):
            await self.bus.publish_event(expired.to_envelope())
        self.bus.set_active_events(self.manager.active_events())

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
                    race_event, envelope = self.manager_v2.inject("ble_lost", now)
                    wire = self.manager_v2.publish_wire(envelope, race_event)
                    if wire is not None:
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
        await self._registry.cancel_all()
        if self._bio is not None:
            await self._bio.stop()
