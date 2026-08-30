"""Public read-only status snapshots (admin spec §7: no foreign private attrs)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from irswitch.bio.provider import BleHeartRateProvider
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import SequenceGraph, TtsLimits, parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.http import (
    get_overlay_runtime,
    reset_overlay_server,
    set_overlay_runtime,
)
from irswitch.overlay.models import RaceState
from irswitch.overlay.runtime import OverlayRuntime
from irswitch.overlay.settings import (
    CommentarySettings,
    HeartRateSettings,
    OverlaySettings,
    OverlayTapeSettings,
    SamplingSettings,
    SystemInfoSettings,
)
from irswitch.overlay.tape import OverlaySessionTape

COMMENTARY_KEYS = {"enabled", "available", "busy", "busyUntil", "status", "lastSpokeAt"}


def _graph() -> SequenceGraph:
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "overtake": {
                    "family": "position",
                    "event_types": ["OVERTAKE"],
                    "phases": ["RESULT"],
                    "speak_priority": 85,
                    "cooldown_s": 8,
                    "slots": [],
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["Position taken."]}},
                }
            },
            "edges": [],
        }
    )


def _director(*, enabled: bool = True) -> CommentaryDirector:
    return CommentaryDirector(
        graph=_graph(),
        settings=CommentarySettings(enabled=enabled),
        sink=NullTtsSink(),
    )


def _overtake() -> object:
    return make_envelope(
        event_type="OVERTAKE",
        phase="RESULT",
        priority=80,
        correlation_id="battle:1",
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


def _runtime(overlay: OverlaySettings, bus: OverlayBus | None = None) -> OverlayRuntime:
    return OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, bus or OverlayBus())


# --- commentary director -------------------------------------------------------


def test_director_snapshot_disabled() -> None:
    snapshot = _director(enabled=False).status_snapshot(100.0)
    assert set(snapshot) == COMMENTARY_KEYS
    assert snapshot["enabled"] is False
    assert snapshot["status"] == "disabled"
    assert snapshot["busy"] is False
    assert snapshot["lastSpokeAt"] is None


def test_director_snapshot_ready_then_speaking() -> None:
    director = _director()
    ready = director.status_snapshot(100.0)
    assert ready["status"] == "ready"
    assert ready["available"] is True
    assert ready["busyUntil"] == 0.0

    utterance = director.observe([_overtake()], None, 100.0)
    assert utterance is not None
    speaking = director.status_snapshot(100.0)
    assert speaking["status"] == "speaking"
    assert speaking["busy"] is True
    assert speaking["busyUntil"] > 100.0
    assert speaking["lastSpokeAt"] == 100.0

    # Same director, later clock: the utterance timer has expired.
    after = director.status_snapshot(speaking["busyUntil"] + 0.1)
    assert after["status"] == "ready"
    assert after["busy"] is False


def test_director_snapshot_enabled_override_wins_over_stale_settings() -> None:
    director = _director(enabled=True)
    assert director.status_snapshot(1.0, enabled=False)["status"] == "disabled"
    off = _director(enabled=False)
    assert off.status_snapshot(1.0, enabled=True)["status"] == "ready"


def test_director_snapshot_empty_graph_is_idle() -> None:
    director = CommentaryDirector(
        graph=SequenceGraph(
            version=1,
            locales=("en",),
            default_tts=TtsLimits(),
            nodes={},
            edges=(),
        ),
        settings=CommentarySettings(enabled=True),
        sink=NullTtsSink(),
    )
    snapshot = director.status_snapshot(5.0)
    assert snapshot["available"] is False
    assert snapshot["status"] == "idle"


def test_director_snapshot_has_no_side_effects() -> None:
    director = _director()
    director.observe([_overtake()], None, 100.0)
    before = director.decisions(50)
    first = director.status_snapshot(100.5)
    second = director.status_snapshot(100.5)
    assert first == second
    assert director.decisions(50) == before


# --- session tape --------------------------------------------------------------


def test_tape_snapshot_closed_then_recording(tmp_path: Path) -> None:
    tape = OverlaySessionTape(
        get_stream_origin_mono=lambda: None,
        get_obs_scene=lambda: None,
        get_driving_mode=lambda: None,
        get_version=lambda: "test",
    )
    closed = tape.status_snapshot()
    assert closed == {
        "available": True,
        "pathOpen": False,
        "path": None,
        "sessionKey": None,
    }

    settings = OverlaySettings(tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)))
    tape.observe(_race(), 10.0, settings)
    open_snapshot = tape.status_snapshot()
    assert open_snapshot["pathOpen"] is True
    assert open_snapshot["path"] == str(tape.path)
    assert open_snapshot["sessionKey"] == "777:0"

    tape.close()
    assert tape.status_snapshot()["pathOpen"] is False


def test_tape_snapshot_does_not_write_or_open(tmp_path: Path) -> None:
    tape = OverlaySessionTape(
        get_stream_origin_mono=lambda: None,
        get_obs_scene=lambda: None,
        get_driving_mode=lambda: None,
        get_version=lambda: "test",
    )
    settings = OverlaySettings(tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)))
    tape.observe(_race(), 10.0, settings)
    path = tape.path
    assert path is not None
    size = path.stat().st_size
    assert tape.status_snapshot() == tape.status_snapshot()
    assert path.stat().st_size == size


# --- BLE heart rate ------------------------------------------------------------


def test_bio_snapshot_disconnected_and_disabled() -> None:
    provider = BleHeartRateProvider(HeartRateSettings(enabled=True), SamplingSettings())
    snapshot = provider.status_snapshot()
    assert snapshot["enabled"] is True
    assert snapshot["status"] == "disconnected"
    assert snapshot["connected"] is False
    assert snapshot["bpm"] is None
    assert snapshot["hrState"] == "unknown"
    assert snapshot["source"] == "bluetooth"
    assert snapshot["deviceFilter"] == "auto"

    off = BleHeartRateProvider(HeartRateSettings(enabled=False), SamplingSettings())
    off.set_status("connecting")
    off_snapshot = off.status_snapshot()
    assert off_snapshot["status"] == "disabled"
    assert off_snapshot["connected"] is False


def test_bio_snapshot_connected_reports_bpm() -> None:
    provider = BleHeartRateProvider(HeartRateSettings(enabled=True), SamplingSettings())
    provider.set_status("connected", device_name="HRM-Test")
    provider.ingest_measurement(bytes([0x00, 148]), now=1.0)
    snapshot = provider.status_snapshot()
    assert snapshot["status"] == "connected"
    assert snapshot["connected"] is True
    assert snapshot["deviceName"] == "HRM-Test"
    assert snapshot["bpm"] == 148
    assert snapshot["hrState"] in {"unknown", "calm", "focused", "pushing", "high"}


def test_bio_snapshot_status_stays_in_enum() -> None:
    provider = BleHeartRateProvider(HeartRateSettings(enabled=True), SamplingSettings())
    allowed = {"disabled", "disconnected", "connecting", "reconnecting", "connected", "error"}
    for status in ("connecting", "reconnecting", "disconnected"):
        provider.set_status(status)
        assert provider.status_snapshot()["status"] in allowed


# --- overlay runtime aggregate -------------------------------------------------


def test_runtime_snapshot_defaults_idle() -> None:
    runtime = _runtime(OverlaySettings())
    snapshot = runtime.status_snapshot(now=50.0)
    assert snapshot["enabled"] is True
    assert snapshot["available"] is True
    assert snapshot["running"] is False
    assert snapshot["status"] == "idle"
    assert snapshot["mode"] == "live"
    assert snapshot["tasks"] == 0
    assert set(snapshot["commentary"]) >= COMMENTARY_KEYS
    assert snapshot["commentary"]["status"] == "disabled"
    assert snapshot["tape"]["status"] == "idle"
    assert snapshot["tape"]["pathOpen"] is False
    assert snapshot["bio"]["available"] is False
    assert snapshot["bio"]["status"] == "disconnected"
    assert snapshot["system"]["status"] == "idle"
    assert snapshot["system"]["available"] is False


def test_runtime_snapshot_disabled_overlay() -> None:
    runtime = _runtime(OverlaySettings(enabled=False))
    snapshot = runtime.status_snapshot(now=1.0)
    assert snapshot["enabled"] is False
    assert snapshot["status"] == "disabled"


def test_runtime_snapshot_running_flag_follows_lifecycle() -> None:
    runtime = _runtime(OverlaySettings())
    assert runtime.status_snapshot(now=1.0)["running"] is False
    runtime._running = True
    assert runtime.status_snapshot(now=1.0)["status"] == "running"


def test_runtime_snapshot_commentary_uses_config_enabled() -> None:
    overlay = OverlaySettings(commentary=CommentarySettings(enabled=True))
    runtime = _runtime(overlay)
    runtime.commentary = _director(enabled=False)
    commentary = runtime.status_snapshot(now=10.0)["commentary"]
    assert commentary["enabled"] is True
    assert commentary["status"] == "ready"

    runtime.commentary = None
    missing = runtime.status_snapshot(now=10.0)["commentary"]
    assert missing["available"] is False
    assert missing["status"] == "idle"


def test_runtime_snapshot_tape_recording(tmp_path: Path) -> None:
    overlay = OverlaySettings(tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)))
    runtime = _runtime(overlay)
    runtime._sync_tape(_race(), 5.0)
    tape = runtime.status_snapshot(now=5.0)["tape"]
    assert tape["enabled"] is True
    assert tape["status"] == "recording"
    assert tape["pathOpen"] is True
    assert tape["sessionKey"] == "777:0"


def test_runtime_snapshot_tape_disabled(tmp_path: Path) -> None:
    overlay = OverlaySettings(tape=OverlayTapeSettings(enabled=False, directory=str(tmp_path)))
    tape = _runtime(overlay).status_snapshot(now=5.0)["tape"]
    assert tape["enabled"] is False
    assert tape["status"] == "disabled"


def test_runtime_snapshot_bio_prefers_provider() -> None:
    overlay = OverlaySettings(heart_rate=HeartRateSettings(enabled=True, device="HRM"))
    runtime = _runtime(overlay)
    provider = BleHeartRateProvider(overlay.heart_rate, SamplingSettings())
    provider.set_status("connected", device_name="HRM-Test")
    runtime._bio = provider
    bio = runtime.status_snapshot(now=2.0)["bio"]
    assert bio["available"] is True
    assert bio["status"] == "connected"
    assert bio["deviceName"] == "HRM-Test"
    assert bio["deviceFilter"] == "HRM"


def test_runtime_snapshot_bio_config_disable_wins() -> None:
    overlay = OverlaySettings(heart_rate=HeartRateSettings(enabled=False))
    runtime = _runtime(overlay)
    provider = BleHeartRateProvider(HeartRateSettings(enabled=True), SamplingSettings())
    provider.set_status("connected", device_name="HRM-Test")
    runtime._bio = provider
    bio = runtime.status_snapshot(now=2.0)["bio"]
    assert bio["enabled"] is False
    assert bio["status"] == "disabled"
    assert bio["connected"] is False


def test_runtime_snapshot_system_sampling() -> None:
    overlay = OverlaySettings(system_info=SystemInfoSettings(enabled=True, gpu_enabled=False))
    runtime = _runtime(overlay)
    runtime._system = object()
    system = runtime.status_snapshot(now=3.0)["system"]
    assert system["status"] == "sampling"
    assert system["available"] is True
    assert system["gpuEnabled"] is False

    disabled = _runtime(
        OverlaySettings(system_info=SystemInfoSettings(enabled=False))
    ).status_snapshot(now=3.0)["system"]
    assert disabled["status"] == "disabled"


def test_runtime_snapshot_fail_soft_on_broken_config() -> None:
    def _boom() -> None:
        raise RuntimeError("config exploded")

    runtime = _runtime(OverlaySettings())
    runtime._get_config = _boom  # type: ignore[assignment]
    snapshot = runtime.status_snapshot(now=7.0)
    assert snapshot["status"] in {"disabled", "idle", "running"}
    assert snapshot["commentary"]["status"] in {"disabled", "idle", "ready", "speaking"}
    assert snapshot["tape"]["status"] in {"disabled", "idle", "recording"}
    assert snapshot["bio"]["status"] == "disconnected"
    assert snapshot["system"]["status"] in {"disabled", "idle", "sampling"}


def test_runtime_snapshot_is_deterministic_and_side_effect_free(tmp_path: Path) -> None:
    overlay = OverlaySettings(tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)))
    runtime = _runtime(overlay)
    first = runtime.status_snapshot(now=9.0)
    second = runtime.status_snapshot(now=9.0)
    assert first == second
    assert first["tasks"] == 0
    assert list(tmp_path.iterdir()) == []


# --- overlay http accessor -----------------------------------------------------


def test_get_overlay_runtime_accessor() -> None:
    reset_overlay_server()
    try:
        assert get_overlay_runtime() is None
        marker = object()
        set_overlay_runtime(marker)
        assert get_overlay_runtime() is marker
    finally:
        reset_overlay_server()
