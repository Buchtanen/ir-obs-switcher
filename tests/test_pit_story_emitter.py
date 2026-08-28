"""PitStoryEmitter FSM tests."""

from __future__ import annotations

from dataclasses import replace

from irswitch.events.engine import EventEngine
from irswitch.events.pit import PitEmitter
from irswitch.events.pit_story import PitStoryEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import EventEngineFeatureSettings, OverlaySettings


def _state(**overrides: object) -> RaceState:
    base = {
        "connected": True,
        "subsession_id": "12345",
        "session_num": 2,
        "class_position": 7,
        "on_pit_road": False,
        "player_lap_dist_pct": 0.12,
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def _pit_story_engine() -> EventEngine:
    overlay = replace(OverlaySettings(), event_engine=EventEngineFeatureSettings(pit_story=True))
    engine = EventEngine(overlay)
    engine.register(PitStoryEmitter(overlay.events.priorities))
    return engine


def test_pit_story_fsm_full_cycle() -> None:
    emitter = PitStoryEmitter()
    t = 0.0
    dist = 0.20

    emitter.tick(_state(on_pit_road=False), t)
    out = emitter.tick(_state(on_pit_road=True, player_lap_dist_pct=dist), t + 0.1)
    assert any(e.phase == "enter" and e.data["state"] == "entry" for e in out)
    assert any(e.phase == "enter" and e.data["state"] == "lane" for e in out)
    cid = next(e.data["correlationId"] for e in out if e.data.get("state") == "entry")
    assert cid == "pit:12345:2:1"

    out = emitter.tick(_state(on_pit_road=True, player_lap_dist_pct=dist), t + 0.2)
    assert any(e.phase == "update" and e.data["state"] == "lane" for e in out)

    for i in range(20):
        emitter.tick(_state(on_pit_road=True, player_lap_dist_pct=dist), t + 0.3 + i * 0.1)
    assert emitter._fsm == "stopped"

    out = emitter.tick(_state(on_pit_road=True, player_lap_dist_pct=dist + 0.01), t + 3.0)
    assert any(e.data["state"] == "released" for e in out)

    out = emitter.tick(
        _state(on_pit_road=False, class_position=9, player_lap_dist_pct=dist + 0.02),
        t + 4.0,
    )
    assert any(e.data["state"] == "exit" for e in out)
    assert any(e.data["state"] == "outcome" for e in out)
    outcome = next(e for e in out if e.data["state"] == "outcome")
    assert outcome.phase == "trigger"
    assert outcome.data["positionDelta"] == -2
    assert all(e.data["correlationId"] == cid for e in out if "correlationId" in e.data)


def test_pit_story_shared_correlation_id() -> None:
    emitter = PitStoryEmitter()
    emitter.tick(_state(on_pit_road=False), 0.0)
    first = emitter.tick(_state(on_pit_road=True), 1.0)
    cid1 = first[0].data["correlationId"]

    emitter.tick(_state(on_pit_road=False, class_position=8), 5.0)
    second = emitter.tick(_state(on_pit_road=True), 10.0)
    cid2 = next(e for e in second if e.phase == "enter").data["correlationId"]
    assert cid1 != cid2
    assert cid2.endswith(":2")


def test_pit_story_flag_off_keeps_legacy_pit_emitter() -> None:
    engine = EventEngine(OverlaySettings())
    assert engine.pit is not None
    assert isinstance(engine.pit, PitEmitter)
    assert not any(isinstance(e, PitStoryEmitter) for e in engine._emitters)

    engine.tick(_state(on_pit_road=False), 0.0)
    out = engine.tick(_state(on_pit_road=True), 1.0)
    assert len(out) == 1
    assert out[0].name == "pit_entry"


def test_pit_story_flag_on_replaces_legacy_pit_emitter() -> None:
    engine = _pit_story_engine()
    assert engine.pit is None
    assert any(isinstance(e, PitStoryEmitter) for e in engine._emitters)

    engine.tick(_state(on_pit_road=False), 0.0)
    out = engine.tick(_state(on_pit_road=True), 1.0)
    assert all(e.name == "pit_story" for e in out)
    assert not any(e.name == "pit_entry" for e in out)
