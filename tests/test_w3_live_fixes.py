"""W3 live-listen fixes: polish gate, tape, phase, hunted, leader change."""

from __future__ import annotations

from irswitch.commentary.composer import build_skeleton
from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.polish import (
    build_polish_request,
    fact_violation_codes,
)
from irswitch.commentary.tts import CommentaryUtterance, ProcessTtsSink
from irswitch.events.adapters.position import position_race_event_to_envelope
from irswitch.events.envelope import make_envelope
from irswitch.events.leader_change import LeaderChangeEmitter
from irswitch.events.manager_v2 import EventManagerV2
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent, RaceEvent
from irswitch.overlay.settings import CommentarySettings, EventPrioritySettings, EventSettings
from irswitch.race.context import RaceContextAnalyzer
from irswitch.race.opponents import relevant_ahead_behind
from irswitch.race.pipeline import build_situation_payload


def test_polish_rejects_invented_p_position() -> None:
    codes = fact_violation_codes(
        "Buchtanen moves from P twenty-nine to P thirty.",
        "Buchtanen drops from P four to P five.",
    )
    assert "invented_position" in codes


def test_polish_does_not_treat_english_possessive_as_sector() -> None:
    codes = fact_violation_codes(
        "He is closing on Rossi, gap 0.70 seconds.",
        "He's closing on Rossi. Gap's 0.70 seconds.",
    )
    assert "invented_sector" not in codes


def test_polish_prompt_omits_recent_history() -> None:
    req = build_polish_request(
        "He is running P thirty.",
        CommentarySettings(),
        fact_pack={
            "version": "commentary-facts/1",
            "hero": {"class_position": 30},
            "recent": ["Buchtanen is running P4."],
        },
    )
    user = req["messages"][1]["content"]
    assert "FACTS:" in user
    assert "P4" not in user
    assert "recent" not in user
    assert "Ignore prior commentary" in req["messages"][0]["content"]


def test_process_sink_polish_fail_rejects_skeleton(monkeypatch) -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    spoken: list[str] = []

    monkeypatch.setattr(
        "irswitch.commentary.tts.polish_skeleton",
        lambda *args, **kwargs: type(
            "O",
            (),
            {
                "text": "",
                "outcome": "retry_exhausted",
                "debug_record": lambda self, node_id="", event_type="": {
                    "outcome": "retry_exhausted"
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda text, **kwargs: (
            spoken.append(text)
            or type("R", (), {"backend": "null", "spoken": True, "error": None})()
        ),
    )

    sink = ProcessTtsSink(
        settings=CommentarySettings(llm_polish=True, tts_backend="null"),
        on_spoken_text=None,
    )
    sink._speak(
        CommentaryUtterance(
            node_id="hunting",
            locale="en",
            emotion="unknown",
            text="Richard is running P thirty.",
            event_type="HUNTING",
            event_id="e1",
            correlation_id="c1",
            estimated_seconds=2.0,
            node=node,
        )
    )
    assert spoken == []


def test_director_decision_hook_survives_ring_buffer() -> None:
    seen: list[str] = []
    director = CommentaryDirector.from_defaults(CommentarySettings(enabled=False))
    director.on_decision = lambda entry, now: seen.append(entry["reason"])
    for i in range(40):
        director.record_external_skip(reason=f"skip-{i}", now=float(i), event_type="HUNTING")
    assert len(seen) == 40
    assert seen[0] == "skip-0"
    assert seen[-1] == "skip-39"
    assert len(director.decisions(10_000)) == 32


def test_race_phase_stays_opening_until_green() -> None:
    telemetry = {
        "SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionLaps": "10"}]},
        "SessionLapsRemain": 9,
    }
    parade = RaceState(
        connected=True,
        overlay_mode="RACE",
        session_num=0,
        lap_completed=2,
        session_state=3,
        session_time=97.0,
    )
    payload = build_situation_payload(parade, telemetry, 1_000)
    assert payload["progress_ratio"] == 0.2
    assert payload["race_phase"] == "opening"

    green = RaceState(
        connected=True,
        overlay_mode="RACE",
        session_num=0,
        lap_completed=2,
        session_state=4,
        flag_green=True,
    )
    assert build_situation_payload(green, telemetry, 1_000)["race_phase"] == "middle"


def test_composer_allows_single_fact_session_wrap() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["session_wrap"]
    envelope = make_envelope(
        event_type="SESSION_WRAP",
        phase="RESULT",
        mode="RACE",
        metrics={"modeLabel": "Race", "position": 29, "p1Name": "A", "p2Name": "B", "p3Name": "C"},
    )
    result = build_skeleton(
        envelope,
        node,
        graph=graph,
        story={"race": {"class_position": 29}, "situation": {}, "story": {}},
        bindings=slot_bindings(envelope, "unknown"),
        emotion="unknown",
        language="en",
    )
    assert result is not None
    required = " ".join(fact["text"] for fact in result.fact_pack["required_facts"])
    optional = " ".join(fact["text"] for fact in result.fact_pack["optional_facts"])
    assert "29" in required or "twenty" in required.lower()
    assert "A" in optional and "B" in optional and "C" in optional


