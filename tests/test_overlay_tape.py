"""Session HUD tape: clocks, gating, replay delay."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from irswitch.events.stream import thaw_context
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer
from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.overlay.replay import OverlayReplayer
from irswitch.overlay.runtime import OverlayRuntime
from irswitch.overlay.settings import (
    EventEngineFeatureSettings,
    OverlaySettings,
    OverlayTapeSettings,
    OverlayV4Settings,
)
from irswitch.overlay.tape import OverlaySessionTape, playback_offset, safe_tape_dir
from irswitch.race.runtime import RaceRuntime


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
    tape.record_commentary(
        {
            "action": "speak",
            "reason": "ok",
            "eventType": "LAP_COMPLETE",
            "nodeId": "lap.complete",
            "emotion": "neutral",
            "text": "Lap in the books.",
            "storyId": "story:0:1",
            "storyRevision": 1,
            "runEpoch": 0,
            "heroOrderRevision": 0,
            "graphMode": "shadow",
            "decision": "selected",
            "eventId": "event:1",
            "semanticKey": "lap:1",
            "score": 51.0,
            "threshold": 45.0,
            "components": {"base": 50.0, "transition": 1.0},
        },
        111.3,
        _race(),
    )
    tape.record_prepared_filler(
        {
            "action": "shadow_selected",
            "reason": "prepared_filler",
            "stage": "STREAM_LOBBY_INTRO",
            "planId": "sha256:plan",
            "variantId": "sha256:variant",
            "legacyNodeId": "field_fact",
            "legacySemanticKey": "field.position",
            "divergence": "different_semantic",
            "comparisonReason": "legacy_candidate",
            "attempt": 2,
            "mergedCount": 0,
            "desiredCount": 3,
            "readyCount": 1,
            "fatalEpisode": 0,
            "text": "must not be retained",
        },
        111.4,
        _race(),
    )
    tape.observe(_race(connected=False, overlay_mode="GENERIC"), 120.0, settings)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    types = [row["type"] for row in rows]
    assert types[0] == "header"
    assert rows[0]["t_stream"] == pytest.approx(10.0)
    assert rows[0]["t_session"] == pytest.approx(12.5)
    assert rows[0]["t_green"] == pytest.approx(0.0)
    commentary = next(row for row in rows if row["type"] == "commentary")
    assert commentary["graphMode"] == "shadow"
    assert commentary["components"]["base"] == 50.0
    assert "event" in types
    assert "decision" in types
    assert "stories" in types
    assert "commentary" in types
    assert "prepared_filler" in types
    prepared = next(row for row in rows if row["type"] == "prepared_filler")
    assert prepared["planId"] == "sha256:plan"
    assert prepared["legacyNodeId"] == "field_fact"
    assert prepared["divergence"] == "different_semantic"
    assert prepared["attempt"] == 2
    assert prepared["mergedCount"] == 0
    assert prepared["desiredCount"] == 3
    assert prepared["readyCount"] == 1
    assert prepared["fatalEpisode"] == 0
    assert "text" not in prepared
    commentary = next(row for row in rows if row["type"] == "commentary")
    assert commentary["text"] == "Lap in the books."
    assert commentary["action"] == "speak"
    assert commentary["storyId"] == "story:0:1"
    assert commentary["storyRevision"] == 1
    assert commentary["runEpoch"] == 0
    assert commentary["heroOrderRevision"] == 0
    assert "scene" in types
    assert tape.path is None


def test_disconnected_idle_does_not_open_tape(tmp_path: Path) -> None:
    tape = OverlaySessionTape(get_version=lambda: "x")
    tape.observe(_race(connected=False, overlay_mode="GENERIC"), 1.0, _settings(tmp_path))
    tape.record_scenario({"action": "observation_changed", "reason": "evidence_changed"}, 1.0, None)
    assert tape.path is None
    assert list(tmp_path.glob("*.jsonl")) == []


def _runtime_with_tape(tmp_path: Path) -> RaceRuntime:
    settings = OverlaySettings(
        theme="cyber_racing",
        v4=OverlayV4Settings(renderer=True),
        tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)),
    )
    return RaceRuntime(lambda: SimpleNamespace(overlay=settings), None, OverlayBus())


def _quiet_race_tick(runtime: RaceRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "_observe_timing", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime, "_observe_race_story", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime, "_apply_sector_points", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime.session, "in_warmup", lambda _now: True)


@pytest.mark.asyncio
async def test_disconnected_runtime_skips_scenario_when_tape_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_with_tape(tmp_path)
    _quiet_race_tick(runtime, monkeypatch)
    recorded: list[object] = []
    monkeypatch.setattr(runtime._tape, "record_scenario", lambda *args, **_k: recorded.append(args))
    monkeypatch.setattr(
        runtime.race_observer.excursion,
        "take_trace",
        lambda: [{"action": "observation_changed", "reason": "evidence_changed"}],
    )
    monkeypatch.setattr(
        runtime.analyzer,
        "analyze",
        lambda _snap: RaceState(connected=False, overlay_mode="GENERIC"),
    )

    async def read() -> TelemetrySnapshot:
        return TelemetrySnapshot.disconnected()

    monkeypatch.setattr(runtime, "_read_telemetry", read)
    await runtime._tick_race()
    assert runtime._tape.path is None
    assert recorded == []
    assert list(tmp_path.glob("*.jsonl")) == []


@pytest.mark.asyncio
async def test_connected_runtime_records_scenario_on_open_tape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_with_tape(tmp_path)
    _quiet_race_tick(runtime, monkeypatch)
    recorded: list[dict[str, object]] = []
    original = runtime._tape.record_scenario

    def spy(entry: dict[str, object], now: float, state: RaceState | None) -> None:
        recorded.append(entry)
        original(entry, now, state)

    monkeypatch.setattr(runtime._tape, "record_scenario", spy)
    monkeypatch.setattr(
        runtime.race_observer.excursion,
        "take_trace",
        lambda: [{"action": "beat_emitted", "reason": "offtrack", "beatId": "offtrack"}],
    )
    monkeypatch.setattr(
        runtime.analyzer,
        "analyze",
        lambda _snap: RaceState(
            connected=True,
            overlay_mode="RACE",
            session_num=0,
            subsession_id="777",
            session_time=12.0,
            session_state=4,
        ),
    )

    async def read() -> TelemetrySnapshot:
        return TelemetrySnapshot(
            connected=True,
            player_car_idx=0,
            session_num=0,
            subsession_id="777",
            track_id="1",
            session_type="Race",
            session_time=12.0,
            session_state=4,
        )

    monkeypatch.setattr(runtime, "_read_telemetry", read)
    await runtime._tick_race()
    assert runtime._tape.path is not None
    assert recorded
    assert recorded[0]["action"] == "beat_emitted"
    assert recorded[0]["scenarioMode"] == "active"
    rows = [
        json.loads(line)
        for line in runtime._tape.path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert any(row.get("type") == "race_scenario" for row in rows)


def test_disabled_tape_writes_nothing(tmp_path: Path) -> None:
    tape = OverlaySessionTape(get_version=lambda: "x")
    tape.observe(_race(), 1.0, _settings(tmp_path, enabled=False))
    assert tape.path is None
    assert list(tmp_path.glob("*.jsonl")) == []


def test_prepared_generated_text_is_retained_only_in_debug(monkeypatch: object) -> None:
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=OverlaySettings()), None, OverlayBus())
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        runtime._tape,
        "record_prepared_filler",
        lambda entry, _now, _state: recorded.append(entry),
    )
    entry = {
        "eventType": "PREPARED_FILLER",
        "action": "generated",
        "acceptedTexts": ["Audit this accepted variant."],
    }

    monkeypatch.setattr(runtime, "_tape_debug_enabled", lambda: False)
    runtime._record_commentary_decision(entry, 1.0)
    assert "acceptedTexts" not in recorded[-1]

    monkeypatch.setattr(runtime, "_tape_debug_enabled", lambda: True)
    runtime._record_commentary_decision(entry, 2.0)
    assert recorded[-1]["acceptedTexts"] == ["Audit this accepted variant."]


def test_scenario_evidence_and_speech_keep_identity_and_clocks(tmp_path: Path) -> None:
    tape = OverlaySessionTape(get_stream_origin_mono=lambda: 100.0, get_version=lambda: "test")
    tape.observe(_race(), 110.0, _settings(tmp_path))
    path = tape.path
    assert path is not None
    tape.record_scenario(
        {
            "action": "detected",
            "parentStoryId": "parent",
            "beatId": "offtrack",
            "scenarioMode": "shadow",
            "reason": "surface_offtrack_held",
        },
        111.0,
        _race(),
    )
    tape.record_commentary(
        {
            "action": "tts_result",
            "parentStoryId": "parent",
            "beatId": "offtrack",
            "correlationId": "parent:offtrack",
            "eventType": "TRACK_EXCURSION",
            "text": "He has gone off track.",
        },
        112.0,
        _race(),
    )
    tape.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    detected = next(row for row in rows if row["type"] == "race_scenario")
    spoken = next(row for row in rows if row["type"] == "commentary")
    assert detected["scenarioMode"] == "shadow"
    assert detected["t_stream"] == 11.0
    assert spoken["t_stream"] == 12.0
    assert spoken["parentStoryId"] == detected["parentStoryId"]
    assert spoken["correlationId"] == "parent:offtrack"


def test_same_session_run_epoch_resets_green_but_preserves_tape_clock(tmp_path: Path) -> None:
    tape = OverlaySessionTape(get_stream_origin_mono=lambda: 100.0, get_version=lambda: "test")
    settings = _settings(tmp_path)
    tape.observe(_race(session_state=3, session_time=105.0), 110.0, settings)
    tape.observe(_race(session_time=106.0), 111.0, settings)
    path = tape.path
    tape.observe(_race(run_epoch=1, session_state=3, session_time=0.2), 120.0, settings)
    tape.observe(_race(run_epoch=1, session_state=4, session_time=4.0), 124.0, settings)
    tape.observe(_race(run_epoch=1, session_state=4, session_time=5.0), 125.0, settings)
    assert tape.path == path
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    restarts = [row for row in rows if row["type"] == "run_reset"]
    assert len(restarts) == 1
    assert restarts[0]["run_epoch"] == 1
    assert restarts[0]["t_green"] is None
    greens = [row for row in rows if row["type"] == "green"]
    assert len(greens) == 2
    assert greens[-1]["run_epoch"] == 1
    assert greens[-1]["t_green"] == 0.0
    assert greens[-1]["t_mono"] == 14.0
    assert greens[-1]["t_stream"] == 24.0


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
    assert "SectorSplitEmitter" in names


@pytest.mark.asyncio
async def test_runtime_marshals_tts_story_transition_onto_overlay_loop() -> None:
    overlay = OverlaySettings(event_engine=EventEngineFeatureSettings(v2_payload=True))
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, OverlayBus())
    received: list[dict] = []
    runtime.overlay_consumer.enqueue_story_transition = received.append  # type: ignore[method-assign]
    runtime._runtime_loop = asyncio.get_running_loop()
    entry = {
        "storyId": "story:0:1",
        "storyRevision": 1,
        "runEpoch": 0,
        "heroOrderRevision": 0,
        "correlationId": "battle:1",
        "eventType": "HUNTING",
        "action": "speaking",
    }

    worker = __import__("threading").Thread(
        target=runtime._ministory_lifecycle_hook,
        args=(entry,),
    )
    worker.start()
    worker.join(timeout=1.0)
    await asyncio.sleep(0)

    assert received == [entry]


@pytest.mark.asyncio
async def test_overlay_runtime_disconnect_clears_stories() -> None:
    """Link drop / iRacing quit must blank the HUD, not leave hunting + SYSINFO."""
    overlay = OverlaySettings(event_engine=EventEngineFeatureSettings(v2_payload=True))
    bus = OverlayBus()
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, bus)
    runtime._hud_live = True
    bus.set_active_stories_v4([{"eventType": "HUNTING"}])
    bus.set_active_events([{"name": "hunting"}])
    assert runtime._idle_when_disconnected(_race(connected=False)) is True
    assert runtime._hud_live is False
    payload = runtime.pipeline.context_payload
    assert payload is not None
    context = thaw_context(payload)
    assert context["hud"]["active_events"] == []
    assert context["hud"]["active_stories_v4"] == []
    consumer = OverlayConsumer(runtime._overlay_subscription, bus)
    await consumer.apply_latest_presentation()
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


<<<<<<< HEAD
def test_llm_polish_records_without_debug_when_llm_rows(
    tmp_path: Path, monkeypatch: object
) -> None:
    settings = _settings(tmp_path)
    runtime = RaceRuntime(lambda: SimpleNamespace(overlay=settings), None, OverlayBus())
    monkeypatch.setattr(runtime, "_tape_debug_enabled", lambda: False)
    runtime._tape.observe(_race(), 10.0, settings)
    runtime._last_race = _race()
    runtime._llm_polish_tape_hook({"outcome": "ok", "nodeId": "hunting"})
    path = runtime._tape.path
    assert path is not None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert any(row.get("type") == "llm_polish" and row.get("nodeId") == "hunting" for row in rows)


def test_llm_polish_skipped_when_llm_rows_false_unless_debug(
    tmp_path: Path, monkeypatch: object
) -> None:
    settings = OverlaySettings(
        theme="cyber_racing",
        v4=OverlayV4Settings(renderer=True),
        tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path), llm_rows=False),
    )
    runtime = RaceRuntime(lambda: SimpleNamespace(overlay=settings), None, OverlayBus())
    monkeypatch.setattr(runtime, "_tape_debug_enabled", lambda: False)
    runtime._tape.observe(_race(), 10.0, settings)
    runtime._last_race = _race()
    runtime._llm_polish_tape_hook({"outcome": "ok", "nodeId": "hunting"})
    path = runtime._tape.path
    assert path is not None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert not any(row.get("type") == "llm_polish" for row in rows)

    monkeypatch.setattr(runtime, "_tape_debug_enabled", lambda: True)
    runtime._llm_polish_tape_hook({"outcome": "ok", "nodeId": "hunting"})
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert any(row.get("type") == "llm_polish" for row in rows)


def test_tape_writes_field_rows_by_default(tmp_path: Path) -> None:
    tape = OverlaySessionTape(
        get_stream_origin_mono=lambda: 100.0,
        get_obs_scene=lambda: "Race",
        get_driving_mode=lambda: "RACE",
        get_version=lambda: "1.2.0-test",
    )
    settings = _settings(tmp_path)
    state = _race(
        position=6,
        class_position=4,
        official_position=8,
        official_class_position=5,
        position_source="live",
        car_idx_live_position=(8, 6),
        car_idx_live_class_position=(5, 4),
        player_car_idx=1,
    )
    tape.observe(state, 110.0, settings)
    snap = TelemetrySnapshot(
        connected=True,
        player_car_idx=1,
        session_type="Race",
        session_state=4,
        position=8,
        class_position=5,
        car_idx_position=(8, 8),
        car_idx_class_position=(5, 5),
        car_idx_lap_dist_pct=(0.1, 0.4),
        car_idx_driver_name=("A", "Hero"),
        car_idx_track_surface=(3, 3),
    )
    from irswitch.race.order import field_tape_payload

    tape.record_field(field_tape_payload(snap, state), 110.2, state)
    path = tape.path
    assert path is not None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["schemaVersion"] == "1.1"
    field = next(row for row in rows if row["type"] == "field")
    assert field["officialClassPosition"] == 5
    assert field["liveClassPosition"] == 4
    assert field["positionSource"] == "live"
    assert field["cars"]


def test_tape_field_can_be_disabled(tmp_path: Path) -> None:
    tape = OverlaySessionTape(
        get_stream_origin_mono=lambda: 100.0,
        get_obs_scene=lambda: "Race",
        get_driving_mode=lambda: "RACE",
        get_version=lambda: "test",
    )
    settings = OverlaySettings(
        theme="cyber_racing",
        v4=OverlayV4Settings(renderer=True),
        tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path), field=False),
    )
    tape.observe(_race(), 110.0, settings)
    tape.record_field({"playerCarIdx": 0, "cars": []}, 110.2, _race())
    path = tape.path
    assert path is not None
    types = [json.loads(line)["type"] for line in path.read_text(encoding="utf-8").splitlines()]
    assert "field" not in types
