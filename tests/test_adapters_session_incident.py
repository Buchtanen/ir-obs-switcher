"""Session + incident + rival_threat adapter coverage for commentary live path."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.adapters import race_event_to_envelope
from irswitch.events.adapters.exception_extra import incident_race_event_to_envelope
from irswitch.events.adapters.position import position_race_event_to_envelope
from irswitch.events.adapters.session import session_race_event_to_envelope
from irswitch.events.manager_v2 import EventManagerV2, event_v4_wire
from irswitch.overlay.protocol import CandidateEvent, RaceEvent
from irswitch.overlay.settings import CommentarySettings


def test_incident_adapter_maps_value_slot() -> None:
    envelope = incident_race_event_to_envelope(
        RaceEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            timestamp=1.0,
            data={"value": 4, "total": 12},
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "INCIDENT"
    assert envelope.phase == "RESULT"
    assert envelope.metrics["value"] == 4
    bound = slot_bindings(envelope, "unknown")
    assert bound["value"] == 4


def test_incident_adapter_copies_branch_metric() -> None:
    envelope = incident_race_event_to_envelope(
        RaceEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            timestamp=1.0,
            data={"value": 2, "total": 8, "branch": "off_track", "nearbyCarIdx": 9},
        ),
        session_id="sub:1",
        mode="PRACTICE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.metrics["branch"] == "off_track"
    assert envelope.metrics["nearbyCarIdx"] == 9
    assert envelope.metrics.get("kind") != "contact_object"


def test_final_lap_and_finish_adapters_bind_position() -> None:
    final = session_race_event_to_envelope(
        RaceEvent(
            name="final_lap",
            channel="session",
            priority=95,
            phase="trigger",
            timestamp=1.0,
            data={"lap": 20, "position": 3, "classPosition": 2},
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert final is not None
    assert final.event_type == "FINAL_LAP"
    assert final.phase == "RESULT"
    assert slot_bindings(final, "unknown")["position"] == 3

    finish = session_race_event_to_envelope(
        RaceEvent(
            name="finish",
            channel="session",
            priority=100,
            phase="trigger",
            timestamp=2.0,
            data={"position": 3, "classPosition": 2},
        ),
        session_id="sub:1",
        mode="RACE",
        now=12.0,
    )
    assert finish is not None
    assert finish.event_type == "FINISH"
    assert slot_bindings(finish, "unknown")["position"] == 3


def test_rival_threat_keeps_gap_and_speakable_target_label() -> None:
    envelope = position_race_event_to_envelope(
        RaceEvent(
            name="rival_threat",
            channel="alert",
            priority=70,
            phase="enter",
            timestamp=1.0,
            data={
                "rivalPosition": 8,
                "gap": 1.8,
                "closingRate": 0.4,
                "targetCarIdx": 22,
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "RIVAL_THREAT"
    assert envelope.phase == "ENTER"
    assert envelope.metrics["gap"] == 1.8
    assert envelope.metrics["targetName"] == "P8"
    assert envelope.metrics["position"] == 8
    assert envelope.metrics["rivalPosition"] == 8
    assert envelope.target is not None
    assert envelope.target.display_name == "P8"
    bound = slot_bindings(envelope, "unknown")
    assert bound["gap"] == "1.80 s"
    assert bound["target_name"] == "P8"


def test_manager_v2_incident_and_finish_emit_v4() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    _, incident_envs = mgr.submit(
        CandidateEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            data={"value": 2, "total": 5},
        ),
        1.0,
        mode="RACE",
    )
    assert len(incident_envs) == 1
    assert incident_envs[0].event_type == "INCIDENT"
    wire = event_v4_wire(incident_envs[0])
    assert wire["format"] == "v4"
    assert wire["eventType"] == "INCIDENT"

    _, finish_envs = mgr.submit(
        CandidateEvent(
            name="finish",
            channel="session",
            priority=100,
            phase="trigger",
            data={"position": 4, "classPosition": 3},
        ),
        2.0,
        mode="RACE",
    )
    assert len(finish_envs) == 1
    assert finish_envs[0].event_type == "FINISH"


def test_registry_routes_session_and_incident() -> None:
    assert (
        race_event_to_envelope(
            RaceEvent(
                name="final_lap",
                channel="session",
                priority=1,
                phase="trigger",
                timestamp=1.0,
                data={"position": 1},
            ),
            session_id="s",
            mode="RACE",
            now=1.0,
        )
        is not None
    )
    assert (
        race_event_to_envelope(
            RaceEvent(
                name="incident",
                channel="alert",
                priority=1,
                phase="trigger",
                timestamp=1.0,
                data={"value": 1},
            ),
            session_id="s",
            mode="RACE",
            now=1.0,
        )
        is not None
    )


def test_director_speaks_rival_threat_and_incident_from_live_shaped_envelopes() -> None:
    director = CommentaryDirector(
        graph=load_sequence_graph(),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=NullTtsSink(),
        language="en",
    )
    rival = position_race_event_to_envelope(
        RaceEvent(
            name="rival_threat",
            channel="alert",
            priority=70,
            phase="enter",
            timestamp=1.0,
            data={"rivalPosition": 9, "gap": 2.1, "targetCarIdx": 3},
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    spoken = director.observe([rival], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "rival_threat"
    # Densified cells may pick a slotless filler; live bindings must still be speech-ready.
    bound = slot_bindings(rival, "unknown")
    assert bound.get("target_name") == "P9"
    assert bound.get("gap") == "2.10 s"
    assert "{" not in spoken.text

    director.reset()
    incident = incident_race_event_to_envelope(
        RaceEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            timestamp=2.0,
            data={"value": 4, "total": 4},
        ),
        session_id="sub:1",
        mode="RACE",
        now=20.0,
    )
    spoken2 = director.observe([incident], None, 20.0)
    assert spoken2 is not None
    assert spoken2.node_id == "incident"
