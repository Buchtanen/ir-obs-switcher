"""Bounded accepted-beat history owned by RaceObserver."""

from __future__ import annotations

from irswitch.events.envelope import EventSubject, make_envelope
from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.race.observer import RaceObserver
from irswitch.race.story import StoryHistory


def _event(index: int):
    return make_envelope(
        event_type="HUNTING" if index < 3 else "OVERTAKE",
        phase="ENTER" if index < 3 else "RESULT",
        mode="RACE",
        event_id=f"event:{index}",
        correlation_id="battle:12",
        monotonic_ms=index * 1_000,
        target=EventSubject(car_id="12", display_name="Rossi"),
        metrics={"gap": 0.8, "newPosition": 5, "branch": "attack"},
    )


def test_story_history_is_bounded_factual_and_resettable() -> None:
    history = StoryHistory(max_beats=3)
    for index in range(4):
        history.note(_event(index))

    beats = history.snapshot()
    assert [beat.event_id for beat in beats] == ["event:1", "event:2", "event:3"]
    assert beats[-1].event_type == "OVERTAKE"
    assert beats[-1].target_name == "Rossi"
    assert beats[-1].position == 5
    assert beats[-1].correlation_id == "battle:12"

    history.clear()
    assert history.snapshot() == ()


def test_race_observer_exposes_history_in_next_story_snapshot() -> None:
    observer = RaceObserver()
    observer.note_accepted([_event(1)])

    context = observer.observe(
        TelemetrySnapshot.disconnected(2.0),
        RaceState(connected=False),
        now=2.0,
    )
    assert [beat.event_id for beat in context.recent_beats] == ["event:1"]

    observer.reset_session()
    reset = observer.observe(
        TelemetrySnapshot.disconnected(3.0),
        RaceState(connected=False),
        now=3.0,
    )
    assert reset.recent_beats == ()
