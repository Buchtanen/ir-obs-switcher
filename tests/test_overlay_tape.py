"""Session HUD tape: clocks, gating, replay delay."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.models import RaceState
from irswitch.overlay.replay import OverlayReplayer
from irswitch.overlay.runtime import OverlayRuntime
from irswitch.overlay.settings import (
    EventEngineFeatureSettings,
    OverlaySettings,
    OverlayTapeSettings,
    OverlayV4Settings,
)
from irswitch.overlay.tape import OverlaySessionTape, playback_offset, safe_tape_dir


def _settings(tmp_path: Path, *, enabled: bool = True) -> OverlaySettings:
    return OverlaySettings(
        theme="cyber_racing",
        v4=OverlayV4Settings(renderer=True),
        tape=OverlayTapeSettings(enabled=enabled, directory=str(tmp_path)),
    )


def _race(**overrides: object) -> RaceState:
    base: dict[str, object] = {
        "connected": True,
        "overlay_mode": "RACE",
        "session_state": 4,
        "session_time": 12.5,
        "subsession_id": "777",
        "session_num": 0,
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def test_safe_tape_dir_rejects_traversal() -> None:
    assert safe_tape_dir("../evil") == "recordings"
    assert safe_tape_dir("recordings") == "recordings"


def test_tape_writes_header_event_decision_scene_not_on_generic(
    tmp_path: Path,
) -> None:
    tape = OverlaySessionTape(
        get_stream_origin_mono=lambda: 100.0,
        get_obs_scene=lambda: "Race",
        get_driving_mode=lambda: "RACE",
        get_version=lambda: "1.2.0-test",
    )
    settings = _settings(tmp_path)
    tape.observe(_race(), 110.0, settings)
    path = tape.path
    assert path is not None
    tape.record_event({"type": "event", "eventType": "LAP_COMPLETE"}, 111.0, _race())
    tape.record_decision(
        {"event_type": "LAP_COMPLETE", "action": "emitted", "reason": "accepted"},
        111.0,
        _race(),
    )
    tape.record_stories([{"eventType": "HUNTING", "phase": "ACTIVE"}], 111.2, _race())
    tape.observe(_race(connected=False, overlay_mode="GENERIC"), 120.0, settings)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    types = [row["type"] for row in rows]
    assert types[0] == "header"
    assert rows[0]["t_stream"] == pytest.approx(10.0)
    assert rows[0]["t_session"] == pytest.approx(12.5)
    assert rows[0]["t_green"] == pytest.approx(0.0)
    assert "event" in types
    assert "decision" in types
    assert "stories" in types
    assert "scene" in types
    assert tape.path is None


def test_disabled_tape_writes_nothing(tmp_path: Path) -> None:
    tape = OverlaySessionTape(get_version=lambda: "x")
    tape.observe(_race(), 1.0, _settings(tmp_path, enabled=False))
    assert tape.path is None
    assert list(tmp_path.glob("*.jsonl")) == []


def test_playback_offset_prefers_t_mono() -> None:
    assert playback_offset({"t": 1400.0, "t_mono": 0.25}) == 0.25
    assert playback_offset({"t": 3.0}) == 3.0


@pytest.mark.asyncio
async def test_replayer_skips_header_and_uses_t_mono(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    path = tmp_path / "tape.jsonl"
    path.write_text(
        json.dumps({"t": 1400.0, "t_mono": 0.0, "type": "header", "schemaVersion": "1.0"})
        + "\n"
        + json.dumps(
            {
                "t": 1401.5,
                "t_mono": 0.0,
                "type": "event",
                "eventType": "LAP_COMPLETE",
                "metrics": {"lapTime": 92.4},
            }
        )
        + "\n"
        + json.dumps({"t": 1402.0, "t_mono": 0.0, "type": "decision", "action": "emitted"})
        + "\n"
        + json.dumps(
            {
                "t": 1403.0,
                "t_mono": 0.0,
                "type": "stories",
                "activeStories": [{"eventType": "HUNTING", "phase": "ACTIVE"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bus = OverlayBus()
    await OverlayReplayer(str(path), bus).run()
    assert sleeps == [] or max(sleeps) < 1.0
    assert bus.active_stories_v4[0]["eventType"] == "HUNTING"


def test_overlay_runtime_constructs_with_practice_emitters() -> None:
    """practice/quali emitters need TimingStore; used to AttributeError in __init__."""
    overlay = OverlaySettings(
        event_engine=EventEngineFeatureSettings(
            v2_payload=True,
            practice=True,
            quali_projection=True,
            pit_story=True,
            hr_pressure=True,
        )
    )
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, OverlayBus())
    assert runtime._timing_store is not None
    names = {type(emitter).__name__ for emitter in runtime.engine._emitters}
    assert "PracticeEmitter" in names
    assert "QualiEmitter" in names


def test_overlay_runtime_disconnect_clears_stories() -> None:
    """Link drop / iRacing quit must blank the HUD, not leave hunting + SYSINFO."""
    overlay = OverlaySettings(event_engine=EventEngineFeatureSettings(v2_payload=True))
    bus = OverlayBus()
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, bus)
    runtime._hud_live = True
    bus.set_active_stories_v4([{"eventType": "HUNTING"}])
    bus.set_active_events([{"name": "hunting"}])
    assert runtime._idle_when_disconnected(_race(connected=False)) is True
    assert runtime._hud_live is False
    assert bus.active_stories_v4 == []
    assert bus.active_events == []
    assert runtime._idle_when_disconnected(_race(connected=True)) is False
    assert runtime._hud_live is True


def test_tape_opens_when_session_type_comes_from_session_name(tmp_path: Path) -> None:
    """Live overlay omitted SessionType; tape must still open in Race."""
    from irswitch.iracing.telemetry import extract_telemetry
    from irswitch.race.context import RaceContextAnalyzer

    tape = OverlaySessionTape(
        get_stream_origin_mono=lambda: None,
        get_obs_scene=lambda: None,
        get_driving_mode=lambda: None,
        get_version=lambda: "test",
    )
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "SessionName": "Race",
            "SessionNum": 0,
            "SessionState": 4,
        },
        1.0,
    )
    state = RaceContextAnalyzer().analyze(snap)
    tape.observe(state, 10.0, _settings(tmp_path))
    assert tape.path is not None
    assert tape.path.parent == tmp_path

    warmup = RaceContextAnalyzer().analyze(
        extract_telemetry({"PlayerCarIdx": 0, "SessionName": "Warmup"}, 1.0)
    )
    tape.observe(warmup, 11.0, _settings(tmp_path))
    assert tape.path is None
