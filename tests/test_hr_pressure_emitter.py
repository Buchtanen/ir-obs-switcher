"""HrPressureEmitter hysteresis tests."""

from __future__ import annotations

from dataclasses import replace

from irswitch.events.engine import EventEngine
from irswitch.events.hr_pressure import HrPressureEmitter
from irswitch.overlay.models import BioState, RaceState
from irswitch.overlay.settings import EventEngineFeatureSettings, OverlaySettings


def _race(connected: bool = True) -> RaceState:
    return RaceState(connected=connected, overlay_mode="RACE")


def _bio(*, state: str = "calm", bpm: int = 120) -> BioState:
    return BioState(
        connected=True,
        status="connected",
        bpm=bpm,
        baseline_bpm=110.0,
        delta_bpm=float(bpm - 110),
        state=state,
    )


def test_hr_pressure_enter_on_pushing() -> None:
    emitter = HrPressureEmitter(exit_delay_s=2.0)
    out = emitter.tick(_race(), 1.0, _bio(state="pushing", bpm=140))
    assert len(out) == 1
    assert out[0].name == "hr_pressure"
    assert out[0].phase == "enter"
    assert out[0].data["hrState"] == "pushing"


def test_hr_pressure_hysteresis_requires_clear_delay() -> None:
    emitter = HrPressureEmitter(exit_delay_s=2.0)
    emitter.tick(_race(), 1.0, _bio(state="high", bpm=150))
    assert emitter.tick(_race(), 2.0, _bio(state="calm", bpm=115)) == []
    out = emitter.tick(_race(), 4.1, _bio(state="calm", bpm=115))
    assert len(out) == 1
    assert out[0].phase == "exit"


def test_hr_pressure_noop_without_bio() -> None:
    emitter = HrPressureEmitter()
    assert emitter.tick(_race(), 1.0, None) == []
    assert emitter.tick(_race(), 1.0, BioState(connected=False)) == []


def test_hr_pressure_update_while_active() -> None:
    emitter = HrPressureEmitter(exit_delay_s=2.0)
    emitter.tick(_race(), 1.0, _bio(state="pushing", bpm=140))
    out = emitter.tick(_race(), 1.5, _bio(state="high", bpm=155))
    assert len(out) == 1
    assert out[0].phase == "update"
    assert out[0].data["bpm"] == 155


def test_hr_pressure_flag_registers_emitter() -> None:
    overlay = replace(OverlaySettings(), event_engine=EventEngineFeatureSettings(hr_pressure=True))
    engine = EventEngine(overlay)
    engine.register(HrPressureEmitter(overlay.events.priorities))
    assert any(isinstance(e, HrPressureEmitter) for e in engine._emitters)

    out = engine.tick(_race(), 1.0, _bio(state="pushing", bpm=140))
    assert any(e.name == "hr_pressure" for e in out)


def test_hr_pressure_flag_off_no_emitter_behavior() -> None:
    engine = EventEngine(OverlaySettings())
    out = engine.tick(_race(), 1.0, _bio(state="high", bpm=160))
    assert out == []
