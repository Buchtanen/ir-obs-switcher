"""Stream-start commentary bridge and opener mutex."""

from __future__ import annotations

import random
from types import SimpleNamespace

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.in_car import InCarDetector
from irswitch.commentary.opener import OpenerMutex
from irswitch.commentary.stream_context import (
    make_stream_start_envelope,
    notify_overlay_stream_started,
)
from irswitch.commentary.tts import NullTtsSink
from irswitch.commentary.validator import estimate_seconds, validate_utterance
from irswitch.events.envelope import make_envelope
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.http import reset_overlay_server, set_overlay_runtime
from irswitch.overlay.models import RaceState
from irswitch.overlay.runtime import OverlayRuntime
from irswitch.overlay.settings import CommentarySettings, OverlaySettings


def test_opener_mutex_stream_start_blocks_in_car() -> None:
    lock = OpenerMutex(hold_s=10.0)
    assert lock.skip_reason("ENTER_CAR", 1.0) is None
    lock.note("STREAM_START", 1.0)
    assert lock.skip_reason("ENTER_CAR", 2.0) == "opener_mutex"
    assert lock.skip_reason("SESSION_INTRO_RACE", 2.0) == "opener_mutex"
    assert lock.skip_reason("QUALI_RECAP", 2.0) == "opener_mutex"
    assert lock.skip_reason("STREAM_START", 2.0) is None
    assert lock.skip_reason("OVERTAKE", 2.0) is None
    assert lock.skip_reason("ENTER_CAR", 12.0) is None


def test_opener_mutex_enter_car_blocks_intro() -> None:
    lock = OpenerMutex(hold_s=10.0)
    lock.note("ENTER_CAR", 1.0)
    assert lock.skip_reason("SESSION_INTRO_PRACTICE", 2.0) == "opener_mutex"


def test_stream_start_envelope_is_commentary_only() -> None:
    env = make_stream_start_envelope(1.5)
    assert env.event_type == "STREAM_START"
    assert env.phase == "ENTER"


def test_director_speaks_stream_start_and_holds_busy() -> None:
    director = CommentaryDirector(
        graph=load_sequence_graph(),
        settings=CommentarySettings(enabled=True, stream_start=True, cooldown_s=0.0),
        sink=NullTtsSink(),
        rng=random.Random(0),
    )
    spoken = director.observe([make_stream_start_envelope(1.0)], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "stream_start"
    assert spoken.estimated_seconds >= 10.0
    assert director._busy_until >= 1.0 + spoken.estimated_seconds - 0.01
    enter = make_envelope(
        event_type="ENTER_CAR",
        phase="RESULT",
        mode="RACE",
        priority=38,
    )
    assert director.observe([enter], None, 1.1) is None
    assert director.decisions(1)[-1]["reason"] == "busy"
    after_tts = 1.0 + spoken.estimated_seconds + 0.05
    assert director.observe([enter], None, after_tts) is None
    assert director.decisions(1)[-1]["reason"] == "opener_mutex"


def test_stream_start_lines_exceed_global_utterance_cap_but_validate() -> None:
    node = load_sequence_graph().nodes["stream_start"]
    assert node.tts.max_seconds >= 15.0
    assert node.slots == ()
    global_cap = 6.0
    long_enough = 0
    for locale in ("en", "cs"):
        for line in node.variant_bucket(locale, "unknown"):
            assert "{" not in line
            assert validate_utterance(line, node) == []
            if estimate_seconds(line) > global_cap:
                long_enough += 1
    assert long_enough >= 4


def test_notify_missing_runtime_does_not_raise() -> None:
    reset_overlay_server()
    notify_overlay_stream_started(1.0)


def test_runtime_stream_start_default_off() -> None:
    reset_overlay_server()
    overlay = OverlaySettings()
    assert overlay.commentary.stream_start is False
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, OverlayBus())
    set_overlay_runtime(runtime)
    runtime.notify_obs_stream_started(1.0)
    assert runtime.commentary is not None
    assert runtime.commentary.opener.skip_reason("ENTER_CAR", 1.1) is None


def test_runtime_stream_start_enabled_notes_mutex() -> None:
    reset_overlay_server()
    overlay = OverlaySettings(
        commentary=CommentarySettings(enabled=True, stream_start=True, cooldown_s=0.0)
    )
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, OverlayBus())
    runtime.notify_obs_stream_started(5.0)
    assert runtime.commentary is not None
    assert runtime.commentary.opener.skip_reason("ENTER_CAR", 5.1) == "opener_mutex"
    detector = InCarDetector()
    env = detector.tick(RaceState(connected=True, player_car_idx=3, overlay_mode="RACE"), 5.2)
    assert env is not None
    assert runtime.commentary.observe([env], None, 5.2) is None


def test_notify_overlay_calls_runtime(monkeypatch: object) -> None:
    called: list[float] = []

    class _Runtime:
        def notify_obs_stream_started(self, now: float) -> None:
            called.append(now)

    monkeypatch.setattr(
        "irswitch.commentary.stream_context.get_overlay_runtime",
        lambda: _Runtime(),
    )
    notify_overlay_stream_started(9.0)
    assert called == [9.0]
