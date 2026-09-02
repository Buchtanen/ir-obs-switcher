"""N12 producer identity, context, audience, and coalescing tests."""

from __future__ import annotations

import json

from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.events.stream import SessionSequenceAllocator, thaw_context
from irswitch.overlay.models import BioState, RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.race.ministory import MiniStoryRegistry
from irswitch.race.pipeline import RacePipeline, build_situation_payload, coalesce_key_for


def _race(**overrides: object) -> RaceState:
    values: dict[str, object] = {
        "connected": True,
        "player_car_idx": 7,
        "session_num": 0,
        "subsession_id": "99",
        "session_type": "Race",
        "overlay_mode": "RACE",
        "lap": 3,
        "lap_completed": 2,
        "session_time": 120.0,
    }
    values.update(overrides)
    return RaceState(**values)  # type: ignore[arg-type]


def _capture(pipeline: RacePipeline, race: RaceState | None = None) -> bytes:
    return pipeline.capture_context(
        race=race or _race(),
        bio=BioState(connected=True, status="connected", bpm=140, state="focused"),
        story=None,
        telemetry_data={
            "SessionLapsRemain": 8,
            "SessionTimeRemain": 480.0,
            "SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionLaps": "10"}]},
        },
        captured_monotonic_ms=1_000,
        language="en",
        commentary_enabled=True,
    )


def test_pipeline_stamps_sidecars_and_routes_commentary_only() -> None:
    fanout = AsyncEventFanout()
    overlay = fanout.subscribe("overlay")
    commentary = fanout.subscribe("commentary")
    pipeline = RacePipeline(fanout)
    pipeline.reset_session("99:0", reason="session_changed")
    _capture(pipeline)
    envelope = make_envelope(
        event_type="ENTER_CAR",
        phase="RESULT",
        mode="RACE",
        priority=38,
        monotonic_ms=1_000,
        correlation_id="in_car",
    )

    batch = pipeline.publish_envelopes([envelope], source="in_car", accepted_monotonic_ms=1_000)

    assert batch is not None
    accepted = batch.events[0]
    assert accepted.event_id == "99:0:ENTER_CAR:1"
    assert accepted.audiences == ("commentary",)
    assert overlay.latest_context == commentary.latest_context == batch.context_payload


def test_pipeline_assigns_one_frozen_ministory_identity_before_fanout() -> None:
    fanout = AsyncEventFanout()
    registry = MiniStoryRegistry()
    pipeline = RacePipeline(fanout, story_registry=registry)
    pipeline.reset_session("99:0", reason="session_changed")
    _capture(pipeline)
    envelope = make_envelope(
        event_type="HUNTING",
        phase="ENTER",
        mode="RACE",
        priority=60,
        monotonic_ms=1_000,
        correlation_id="battle:front:12",
        target={"carId": "12", "displayName": "Rossi"},
        metrics={"gap": 0.8},
    )

    batch = pipeline.publish_envelopes(
        [envelope], source="event_engine", accepted_monotonic_ms=1_000
    )

    assert batch is not None
    accepted = batch.events[0]
    story = json.loads(accepted.story_payload or b"{}")
    assert story == {
        "correlationId": "battle:front:12",
        "eventType": "HUNTING",
        "heroOrderRevision": 0,
        "runEpoch": 0,
        "state": "ready",
        "storyId": "story:0:1",
        "storyRevision": 1,
    }
    assert registry.token_for(envelope) is not None


def test_manager_and_sidecars_share_one_sequence_allocator() -> None:
    allocator = SessionSequenceAllocator("99:0")
    manager = EventManagerV2(session_id="99:0", sequence_allocator=allocator)
    race_event, envelopes = manager.submit(
        CandidateEvent(
            name="lap_complete",
            channel="timing",
            priority=50,
            phase="trigger",
            data={"lap": 2, "lapTime": 60.0},
        ),
        1.0,
        mode="RACE",
    )
    assert race_event is not None
    assert [item.sequence for item in envelopes] == [1]

    sidecar = make_envelope(event_type="FIELD_FACT", phase="RESULT", mode="RACE")
    allocator.stamp(sidecar)
    assert sidecar.sequence == 2
    assert sidecar.event_id == "99:0:FIELD_FACT:2"


def test_context_contains_same_tick_identity_bio_and_situation() -> None:
    fanout = AsyncEventFanout()
    fanout.subscribe("overlay")
    pipeline = RacePipeline(fanout)
    pipeline.reset_session("99:0", reason="session_changed")

    context = thaw_context(_capture(pipeline))

    assert context["identity"]["session_type"] == "Race"
    assert context["race"]["lap"] == 3
    assert context["bio"]["hr_state"] == "focused"
    assert context["situation"] == {
        "captured_monotonic_ms": 1000,
        "current_lap": 3,
        "is_final_lap": False,
        "lap_completed": 2,
        "laps_remaining": 8.0,
        "player_finished": False,
        "progress_ratio": 0.2,
        "progress_source": "laps",
        "race_phase": "middle",
        "session_checkered": False,
        "session_time_elapsed_s": 120.0,
        "session_time_remaining_s": 480.0,
        "session_time_total_s": None,
        "session_type": "Race",
        "total_laps": 10,
        "run_epoch": 0,
        "green_session_time_s": None,
        "race_elapsed_s": None,
        "racing_laps_completed": 2,
    }


def test_situation_override_order_and_non_race_unknown() -> None:
    assert build_situation_payload(_race(player_finished=True), {}, 1)["race_phase"] == "finished"
    assert (
        build_situation_payload(_race(session_checkered=True), {}, 1)["race_phase"] == "checkered"
    )
    assert build_situation_payload(_race(is_final_lap=True), {}, 1)["race_phase"] == "final_lap"
    assert build_situation_payload(_race(overlay_mode="PRACTICE"), {}, 1)["race_phase"] == "unknown"


def test_coalesce_keys_keep_front_and_rear_relations_independent() -> None:
    front = make_envelope(
        event_type="HUNTING",
        phase="UPDATE",
        mode="RACE",
        target={"carId": "12"},
        metrics={"relationEpoch": 3},
    )
    rear = make_envelope(
        event_type="HUNTED",
        phase="UPDATE",
        mode="RACE",
        target={"carId": "9"},
        metrics={"relationEpoch": 4},
    )
    front_key = coalesce_key_for(front, "99:0")
    rear_key = coalesce_key_for(rear, "99:0")

    assert front_key == ("99:0", "front", "player", "12", "3", "HUNTING")
    assert rear_key == ("99:0", "rear", "player", "9", "4")
    assert front_key != rear_key
