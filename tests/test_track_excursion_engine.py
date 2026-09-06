"""ScenarioEngine is the sole TRACK_EXCURSION speaking publisher."""

from __future__ import annotations

from test_track_excursion_live import state

from irswitch.events.scenarios.track_excursion_runtime import (
    DEFINITION_PATH,
    load_track_excursion_engine,
)
from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.overlay.settings import RaceObserverSettings
from irswitch.race.observer import RaceObserver


def _offtrack_frames() -> list[tuple[float, RaceState]]:
    return [
        (0.0, state()),
        (0.2, state(player_track_surface=0)),
        (0.41, state(player_track_surface=0)),
    ]


def test_track_excursion_runtime_definition_loads() -> None:
    assert DEFINITION_PATH.is_file()
    engine = load_track_excursion_engine()
    assert engine.definition.scenario_id == "track_excursion"
    assert engine.definition.status == "runtime"
    assert "offtrack" in engine.definition.emissions
    assert "stream_end" not in engine.definition.emissions


def test_active_engine_publishes_detector_envelopes_with_unknown_cause() -> None:
    observer = RaceObserver(settings=RaceObserverSettings(scenario_mode="active"))
    snap = TelemetrySnapshot(connected=True, timestamp=0, subsession_id="test", session_num=1)
    for now, sample in _offtrack_frames():
        observer.observe(snap, sample, now=now)
    beats = [
        env for env in observer.take_derived_envelopes() if env.event_type == "TRACK_EXCURSION"
    ]
    assert [env.metrics["beatId"] for env in beats] == ["offtrack"]
    assert all(env.metrics["cause"] == "unknown" for env in beats)
    assert all(env.metrics["damage"] == "unknown" for env in beats)
    traces = observer.excursion.take_trace()
    assert any(row.get("action") == "engine_transition" for row in traces)
    assert all(
        row.get("cause") == "unknown" for row in traces if row.get("action") == "engine_transition"
    )


def test_active_does_not_speak_when_engine_drops(monkeypatch) -> None:
    observer = RaceObserver(settings=RaceObserverSettings(scenario_mode="active"))
    monkeypatch.setattr(observer.excursion_engine, "publish", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(observer.excursion_engine, "drain_traces", list)
    snap = TelemetrySnapshot(connected=True, timestamp=0, subsession_id="test", session_num=1)
    for now, sample in _offtrack_frames():
        observer.observe(snap, sample, now=now)
    types = [env.event_type for env in observer.take_derived_envelopes()]
    assert "TRACK_EXCURSION" not in types
    assert observer.excursion.take_trace()


def test_shadow_ticks_engine_but_does_not_speak() -> None:
    observer = RaceObserver(settings=RaceObserverSettings(scenario_mode="shadow"))
    snap = TelemetrySnapshot(connected=True, timestamp=0, subsession_id="test", session_num=1)
    for now, sample in _offtrack_frames():
        observer.observe(snap, sample, now=now)
    types = [env.event_type for env in observer.take_derived_envelopes()]
    assert "TRACK_EXCURSION" not in types
    traces = observer.excursion.take_trace()
    assert any(row.get("action") == "engine_transition" for row in traces)
    assert any(row.get("action") == "detected" for row in traces)
