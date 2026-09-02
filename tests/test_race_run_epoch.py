"""Run identity survives jitter but not a confirmed same-session restart."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.manager_v2 import event_v4_wire
from irswitch.events.stream import thaw_context, thaw_envelope
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.models import BioState, RaceState, TelemetrySnapshot
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.narrative import StreamNarrativeFsm
from irswitch.race.pipeline import RacePipeline, build_situation_payload
from irswitch.race.run import RunClock
from irswitch.race.runtime import RaceRuntime
from irswitch.race.story import StoryHistory


def test_rewind_is_confirmed_once_and_jitter_or_single_stale_sample_are_ignored():
    clock = RunClock()
    assert clock.observe("s", 106.0, now=0.0, connected=True) == "accepted"
    assert clock.observe("s", 105.9, now=0.2, connected=True) == "accepted"
    assert clock.observe("s", 2.0, now=0.4, connected=True) == "pending"
    assert clock.observe("s", 106.4, now=0.6, connected=True) == "accepted"
    assert clock.run_epoch == 0
    assert clock.observe("s", 2.0, now=0.8, connected=True) == "pending"
    assert clock.observe("s", 2.2, now=1.0, connected=True) == "restarted"
    assert clock.run_epoch == 1
    assert clock.observe("s", 2.4, now=1.2, connected=True) == "accepted"
    assert clock.run_epoch == 1
    clock.observe("new", 0.0, now=1.4, connected=True)
    assert clock.run_epoch == 0


def test_clock_ignores_disconnected_and_non_finite_times():
    clock = RunClock()
    clock.observe("s", 100.0, now=0.0, connected=True)
    for i, value in enumerate((None, float("nan"), float("inf"), -1.0)):
        clock.observe("s", value, now=float(i + 1), connected=True)
    clock.observe("s", 0.0, now=5.0, connected=False)
    assert clock.run_epoch == 0
    assert clock.observe("s", 100.1, now=6.0, connected=True) == "accepted"


def test_green_origin_excludes_formation_and_does_not_reset_on_yellow():
    clock = RunClock()
    clock.observe("s", 100.0, now=0.0, connected=True)
    parade = RaceState(
        connected=True,
        overlay_mode="RACE",
        session_num=0,
        session_time=100.0,
        session_state=3,
        lap_completed=2,
    )
    clock.apply(parade)
    green = clock.apply(replace(parade, session_time=106.0, session_state=4))
    data = {"SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionTime": "480 sec"}]}}
    situation = build_situation_payload(green, data, 1000)
    assert situation["race_phase"] == "opening"
    assert situation["race_elapsed_s"] == 0.0
    assert situation["session_time_elapsed_s"] == 106.0
    clock.apply(replace(parade, session_time=150.0, flag_yellow=True))
    later = clock.apply(replace(green, session_time=202.0))
    assert build_situation_payload(later, data, 2000)["progress_ratio"] == 0.2
    laps = {"SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionLaps": "10"}]}}
    assert build_situation_payload(green, laps, 1000)["progress_ratio"] == 0.0


def test_joining_mid_race_does_not_claim_a_new_green_origin():
    clock = RunClock()
    clock.observe("s", 300.0, now=1.0, connected=True)
    state = clock.apply(
        RaceState(
            connected=True,
            overlay_mode="RACE",
            session_num=0,
            session_time=300.0,
            session_state=4,
            lap_completed=5,
        )
    )
    assert state.green_session_time is None
    data = {
        "SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionTime": "480 sec"}]},
        "SessionTimeRemain": 180.0,
    }
    assert build_situation_payload(state, data, 1000)["race_phase"] == "middle"


def test_run_epoch_is_frozen_in_context_event_and_correlation():
    fanout = AsyncEventFanout()
    fanout.subscribe("commentary")
    pipeline = RacePipeline(fanout)
    pipeline.reset_session("s", reason="session_changed")
    assert pipeline.reset_run(1) is not None
    assert pipeline.reset_run(1) is None
    race = RaceState(run_epoch=1)
    context = pipeline.capture_context(
        race=race,
        bio=BioState(),
        story=None,
        telemetry_data={},
        captured_monotonic_ms=1000,
        language="en",
        commentary_enabled=True,
    )
    assert thaw_context(context)["identity"]["run_epoch"] == 1
    assert thaw_context(context)["story"]["run_epoch"] == 1
    envelope = make_envelope(
        event_type="HUNTING", phase="ENTER", mode="RACE", correlation_id="front:7:8:1"
    )
    batch = pipeline.publish_envelopes(
        [envelope],
        source="test",
        accepted_monotonic_ms=1000,
        overlay_wires=[event_v4_wire(envelope)],
    )
    event = thaw_envelope(batch.events[0].envelope)
    assert event.metrics["runEpoch"] == 1
    assert event.correlation_id == "run:1:front:7:8:1"
    assert batch.events[0].overlay_payload is not None
    overlay_wire = json.loads(batch.events[0].overlay_payload)
    assert overlay_wire["metrics"]["runEpoch"] == 1
    assert "runEpoch" not in overlay_wire
    assert overlay_wire["correlationId"] == "run:1:front:7:8:1"


def test_history_drops_invalid_source_scalars():
    history = StoryHistory()
    history.note(
        make_envelope(
            event_type="LAP_COMPLETE",
            phase="RESULT",
            mode="RACE",
            metrics={
                "gap": -38,
                "frontGap": "nan",
                "rearGap": "inf",
                "delta": 0,
                "position": 4.2,
                "lapTime": float("nan"),
            },
        )
    )
    beat = history.snapshot()[0]
    assert (beat.gap, beat.front_gap, beat.rear_gap, beat.delta, beat.position, beat.lap_time) == (
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_session_switch_does_not_invent_final_classification_and_epoch_can_wrap_again():
    fsm = StreamNarrativeFsm()
    race = RaceState(connected=True, overlay_mode="RACE", class_position=8, p1_name="Leader")
    fsm.tick(race, 1, session_key="s")
    changed = fsm.tick(replace(race, overlay_mode="PRACTICE"), 2, session_key="next")
    assert "position" not in changed[0].metrics
    assert "p1Name" not in changed[0].metrics
    fsm = StreamNarrativeFsm()
    fsm.tick(race, 1, session_key="s")
    assert fsm.tick(replace(race, player_finished=True), 2, session_key="s")
    fsm.reset_run()
    restarted = replace(race, run_epoch=1)
    assert fsm.tick(restarted, 3, session_key="s") == []
    result = fsm.tick(replace(restarted, player_finished=True), 4, session_key="s")
    assert len(result) == 1
    assert result[0].metrics["position"] == 8


@pytest.mark.asyncio
async def test_runtime_rewind_resets_registered_stores_once_before_observing(monkeypatch):
    runtime = RaceRuntime(lambda: SimpleNamespace(overlay=OverlaySettings()), None, OverlayBus())
    clock = [10.0]
    monkeypatch.setattr("irswitch.race.runtime.time.monotonic", lambda: clock[0])
    snapshot = [
        TelemetrySnapshot(
            connected=True,
            player_car_idx=0,
            session_num=0,
            subsession_id="test",
            track_id="1",
            session_type="Race",
            session_time=106.0,
            session_state=4,
        )
    ]

    async def read():
        return snapshot[0]

    monkeypatch.setattr(runtime, "_read_telemetry", read)
    resets = []
    runtime.session.add_reset_hook(lambda: resets.append(clock[0]))
    await runtime._tick_race()
    assert resets == [10.0]
    initial_manager = runtime.manager
    for mono, session_time in ((10.2, 0.0), (10.4, 0.2), (10.6, 0.4)):
        clock[0] = mono
        snapshot[0] = replace(snapshot[0], session_time=session_time, session_state=3)
        await runtime._tick_race()
    assert resets == [10.0, 10.4]
    assert runtime.manager is not initial_manager
    assert runtime._last_race.run_epoch == 1
    assert thaw_context(runtime.pipeline.context_payload)["story"]["run_epoch"] == 1
    assert runtime.race_observer.context.run_epoch == 1
