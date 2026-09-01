"""Pit + bio V4 adapter tests."""

from __future__ import annotations

from irswitch.events.adapters.bio import bio_race_event_to_envelope
from irswitch.events.adapters.pit import pit_race_event_to_envelope
from irswitch.events.manager_v2 import EventManagerV2, event_v4_wire
from irswitch.overlay.protocol import CandidateEvent, RaceEvent


def test_pit_story_entry_envelope() -> None:
    envelope = pit_race_event_to_envelope(
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="enter",
            timestamp=1.0,
            data={
                "state": "entry",
                "correlationId": "pit:sub:1:1",
                "position": 7,
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "PIT_ENTRY"
    assert envelope.phase == "ENTER"
    assert envelope.correlation_id == "pit:sub:1:1"
    assert envelope.presentation.variant == "pit_entry"
    assert envelope.copy.headline_token == "pit.entry"


def test_pit_story_outcome_envelope_is_result() -> None:
    envelope = pit_race_event_to_envelope(
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="trigger",
            timestamp=2.0,
            data={
                "state": "outcome",
                "correlationId": "pit:sub:1:1",
                "positionDelta": 2,
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=12.0,
    )
    assert envelope is not None
    assert envelope.event_type == "PIT_OUTCOME"
    assert envelope.phase == "RESULT"
    assert envelope.presentation.preferred_state == "RESULT"


def test_hr_pressure_envelope_maps_catalog() -> None:
    envelope = bio_race_event_to_envelope(
        RaceEvent(
            name="hr_pressure",
            channel="bio",
            priority=35,
            phase="enter",
            timestamp=1.0,
            data={"state": "hr_pressure", "bpm": 160, "deltaBpm": 28, "hrState": "high"},
        ),
        session_id="sub:1",
        mode="RACE",
        now=5.0,
    )
    assert envelope is not None
    assert envelope.event_type == "HR_PRESSURE_RISING"
    assert envelope.presentation.variant == "hr_pressure"
    assert envelope.copy.headline_token == "bio.hr_high"


def test_hr_pressure_envelope_rounds_float_bpm() -> None:
    envelope = bio_race_event_to_envelope(
        RaceEvent(
            name="hr_pressure",
            channel="bio",
            priority=35,
            phase="enter",
            timestamp=1.0,
            data={
                "state": "hr_pressure",
                "bpm": 147.6,
                "baselineBpm": 118.2,
                "deltaBpm": 29.4,
                "hrState": "high",
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=5.0,
    )
    assert envelope is not None
    assert envelope.metrics["bpm"] == 148
    assert envelope.metrics["baselineBpm"] == 118
    assert envelope.metrics["deltaBpm"] == 29


def test_pit_story_lane_envelope_uses_lane_token() -> None:
    envelope = pit_race_event_to_envelope(
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="update",
            timestamp=1.5,
            data={"state": "lane", "correlationId": "pit:sub:1:2", "position": 5},
        ),
        session_id="sub:1",
        mode="RACE",
        now=11.0,
    )
    assert envelope is not None
    assert envelope.event_type == "PIT_LANE"
    assert envelope.copy.headline_token == "pit.lane"


def test_manager_v2_submit_pit_story_emits_v4() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    _, envelopes = mgr.submit(
        CandidateEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="enter",
            data={"state": "lane", "correlationId": "pit:sub:1:3", "position": 5},
        ),
        3.0,
        mode="RACE",
    )
    assert len(envelopes) == 2
    assert envelopes[0].event_type == "PIT_LANE"
    assert envelopes[0].phase == "ENTER"
    assert envelopes[1].phase == "ACTIVE"
    wire = event_v4_wire(envelopes[1])
    assert wire["format"] == "v4"
    assert wire["presentation"]["variant"] == "pit_lane"


def test_manager_v2_submit_hr_pressure_emits_v4() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    _, envelopes = mgr.submit(
        CandidateEvent(
            name="hr_pressure",
            channel="bio",
            priority=35,
            phase="enter",
            data={"state": "hr_pressure", "bpm": 150, "hrState": "pushing"},
        ),
        4.0,
        mode="RACE",
    )
    assert len(envelopes) == 2
    assert envelopes[0].event_type == "HR_PRESSURE_RISING"
    assert envelopes[1].phase == "ACTIVE"
