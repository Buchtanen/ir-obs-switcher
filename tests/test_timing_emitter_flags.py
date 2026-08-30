"""Feature-flag registration for T2 practice/quali timing emitters."""

from __future__ import annotations

from dataclasses import replace

from irswitch.events.engine import EventEngine
from irswitch.events.practice import PracticeEmitter
from irswitch.events.quali import QualiEmitter
from irswitch.events.sector_split import SectorSplitEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import (
    EventEngineFeatureSettings,
    OverlaySettings,
)
from irswitch.race.timing import SegmentReferenceTracker, TimingStore


def _register_timing_emitters(
    engine: EventEngine,
    overlay: OverlaySettings,
    store: TimingStore,
    reference: SegmentReferenceTracker,
) -> None:
    """Mirror OverlayRuntime._register_timing_emitters for unit tests."""
    if overlay.event_engine.practice or overlay.event_engine.quali_projection:
        engine.register(
            SectorSplitEmitter(
                store,
                overlay.events,
                overlay.events.priorities,
            )
        )
    if overlay.event_engine.practice:
        engine.register(
            PracticeEmitter(
                store,
                reference,
                overlay.events,
                overlay.events.priorities,
            )
        )
    if overlay.event_engine.quali_projection:
        engine.register(
            QualiEmitter(
                store,
                reference,
                overlay.events,
                overlay.events.priorities,
            )
        )


def test_practice_flag_registers_emitter() -> None:
    overlay = replace(OverlaySettings(), event_engine=EventEngineFeatureSettings(practice=True))
    engine = EventEngine(overlay)
    store = TimingStore()
    ref = SegmentReferenceTracker()
    _register_timing_emitters(engine, overlay, store, ref)

    assert any(isinstance(e, PracticeEmitter) for e in engine._emitters)
    assert any(isinstance(e, SectorSplitEmitter) for e in engine._emitters)
    assert not any(isinstance(e, QualiEmitter) for e in engine._emitters)


def test_quali_flag_registers_emitter() -> None:
    overlay = replace(
        OverlaySettings(),
        event_engine=EventEngineFeatureSettings(quali_projection=True),
    )
    engine = EventEngine(overlay)
    store = TimingStore()
    ref = SegmentReferenceTracker()
    _register_timing_emitters(engine, overlay, store, ref)

    assert any(isinstance(e, QualiEmitter) for e in engine._emitters)
    assert any(isinstance(e, SectorSplitEmitter) for e in engine._emitters)
    assert not any(isinstance(e, PracticeEmitter) for e in engine._emitters)


def test_flags_off_skips_timing_emitters() -> None:
    engine = EventEngine(OverlaySettings())
    store = TimingStore()
    ref = SegmentReferenceTracker()
    _register_timing_emitters(engine, OverlaySettings(), store, ref)

    assert not any(
        isinstance(e, (PracticeEmitter, QualiEmitter, SectorSplitEmitter)) for e in engine._emitters
    )


def test_practice_flag_emitter_tick_reaches_engine() -> None:
    overlay = replace(OverlaySettings(), event_engine=EventEngineFeatureSettings(practice=True))
    engine = EventEngine(overlay)
    store = TimingStore()
    ref = SegmentReferenceTracker()
    _register_timing_emitters(engine, overlay, store, ref)

    state = RaceState(connected=True, overlay_mode="QUALIFYING")
    assert engine.tick(state, 1.0) == []

    state = RaceState(connected=True, overlay_mode="PRACTICE")
    assert engine.tick(state, 1.0) == []
