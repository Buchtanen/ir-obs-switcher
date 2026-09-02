"""Race composition runtime: one producer and independent N12 consumers."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from irswitch.commentary.bridge import merge_speech_envelopes, speech_envelope_from_race_event
from irswitch.commentary.consumer import CommentaryConsumer
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.in_car import InCarDetector
from irswitch.commentary.session_briefs import SessionBriefsDetector
from irswitch.commentary.tts import build_tts_sink
from irswitch.config import AppConfig
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.engine import EventEngine
from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.events.manager import EventManager
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.events.replay import is_n12_replay, load_n12_replay
from irswitch.events.stream import (
    ConfigUpdate,
    FillerResult,
    SessionSequenceAllocator,
    canonical_json_bytes,
    freeze_config,
)
from irswitch.events.worker import WorkerSupervisor
from irswitch.iracing.sectors import resolve_sector_points_from_pcts
from irswitch.iracing.session_context import extract_session_context
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer
from irswitch.overlay.mock import mock_bio_state, mock_race_state, mock_system_state
from irswitch.overlay.models import BioState, RaceState, SystemState, TelemetrySnapshot
from irswitch.overlay.session import (
    SessionCoordinator,
    build_session_key,
    overlay_mode_from_session_type,
)
from irswitch.overlay.settings import OverlaySettings
from irswitch.overlay.tape import OverlaySessionTape
from irswitch.race.context import RaceContextAnalyzer
from irswitch.race.driver_facts import DriverFactLedger
from irswitch.race.grid_story import QUALI_RECAP
from irswitch.race.observer import RaceObserver
from irswitch.race.pipeline import AcceptedRecord, RacePipeline, build_situation_payload
from irswitch.race.run import RunClock
from irswitch.race.timing import CrossingDetector, SegmentReferenceTracker, TimingStore
from irswitch.race.timing.points import default_sectors
from irswitch.race.watcher_log import WatcherLog
from irswitch.sampling.scheduler import SamplingScheduler, resolve_component_hz
from irswitch.server.task_registry import TaskRegistry
from irswitch.util.logging import get_runtime_log_level

logger = logging.getLogger(__name__)

OverlayMode = Literal["live", "mock", "replay"]  # pipeline input; not HUD overlay_mode

_SITUATION_SUPPRESS_TYPES = frozenset(
    {
        "HUNTING",
        "APPROACH",
        "ATTACK_RANGE",
        "SIDE_BY_SIDE",
        "HUNTED",
        "BATTLE_FOR_POSITION",
        "INCIDENT",
        "INCIDENT_AFTERMATH",
        "FINAL_LAP",
        "FINISH",
        "SESSION_CHECKERED",
        "SESSION_FLAG",
        "SESSION_WRAP",
        "SESSION_INTRO_RACE",
        "ENTER_CAR",
        "STREAM_START",
        "PIT_ENTRY",
        "PIT_LANE",
        "PIT_STOPPED",
        "PIT_RELEASED",
        "PIT_EXIT",
        "PIT_OUTCOME",
    }
)


class RaceRuntime:
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
        self._sequence_allocator = SessionSequenceAllocator()
        self._event_fanout = AsyncEventFanout()
        self._overlay_subscription = self._event_fanout.subscribe("overlay", capacity=64)
        self._commentary_subscription = self._event_fanout.subscribe("commentary", capacity=64)
        self.pipeline = RacePipeline(
            self._event_fanout,
            sequence_allocator=self._sequence_allocator,
        )
        self.manager: EventManager = EventManager()
        self.manager_v2: EventManagerV2 | None = None
        overlay = self._overlay_settings()
        self._config_generation = 0
        self._config_signature: bytes | None = None
        self._init_managers(overlay)
        self.engine = EventEngine(overlay)
        self._timing_detector = CrossingDetector(points=default_sectors())
        self._timing_store = TimingStore()
        self._segment_ref = SegmentReferenceTracker()
        self._sector_sig: tuple[str, ...] | None = None
        self._timing_after_session = False
        self._register_timing_emitters(overlay)
        self._register_t4_emitters(overlay)
        self.analyzer = RaceContextAnalyzer(overlay.battle)
        self.session = SessionCoordinator()
        self.run_clock = RunClock()
        self.session.add_reset_hook(self.analyzer.reset)
        self.session.add_reset_hook(self._reset_event_pipeline)
        self.session.add_reset_hook(self._reset_timing)
        self.session.add_reset_hook(self._segment_ref.reset)
        self._bio: Any = None
        self._system: Any = None
        self._origin = time.monotonic()
        self._prev_bio_status: str | None = None
        self._pending_derived_speech: list[EventEnvelope] = []
        self._pending_stream_records: list[AcceptedRecord] = []
        self._last_situation_phase: str | None = None
        self._last_situation_fact_at = 0.0
        self._tape = OverlaySessionTape()
        self._tape_decision_cursor = 0
        self._stories_sig: tuple[tuple[object, ...], ...] | None = None
        self._last_race = RaceState()
        self._last_bio = BioState()
        self._last_system = SystemState()
        self._last_snapshot = TelemetrySnapshot()
        self._hud_live = False
        self._running = False
        self._replay_writer: Any = None
        self.race_observer = RaceObserver(settings=overlay.race_observer)
        self.driver_facts = DriverFactLedger()
        director = self._build_commentary(overlay)
        if director is None:
            director = CommentaryDirector.from_defaults(
                overlay.commentary, language=overlay.language
            )
        director.watcher_log = WatcherLog()
        self.commentary_consumer = CommentaryConsumer(
            self._commentary_subscription,
            director,
            self._commentary_settings,
            decision_hook=self._record_commentary_decision,
        )
        director.filler_formatter = lambda envelope: self.race_observer.format_filler_text(
            envelope, locale=self._overlay_settings().language
        )
        sink = director.sink
        if hasattr(sink, "on_story_debug"):
            sink.on_story_debug = self._ministory_tape_hook
        previous_spoken = getattr(sink, "on_spoken_text", None)

        def _spoken(text: str) -> None:
            if callable(previous_spoken):
                previous_spoken(text)
            self._tts_final_tape_hook(text)

        if hasattr(sink, "on_spoken_text"):
            sink.on_spoken_text = _spoken
        self._stream_start_emitted = False
        self._commentary_available = True
        self.overlay_consumer = OverlayConsumer(
            self._overlay_subscription,
            self.bus,
            record_event=self._record_overlay_event,
        )
        self._overlay_supervisor = WorkerSupervisor("overlay_consumer", self.overlay_consumer.run)
        self._commentary_supervisor = WorkerSupervisor(
            "commentary_consumer", self.commentary_consumer.run
        )
        self.in_car = InCarDetector()
        self.session_briefs = SessionBriefsDetector()
        self._weekend_track: str | None = None
        self.session.add_reset_hook(self.race_observer.reset_session)
        self.session.add_reset_hook(self.in_car.reset)
        self.session.add_reset_hook(self.session_briefs.reset)
        self.session.add_reset_hook(self.driver_facts.reset)
        self.session.add_reset_hook(self._reset_situation_facts)

    def _init_managers(self, overlay: OverlaySettings) -> None:
        if overlay.event_engine.v2_payload:
            self.manager_v2 = EventManagerV2(
                overlay.events,
                sequence_allocator=self._sequence_allocator,
            )
            self.manager = self.manager_v2.legacy
        else:
            self.manager_v2 = None
            self.manager = EventManager(overlay.events)

    def _session_id(self, state: RaceState) -> str:
        sid = state.subsession_id or "unknown"
        num = state.session_num if state.session_num is not None else 0
        return f"{sid}:{num}"

    @property
    def commentary(self) -> CommentaryDirector | None:
        """Compatibility accessor; ownership stays with CommentaryConsumer."""
        if not self._commentary_available:
            return None
        return self.commentary_consumer.director

    @commentary.setter
    def commentary(self, value: CommentaryDirector | None) -> None:
        if value is None:
            self._commentary_available = False
            return
        self.commentary_consumer.director = value
        self._commentary_available = True

    def _commentary_settings(self):
        overlay = self._overlay_settings()
        return overlay.commentary, overlay.language

    def _publish_config_update_if_changed(self) -> None:
        overlay = self._overlay_settings()
        payload = {
            "generation": self._config_generation + 1,
            "language": overlay.language,
            "commentary": asdict(overlay.commentary),
        }
        signature = canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "generation"}
        )
        if signature == self._config_signature:
            return
        self._config_generation += 1
        payload["generation"] = self._config_generation
        update = ConfigUpdate(
            generation=self._config_generation,
            frozen_config=freeze_config(payload),
            stream_sequence=self._event_fanout.next_stream_sequence(),
        )
        self._event_fanout.publish(update)
        self._config_signature = signature

    def _record_overlay_event(self, envelope: dict[str, Any], now: float) -> None:
        if self.mode != "replay":
            self._tape.record_event(envelope, now, self._last_race)

    def _record_commentary_decision(self, entry: dict[str, Any], now: float) -> None:
        if self._tape_debug_enabled() and self.mode != "replay":
            self._tape.record_commentary(entry, now, self._last_race)

    def _reset_event_pipeline(self) -> None:
        """Drop active overlay stories on session/track change (Spec §21)."""
        overlay = self._overlay_settings()
        self._init_managers(overlay)
        self.engine = EventEngine(overlay)
        self._register_timing_emitters(overlay)
        self._register_t4_emitters(overlay)
        self._pending_derived_speech = []
        self._pending_stream_records = []
        self._tape_decision_cursor = 0
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
        self._timing_after_session = False

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

    def _tts_final_tape_hook(self, text: str) -> None:
        if not self._tape_debug_enabled() or self.mode == "replay":
            return
        if not (text or "").strip():
            return
        self._tape.record_commentary(
            {
                "action": "spoken",
                "reason": "tts_final",
                "text": text,
            },
            time.monotonic(),
            self._last_race,
        )

    def _ministory_tape_hook(self, entry: dict[str, Any]) -> None:
        if not self._tape_debug_enabled() or self.mode == "replay":
            return
        self._tape.record_commentary(entry, time.monotonic(), self._last_race)

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

    def _observe_race_story(
        self,
        snap: TelemetrySnapshot,
        state: RaceState,
        now: float,
    ) -> None:
        """Update RaceObserver story context; fail-soft (never break the race tick)."""
        overlay = self._overlay_settings()
        self.race_observer.apply_settings(overlay.race_observer)
        try:
            self.race_observer.observe(
                snap,
                state,
                now=now,
                telemetry_data=self._session_brief_data(),
            )
            derived = self.race_observer.take_derived_envelopes()
            if derived:
                self._pending_derived_speech.extend(derived)
        except Exception:
            logger.warning("RaceObserver observe failed", exc_info=True)
        self._maybe_emit_stream_start_if_live(now)

    def _maybe_emit_stream_start_if_live(self, now: float) -> None:
        """Speak STREAM_START when OBS is already live at connect (no rising edge)."""
        if getattr(self, "_stream_start_emitted", False):
            return
        try:
            from irswitch.server.metrics import get_metrics

            if get_metrics().stream_started_ts is None:
                return
        except Exception:
            return
        self.notify_obs_stream_started(now)

    def notify_obs_stream_started(self, now: float) -> None:
        """OBS streaming rising edge → commentary-only STREAM_START. Fail-soft."""
        if getattr(self, "_stream_start_emitted", False):
            return
        overlay = self._overlay_settings()
        if not overlay.commentary.stream_start:
            return
        if not overlay.commentary.enabled:
            return
        try:
            from irswitch.commentary.stream_context import make_stream_start_envelope

            self._publish_config_update_if_changed()
            envelope = make_stream_start_envelope(now)
            self.commentary_consumer.note_stream_start_accepted(now)
            self._ensure_context(now)
            self.race_observer.note_accepted([envelope])
            self.pipeline.publish_envelopes(
                [envelope],
                source="stream_start",
                accepted_monotonic_ms=int(time.monotonic() * 1000),
                poll_interval_ms=self._poll_interval_ms(),
            )
            self._stream_start_emitted = True
        except Exception:
            logger.warning("STREAM_START commentary failed", exc_info=True)

    def _reset_commentary(self) -> None:
        """Compatibility hook; N12 config/reset delivery uses typed stream items."""
        overlay = self._overlay_settings()
        self.race_observer.apply_settings(overlay.race_observer)
        self._publish_config_update_if_changed()

    def _collect_in_car(self, state: RaceState, now: float) -> AcceptedRecord | None:
        try:
            envelope = self.in_car.tick(state, now)
        except Exception:
            logger.warning("in-car detector failed", exc_info=True)
            return None
        return AcceptedRecord(envelope, "in_car") if envelope is not None else None

    def _collect_session_brief(self, state: RaceState, now: float) -> AcceptedRecord | None:
        """Accept at most one factual session brief into the shared stream."""
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
            return None
        if envelope is None:
            return None
        # Acceptance and speech budgets are now separate. A factual brief is
        # emitted once; the commentary consumer may defer/skip it independently.
        self.session_briefs.acknowledge(envelope.event_type)
        return AcceptedRecord(envelope, "session_brief")

    def weekend_track(self) -> str | None:
        """Last WeekendInfo display name for YouTube ``Track:`` rewrite."""
        if self._weekend_track:
            return self._weekend_track
        briefs_track = getattr(self.session_briefs, "last_track", None)
        if callable(briefs_track):
            value = briefs_track()
            return value if isinstance(value, str) and value.strip() else None
        if isinstance(briefs_track, str) and briefs_track.strip():
            return briefs_track.strip()
        return None

    def _remember_weekend_track(self) -> None:
        data = self._session_brief_data()
        if not data:
            return
        try:
            ctx = extract_session_context(data)
        except Exception:
            return
        track = ctx.track if ctx is not None else None
        if track:
            self._weekend_track = track

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

    def _empty_hud(self) -> dict[str, Any]:
        return {"active_events": [], "active_stories_v4": []}

    def _current_hud(self) -> dict[str, Any]:
        if self.manager_v2 is not None:
            return {
                "active_events": list(self.manager_v2.active_events()),
                "active_stories_v4": list(self.manager_v2.active_stories_v4()),
            }
        return {
            "active_events": list(self.manager.active_events()),
            "active_stories_v4": [],
        }

    def _poll_interval_ms(self) -> int:
        hz = self._race_hz()
        if hz <= 0:
            return 200
        return max(1, int(1000.0 / hz))

    def _capture_context(
        self, state: RaceState, now: float, *, hud: dict[str, Any] | None = None
    ) -> None:
        overlay = self._overlay_settings()
        telemetry_data = self._session_brief_data()
        self.driver_facts.refresh(
            telemetry_data,
            self._last_snapshot,
            session_id=self._session_id(state),
            observed_monotonic_ms=int(now * 1000),
        )
        self.pipeline.capture_context(
            race=state,
            bio=self._last_bio,
            story=self.race_observer.context,
            telemetry_data=telemetry_data,
            captured_monotonic_ms=int(now * 1000),
            language=overlay.language,
            commentary_enabled=bool(overlay.commentary.enabled),
            config_generation=self._config_generation,
            driver_profiles=self.driver_facts.profiles_snapshot(),
            system=self._last_system,
            hud=self._empty_hud() if hud is None else hud,
            grid_story=bool(overlay.race_observer.grid_story),
        )

    def _reset_situation_facts(self) -> None:
        self._last_situation_phase = None
        self._last_situation_fact_at = 0.0

    def _collect_situation_fact(
        self, state: RaceState, now: float, existing: list[AcceptedRecord]
    ) -> AcceptedRecord | None:
        if state.overlay_mode != "RACE" or not state.connected or state.mute_field:
            return None
        if any(
            record.envelope.priority > 28 or record.envelope.event_type in _SITUATION_SUPPRESS_TYPES
            for record in existing
        ):
            return None
        situation = build_situation_payload(state, self._session_brief_data(), int(now * 1000))
        phase = str(situation.get("race_phase") or "unknown")
        current_lap = situation.get("current_lap")
        due = phase != self._last_situation_phase or now - self._last_situation_fact_at >= 120
        if not due or (phase == "unknown" and current_lap is None):
            return None
        self._last_situation_phase = phase
        self._last_situation_fact_at = now
        envelope = make_envelope(
            event_type="FIELD_FACT",
            phase="RESULT",
            mode="RACE",
            priority=28,
            monotonic_ms=int(now * 1000),
            correlation_id=f"situation:{phase}",
            metrics={
                "current_lap": current_lap,
                "situationPhase": phase,
            },
        )
        return AcceptedRecord(envelope, "filler")

    def _ensure_context(self, now: float) -> None:
        if self.pipeline.context_payload is not None:
            return
        session_id = self._session_id(self._last_race)
        self.pipeline.reset_session(session_id, reason="context_bootstrap")
        self._capture_context(self._last_race, now, hud=self._current_hud())

    def _collect_filler_response(self, now: float) -> AcceptedRecord | None:
        request = self.commentary_consumer.take_filler_request()
        if request is None:
            return None
        if request.session_id != self.pipeline.session_id:
            self.commentary_consumer.complete_filler(FillerResult(request.request_id, "stale"))
            return None
        if int(now * 1000) - request.requested_monotonic_ms > 3_000:
            self.commentary_consumer.complete_filler(FillerResult(request.request_id, "stale"))
            return None
        if not self._overlay_settings().commentary.enabled:
            self.commentary_consumer.complete_filler(FillerResult(request.request_id, "disabled"))
            return None
        envelope = self.race_observer.next_filler_envelope(now, locale=request.locale)
        if envelope is None:
            self.commentary_consumer.complete_filler(FillerResult(request.request_id, "no_fact"))
            return None
        return AcceptedRecord(envelope, "filler")

    def _collect_commentary_sidecars(self, state: RaceState, now: float) -> list[AcceptedRecord]:
        """Normalize direct sidecars into producer records in deterministic order."""
        if any(env.event_type == QUALI_RECAP for env in self._pending_derived_speech):
            return []
        records: list[AcceptedRecord] = []
        brief = self._collect_session_brief(state, now)
        if brief is not None:
            records.append(brief)
            return records
        in_car = self._collect_in_car(state, now)
        if in_car is not None:
            records.append(in_car)
        return records

    def _observe_timing(self, snap: TelemetrySnapshot, *, session_finished: bool = False) -> None:
        """Ingest player crossings (Practice/Quali). Keep the checkered out-lap.

        CoolDown always stops. The tick that becomes player_finished / mute_field
        still ingests, then later ticks skip.
        """
        if snap.session_state not in (5, 6):
            self._timing_after_session = False
        if snap.session_state == 6 or self._timing_after_session:
            self._timing_after_session = True
            return
        mode = overlay_mode_from_session_type(snap.session_type)
        if mode not in {"PRACTICE", "QUALIFYING"}:
            if session_finished:
                self._timing_after_session = True
            return
        self._apply_sector_points(snap)
        if snap.player_car_idx is None or snap.player_lap_dist_pct is None:
            if session_finished:
                self._timing_after_session = True
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
        if session_finished:
            self._timing_after_session = True

    def _overlay_settings(self) -> OverlaySettings:
        cfg = self._get_config()
        if cfg is None:
            return OverlaySettings()
        return cfg.overlay

    def _idle_when_disconnected(self, state: RaceState, now: float | None = None) -> bool:
        """Blank live HUD when iRacing telemetry is gone. True → skip emitters."""
        if state.connected:
            self._hud_live = True
            return False
        if self._hud_live:
            self._reset_event_pipeline()
            self._hud_live = False
        captured = now if now is not None else time.monotonic()
        self._last_race = state
        self._capture_context(state, captured, hud=self._empty_hud())
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
            self._running = True
            try:
                await self._run_replay(Path(self._replay_path))
            finally:
                self._running = False
            return

        self._running = True
        # Subscriptions and workers exist before the producer can publish.
        self._registry.spawn("overlay_consumer", self._overlay_supervisor.run())
        self._registry.spawn("commentary_consumer", self._commentary_supervisor.run())
        self._registry.spawn(
            "race_producer", SamplingScheduler("race", self._race_hz, self._tick_race).run()
        )
        self._registry.spawn(
            "overlay_system", SamplingScheduler("system", self._system_hz, self._tick_system).run()
        )
        if self.mode != "mock":
            self._registry.spawn("overlay_bio", self._run_bio())
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self._running = False
            self._tape.close()
            self._event_fanout.close()
            await self._registry.cancel_all()
            self._close_commentary_sink()
            self.stop_event_capture()
            raise

    async def _run_replay(self, path: Path) -> None:
        if is_n12_replay(path):
            logger.info("N12 replay: %s", path)
            self._registry.spawn("overlay_consumer", self._overlay_supervisor.run())
            self._registry.spawn("commentary_consumer", self._commentary_supervisor.run())
            try:
                await load_n12_replay(path).replay(self._event_fanout)
                await self._drain_consumer_queues()
            finally:
                self._event_fanout.close()
                await self._registry.cancel_all()
                self._close_commentary_sink()
            return
        from irswitch.overlay.replay import OverlayReplayer

        logger.info("Overlay replay: %s", path)
        await OverlayReplayer(str(path), self.bus).run()

    async def _drain_consumer_queues(self, timeout_s: float = 1.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            overlay = self._overlay_subscription.snapshot(producer_stream_sequence=0)
            commentary = self._commentary_subscription.snapshot(producer_stream_sequence=0)
            if overlay.depth == 0 and commentary.depth == 0:
                await asyncio.sleep(0.05)
                return
            await asyncio.sleep(0.02)

    async def _tick_race(self) -> None:
        now = time.monotonic()
        self._publish_config_update_if_changed()
        filler_record = self._collect_filler_response(now)
        if self.mode == "mock":
            state = mock_race_state(now - self._origin)
            self._last_bio = mock_bio_state(now - self._origin)
            self.session.observe(
                session_key=build_session_key(
                    subsession_id="mock",
                    session_num=0,
                    track_id="mock",
                ),
                connected=True,
                now=now,
            )
            self.run_clock.observe(
                self.session.session_key, state.session_time, now=now, connected=state.connected
            )
            state = self.run_clock.apply(state)
        else:
            snap = await self._read_telemetry()
            self._remember_weekend_track()
            self.session.observe(
                session_key=build_session_key(
                    subsession_id=snap.subsession_id,
                    session_num=snap.session_num,
                    track_id=snap.track_id,
                ),
                connected=snap.connected,
                now=now,
            )
            observation = self.run_clock.observe(
                self.session.session_key, snap.session_time, now=now, connected=snap.connected
            )
            if observation == "pending":
                return
            if observation == "restarted":
                self.session.force_reset()
                self.race_observer.narrative.reset_run()
                filler_record = None
                logger.info("Race run restarted epoch=%s", self.run_clock.run_epoch)
            self._apply_sector_points(snap)
            try:
                state = self.analyzer.analyze(snap)
            except Exception:
                logger.warning("RaceContextAnalyzer failed", exc_info=True)
                state = RaceState(connected=False)
            state = self.run_clock.apply(state)
            self._last_snapshot = snap
            self._observe_timing(
                snap, session_finished=bool(state.mute_field or state.session_finished)
            )
            self._observe_race_story(snap, state, now)
        self.pipeline.reset_session(self._session_id(state), reason="session_changed")
        self.pipeline.reset_run(state.run_epoch)
        if self.manager_v2 is not None:
            self.manager_v2.set_run_epoch(state.run_epoch)
        self._last_race = state
        self._sync_tape(state, now)
        if self._idle_when_disconnected(state, now):
            self._pending_derived_speech.clear()
            return
        if self.session.in_warmup(now):
            # Suppress trend/semantic emitters during reconnect warm-up; still publish state.
            self._pending_derived_speech.clear()
            self._capture_context(state, now, hud=self._current_hud())
            return
        records = await self._emit_from_race(state, now)
        for envelope in self._pending_derived_speech:
            records.append(AcceptedRecord(envelope, _derived_source(envelope.event_type)))
        self._pending_derived_speech = []
        if filler_record is not None:
            records.append(filler_record)
        records.extend(self._collect_commentary_sidecars(state, now))
        if self._pending_stream_records:
            records.extend(self._pending_stream_records)
            self._pending_stream_records = []
        situation_fact = self._collect_situation_fact(state, now, records)
        if situation_fact is not None:
            records.append(situation_fact)
        try:
            self.race_observer.note_accepted([record.envelope for record in records])
        except Exception:
            logger.warning("RaceObserver accepted history failed", exc_info=True)
        self._capture_context(state, now, hud=self._current_hud())
        self.pipeline.publish_records(
            records,
            accepted_monotonic_ms=int(time.monotonic() * 1000),
            poll_interval_ms=self._poll_interval_ms(),
        )

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

    async def _emit_from_race(self, state: RaceState, now: float) -> list[AcceptedRecord]:
        records: list[AcceptedRecord] = []
        overlay = self._overlay_settings()
        self.engine.incident.apply_settings(overlay.race_observer)
        try:
            candidates = self.engine.tick(state, now, self._last_bio)
        except Exception:
            logger.warning("EventEngine tick failed", exc_info=True)
            return records
        if self.manager_v2 is not None:
            self.manager_v2.set_session_id(self._session_id(state))
            self.manager_v2.update_pit_state(bool(state.on_pit_road), now)
            for candidate in candidates:
                race_event, envelopes = self.manager_v2.submit(
                    candidate, now, mode=state.overlay_mode
                )
                speech = merge_speech_envelopes(
                    race_event,
                    envelopes,
                    now=now,
                    mode=state.overlay_mode,
                )
                wires = self.manager_v2.publish_wire(envelopes, race_event)
                records.extend(_accepted_records(speech, wires, source="event_engine"))
            for race_event, envelopes in self.manager_v2.tick(now, mode=state.overlay_mode):
                wires = self.manager_v2.publish_wire(envelopes, race_event)
                records.extend(_accepted_records(envelopes, wires, source="event_engine"))
            self._drain_tape_side(now)
            return records
        for candidate in candidates:
            event = self.manager.submit(candidate, now)
            if event is not None:
                wire = event.to_envelope()
                speech_envelope = speech_envelope_from_race_event(
                    event, now=now, mode=state.overlay_mode
                )
                if speech_envelope is None:
                    speech_envelope = make_envelope(
                        event_type=event.name.upper(),
                        phase=event.phase,
                        mode=state.overlay_mode,
                        priority=event.priority,
                        monotonic_ms=int(now * 1000),
                        metrics=dict(event.data),
                        correlation_id=event.name,
                    )
                records.append(AcceptedRecord(speech_envelope, "event_engine", wire))
        for expired in self.manager.tick(now):
            wire = expired.to_envelope()
            envelope = make_envelope(
                event_type=expired.name.upper(),
                phase="EXIT",
                mode=state.overlay_mode,
                priority=expired.priority,
                monotonic_ms=int(now * 1000),
                metrics=dict(expired.data),
                correlation_id=expired.name,
            )
            records.append(AcceptedRecord(envelope, "event_engine", wire))
        return records

    def _sync_tape(self, state: RaceState, now: float) -> None:
        if self.mode == "replay":
            return
        self._tape.observe(state, now, self._overlay_settings())

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

    async def _tick_system(self) -> None:
        overlay = self._overlay_settings()
        if self.mode == "mock":
            self._last_system = mock_system_state(time.monotonic() - self._origin)
            self._capture_context(self._last_race, time.monotonic(), hud=self._current_hud())
            return
        if not overlay.system_info.enabled:
            return
        if self._system is None:
            from irswitch.system.provider import SystemInfoProvider

            self._system = SystemInfoProvider(overlay.system_info, overlay.sampling)
        else:
            self._system.apply_settings(overlay.system_info, overlay.sampling)
        fps = self._last_race.fps
        ft = self._last_race.frametime_ms
        try:
            state = await asyncio.to_thread(self._system.sample, fps=fps, frametime_ms=ft)
        except Exception:
            logger.warning("System info sample failed", exc_info=True)
            return
        self._last_system = state
        self._capture_context(self._last_race, time.monotonic(), hud=self._current_hud())

    async def _run_bio(self) -> None:
        overlay = self._overlay_settings()
        if not overlay.heart_rate.enabled:
            return
        from irswitch.bio.provider import BleHeartRateProvider

        def _on_state(bio_state: Any) -> None:
            prev = self._prev_bio_status
            self._prev_bio_status = bio_state.status
            self._last_bio = bio_state
            now = time.monotonic()
            if prev in {"connected"} and bio_state.status in {"disconnected", "reconnecting"}:
                if self.manager_v2 is not None:
                    race_event, envelopes = self.manager_v2.inject("ble_lost", now)
                    wires = self.manager_v2.publish_wire(envelopes, race_event)
                    speech = merge_speech_envelopes(
                        race_event,
                        envelopes,
                        now=now,
                        mode=self._last_race.overlay_mode,
                    )
                    self._pending_stream_records.extend(
                        _accepted_records(speech, wires, source="event_engine")
                    )
                else:
                    event = self.manager.inject("ble_lost", now)
                    if event is not None:
                        envelope = make_envelope(
                            event_type=event.name.upper(),
                            phase=event.phase,
                            mode=self._last_race.overlay_mode,
                            priority=event.priority,
                            monotonic_ms=int(now * 1000),
                            metrics=dict(event.data),
                            correlation_id=event.name,
                        )
                        self._pending_stream_records.append(
                            AcceptedRecord(envelope, "event_engine", event.to_envelope())
                        )
            self._capture_context(self._last_race, now, hud=self._current_hud())

        self._bio = BleHeartRateProvider(overlay.heart_rate, overlay.sampling, on_state=_on_state)
        await self._bio.run()

    async def stop(self) -> None:
        self._running = False
        self._tape.close()
        self._event_fanout.close()
        try:
            await asyncio.wait_for(self._registry.cancel_all(), timeout=2.0)
        except TimeoutError:
            logger.error("N12 bounded shutdown timed out")
        self._close_commentary_sink()
        self.stop_event_capture()
        if self._bio is not None:
            await self._bio.stop()

    def start_event_capture(
        self,
        path: Path,
        *,
        source_commit: str,
        config_digest: str,
    ) -> None:
        """Start optional N12 replay capture without changing runtime defaults."""
        from irswitch.events.replay import N12ReplayWriter

        self.stop_event_capture()
        overlay = self._overlay_settings()
        self._replay_writer = N12ReplayWriter(
            path,
            source_commit=source_commit,
            config_generation=self._config_generation,
            config_digest=config_digest,
            locale=overlay.language,
        )
        self._event_fanout.set_capture(self._replay_writer.record)

    def stop_event_capture(self) -> None:
        self._event_fanout.set_capture(None)
        writer = self._replay_writer
        self._replay_writer = None
        if writer is not None:
            writer.close()

    def _close_commentary_sink(self) -> None:
        close = getattr(self.commentary_consumer.director.sink, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.warning("commentary sink close failed", exc_info=True)

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
            "eventStream": self._event_fanout.status_snapshot(),
            "eventCapture": {
                "active": self._replay_writer is not None,
                "schema": "n12-replay/1",
            },
            "overlayConsumer": {
                **self.overlay_consumer.status_snapshot(),
                "supervisor": self._overlay_supervisor.status_snapshot(),
            },
            "commentary": self._commentary_status(overlay, now),
            "tape": self._tape_status(overlay),
            "bio": self._bio_status(overlay),
            "system": self._system_status(overlay),
        }

    def _commentary_status(self, overlay: OverlaySettings, now: float) -> dict[str, Any]:
        enabled = False
        try:
            enabled = bool(overlay.commentary.enabled)
            if self.commentary is not None:
                return {
                    **self.commentary_consumer.status_snapshot(now),
                    "supervisor": self._commentary_supervisor.status_snapshot(),
                }
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
            state = self._last_bio
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


def _accepted_records(
    envelopes: list[EventEnvelope],
    wires: list[dict[str, Any]],
    *,
    source: str,
) -> list[AcceptedRecord]:
    normalized = list(envelopes)
    if not normalized:
        normalized = [_envelope_from_wire(wire) for wire in wires]
    records: list[AcceptedRecord] = []
    for index, envelope in enumerate(normalized):
        wire: dict[str, Any] | None = None
        for candidate in wires:
            if candidate.get("eventId") == envelope.event_id:
                wire = candidate
                break
        if wire is None and len(wires) == len(normalized):
            wire = wires[index]
        elif wire is None and len(wires) == 1:
            wire = wires[0]
        records.append(AcceptedRecord(envelope, source, wire))
    return records


def _envelope_from_wire(wire: dict[str, Any]) -> EventEnvelope:
    if wire.get("eventType"):
        return EventEnvelope.from_dict(wire)
    return make_envelope(
        event_type=str(wire.get("name") or "UNKNOWN").upper(),
        phase=str(wire.get("phase") or "RESULT"),
        mode="GENERIC",
        priority=int(wire.get("priority") or 0),
        monotonic_ms=int(float(wire.get("timestamp") or 0.0) * 1000),
        metrics=dict(wire.get("data") or {}),
        correlation_id=str(wire.get("name") or "unknown"),
    )


def _derived_source(event_type: str) -> str:
    if event_type in {"SESSION_PREVIEW", "SESSION_WRAP", "BACK_UNDER_WAY"}:
        return "narrative"
    if event_type == "INCIDENT_AFTERMATH":
        return "aftermath"
    if event_type == "SESSION_FLAG":
        return "flags"
    if event_type == "PACE_HUNT":
        return "timing_hunt"
    if event_type in {"QUALI_RECAP", "PARADE_PAD"}:
        return "grid_story"
    return "derived"