def test_manager_v2_exit_clears_active_story() -> None:
    mgr = EventManagerV2(EventSettings(), session_id="s1")
    enter = CandidateEvent(
        name="battle",
        channel="battle",
        priority=20,
        phase="enter",
        data={"state": "hunted", "targetCarIdx": 4, "gap": 0.4},
    )
    mgr.submit(enter, 1.0, mode="RACE")
    assert any(row["eventType"] == "HUNTED" for row in mgr.active_stories_v4())
    exit_c = CandidateEvent(
        name="battle",
        channel="battle",
        priority=20,
        phase="exit",
        data={"state": "hunted", "targetCarIdx": 4, "gap": 1.2},
    )
    mgr.submit(exit_c, 2.0, mode="RACE")
    assert mgr.active_stories_v4() == []


def test_last_place_has_no_car_behind() -> None:
    data = {
        "PlayerCarIdx": 2,
        "PlayerCarPosition": 3,
        "PlayerCarClassPosition": 3,
        "PlayerCarClass": 1,
        "LapLastLapTime": 90.0,
        "CarIdxLapDistPct": [0.40, 0.30, 0.50],
        "CarIdxLapCompleted": [10, 10, 10],
        "CarIdxClass": [1, 1, 1],
        "CarIdxClassPosition": [1, 2, 3],
        "CarIdxPosition": [1, 2, 3],
        "CarIdxOnPitRoad": [False, False, False],
        "CarIdxTrackSurface": [3, 3, 3],
    }
    snap = extract_telemetry(data, timestamp=1.0)
    ahead, behind = relevant_ahead_behind(snap)
    assert behind is None
    assert ahead == 1


def test_leader_change_emits_priority_75() -> None:
    emitter = LeaderChangeEmitter(EventPrioritySettings())
    first = RaceState(
        connected=True,
        overlay_mode="RACE",
        session_state=4,
        leader_car_idx=4,
        leader_name="Nash",
        class_field_size=12,
    )
    assert emitter.tick(first, 1.0) == []
    changed = RaceState(
        connected=True,
        overlay_mode="RACE",
        session_state=4,
        leader_car_idx=9,
        leader_name="Knaus",
        p1_name="Knaus",
        class_position=4,
        class_field_size=12,
    )
    assert emitter.tick(changed, 1.2) == []
    out = emitter.tick(changed, 1.6)
    assert len(out) == 1
    assert out[0].name == "leader_change"
    assert out[0].priority == 75
    assert out[0].data["targetName"] == "Knaus"
    assert out[0].data["oldLeaderName"] == "Nash"
    env = position_race_event_to_envelope(
        RaceEvent(
            name=out[0].name,
            channel=out[0].channel,
            priority=out[0].priority,
            phase=out[0].phase,
            timestamp=1.6,
            data=out[0].data,
        ),
        session_id="s1",
        mode="RACE",
        now=1.6,
    )
    assert env is not None
    assert env.event_type == "LEADER_CHANGE"
    assert env.priority == 75
    assert env.copy.headline_token == "position.leader_change"
    assert env.target is not None
    assert env.target.display_name == "Knaus"


def test_context_fills_leader_and_podium() -> None:
    data = {
        "PlayerCarIdx": 2,
        "PlayerCarPosition": 3,
        "PlayerCarClassPosition": 3,
        "PlayerCarClass": 1,
        "LapLastLapTime": 90.0,
        "CarIdxLapDistPct": [0.54, 0.52, 0.50, 0.48],
        "CarIdxLapCompleted": [10, 10, 10, 10],
        "CarIdxClass": [1, 1, 1, 1],
        "CarIdxClassPosition": [1, 2, 3, 4],
        "CarIdxPosition": [1, 2, 3, 4],
        "CarIdxOnPitRoad": [False, False, False, False],
        "CarIdxTrackSurface": [3, 3, 3, 3],
        "DriverInfo": {
            "Drivers": [
                {"CarIdx": 0, "UserName": "Alpha"},
                {"CarIdx": 1, "UserName": "Bravo"},
                {"CarIdx": 2, "UserName": "Hero"},
                {"CarIdx": 3, "UserName": "Delta"},
            ]
        },
    }
    snap = extract_telemetry(data, timestamp=1.0)
    state = RaceContextAnalyzer().analyze(snap)
    assert state.leader_car_idx == 0
    assert state.leader_name == "Alpha"
    assert state.p1_name == "Alpha"
    assert state.p2_name == "Bravo"
    assert state.p3_name == "Hero"
    assert state.class_field_size == 4
