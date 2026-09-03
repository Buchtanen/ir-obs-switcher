"""Director: post-arbitration node pick, HR emotion, silence when unfilled."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector, resolve_emotion, slot_bindings
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import EventSubject, make_envelope
from irswitch.overlay.models import BioState
from irswitch.overlay.settings import CommentarySettings


def _graph(*, filled: bool) -> object:
    variants = {}
    if filled:
        variants = {
            "en": {
                "neutral": ["He takes P{position} from {target_name}."],
                "pushing": ["Now. P{position} is his."],
            },
            "cs": {"neutral": ["Bere P{position}."]},
        }
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en", "cs"],
            "nodes": {
                "hunting": {
                    "family": "battle",
                    "event_types": ["HUNTING"],
                    "phases": ["ENTER"],
                    "speak_priority": 50,
                    "cooldown_s": 16,
                    "slots": [{"name": "gap", "type": "gap", "example": "1.0"}],
                    "hr_states": ["unknown", "pushing"],
                    "variants": {
                        "en": {"neutral": ["Closing to {gap} seconds."] if filled else []},
                    },
                },
                "hunted": {
                    "family": "battle",
                    "event_types": ["HUNTED"],
                    "phases": ["ENTER"],
                    "speak_priority": 48,
                    "cooldown_s": 16,
                    "slots": [{"name": "gap", "type": "gap", "example": "1.0"}],
                    "hr_states": ["unknown", "pushing"],
                    "variants": {
                        "en": {"neutral": ["Pressure from {gap} seconds."] if filled else []},
                    },
                },
                "overtake": {
                    "family": "position",
                    "event_types": ["OVERTAKE"],
                    "phases": ["RESULT"],
                    "speak_priority": 85,
                    "cooldown_s": 8,
                    "slots": [
                        {"name": "position", "type": "int", "example": "5"},
                        {"name": "target_name", "type": "name", "example": "Rossi"},
                    ],
                    "hr_states": ["unknown", "pushing"],
                    "variants": variants,
                },
            },
            "edges": [
                {
                    "from": "hunting",
                    "to": "overtake",
                    "when": {"same_correlation": True, "min_gap_s": 0.5, "max_gap_s": 30},
                }
            ],
        }
    )


def _overtake() -> object:
    return make_envelope(
        event_type="OVERTAKE",
        phase="RESULT",
        priority=80,
        correlation_id="battle:12",
        metrics={"newPosition": 5},
        target=EventSubject(car_id="12", display_name="Rossi"),
    )


def test_unfilled_graph_is_silent() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=False),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5),
        sink=NullTtsSink(),
    )
    assert director.observe([_overtake()], None, 10.0) is None


def test_disabled_flag_is_silent_even_with_text() -> None:
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=False),
        sink=sink,
    )
    assert director.observe([_overtake()], None, 10.0) is None
    assert sink.spoken == []


def test_same_direction_position_change_does_not_interrupt_finish_or_itself() -> None:
    sink = NullTtsSink(force_busy=True)
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True),
        sink=sink,
    )
    director._current_event_type = "POSITION_LOST"
    director.hero_order_changed(10.0, "POSITION_LOST")
    assert sink.interrupted == 0
    director._current_event_type = "FINISH"
    director.hero_order_changed(11.0, "POSITION_LOST")
    assert sink.interrupted == 0
    director._current_event_type = "HUNTING"
    director.hero_order_changed(12.0, "POSITION_LOST")
    assert sink.interrupted == 1


def test_speaks_filled_variant_and_binds_slots() -> None:
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=sink,
    )
    spoken = director.observe([_overtake()], None, 10.0)
    assert spoken is not None
    assert spoken.text == "He takes P5 from Rossi."
    assert spoken.node_id == "overtake"
    assert spoken.emotion == "unknown"
    assert sink.spoken[-1].text == spoken.text


def test_hr_pushing_selects_emotion_variant() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=True),
        sink=NullTtsSink(),
    )
    bio = BioState(connected=True, status="connected", bpm=140, state="pushing")
    spoken = director.observe([_overtake()], bio, 10.0)
    assert spoken is not None
    assert spoken.emotion == "pushing"
    assert spoken.text == "Now. P5 is his."


def test_missing_hr_is_unknown() -> None:
    assert resolve_emotion(None, True) == "unknown"
    assert resolve_emotion(BioState(connected=False, state="pushing"), True) == "unknown"
    assert resolve_emotion(BioState(connected=True, state="focused"), True) == "focused"


def test_global_cooldown_blocks_second_line() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=4.0),
        sink=NullTtsSink(),
    )
    assert director.observe([_overtake()], None, 10.0) is not None
    assert director.observe([_overtake()], None, 11.0) is None


def test_skips_update_phase() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True),
        sink=NullTtsSink(),
    )
    env = make_envelope(event_type="OVERTAKE", phase="UPDATE", priority=80)
    assert director.observe([env], None, 10.0) is None


def test_slot_bindings_prefer_envelope_metrics() -> None:
    env = _overtake()
    bound = slot_bindings(env, "unknown")
    assert bound["position"] == 5
    assert bound["target_name"] == "Rossi"


def test_decision_log_records_disabled() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=False, decision_log_size=8),
        sink=NullTtsSink(),
    )
    assert director.observe([_overtake()], None, 10.0) is None
    rows = director.decisions()
    assert len(rows) == 1
    assert rows[0]["action"] == "skipped"
    assert rows[0]["reason"] == "disabled"


def test_decision_log_records_spoken_and_busy() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=4.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    spoken = director.observe([_overtake()], None, 10.0)
    assert spoken is not None
    assert director.decisions(1)[-1]["reason"] == "spoken"
    # Still inside estimated TTS duration → busy wins over global_cooldown.
    assert director.observe([_overtake()], None, 10.1) is None
    assert director.decisions(1)[-1]["reason"] == "busy"


def test_decision_log_records_global_cooldown_after_busy() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=4.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    spoken = director.observe([_overtake()], None, 10.0)
    assert spoken is not None
    after_busy = 10.0 + spoken.estimated_seconds + 0.05
    assert after_busy < 10.0 + 4.0
    assert director.observe([_overtake()], None, after_busy) is None
    assert director.decisions(1)[-1]["reason"] == "global_cooldown"


def test_decision_log_records_no_speak_phase() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True),
        sink=NullTtsSink(),
    )
    env = make_envelope(event_type="OVERTAKE", phase="UPDATE", priority=80)
    assert director.observe([env], None, 10.0) is None
    assert director.decisions(1)[-1]["reason"] == "no_speak_phase"


def test_decision_log_records_slot_unbound() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    env = make_envelope(
        event_type="OVERTAKE",
        phase="RESULT",
        priority=80,
        metrics={},  # no position / target → cannot fill template
        target=EventSubject(car_id="12"),
    )
    assert director.observe([env], None, 10.0) is None
    assert director.decisions(1)[-1]["reason"] == "slot_unbound"


def test_mixes_configured_hero_name_into_he_line() -> None:
    graph = parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "hunting": {
                    "family": "battle",
                    "event_types": ["HUNTING"],
                    "phases": ["ENTER"],
                    "speak_priority": 50,
                    "cooldown_s": 1,
                    "slots": [{"name": "gap", "type": "gap", "example": "1.0"}],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["He closes to {gap}."]},
                    },
                }
            },
            "edges": [],
        }
    )
    director = CommentaryDirector(
        graph=graph,
        settings=CommentarySettings(
            enabled=True,
            cooldown_s=0.5,
            use_hr_emotion=False,
            driver_name="Richard",
            driver_nickname="Buchtanen",
        ),
        sink=NullTtsSink(),
    )
    env = make_envelope(
        event_type="HUNTING",
        phase="ENTER",
        priority=50,
        metrics={"gap": 1.0},
    )
    spoken = director.observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.text.startswith("Richard ") or spoken.text.startswith("Buchtanen ")
    assert not spoken.text.startswith("He ")
    assert spoken.hero_name in {"Richard", "Buchtanen"}


def test_observe_picks_off_track_branch_over_generic() -> None:
    graph = parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "incident_generic": {
                    "family": "exception",
                    "event_types": ["INCIDENT"],
                    "phases": ["RESULT"],
                    "speak_priority": 90,
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["Contact in the pack."]}},
                },
                "incident_off": {
                    "family": "exception",
                    "event_types": ["INCIDENT"],
                    "phases": ["RESULT"],
                    "speak_priority": 40,
                    "branch": "off_track",
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["He's off the road."]}},
                },
            },
            "edges": [
                {
                    "from": "incident_generic",
                    "to": "incident_off",
                    "when": {"same_correlation": True, "min_gap_s": 0.0, "max_gap_s": 30},
                }
            ],
        }
    )
    director = CommentaryDirector(
        graph=graph,
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    off = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        priority=90,
        correlation_id="inc:1",
        metrics={"branch": "off_track"},
    )
    spoken = director.observe([off], None, 10.0)
    assert spoken is not None
    assert spoken.text == "He's off the road."

    generic = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        priority=90,
        correlation_id="inc:1",
        metrics={"branch": "unknown"},
    )
    second = director.observe([generic], None, 12.0)
    assert second is not None
    assert second.text == "Contact in the pack."


def _hunt(mode: str, event_type: str = "HUNTING") -> object:
    return make_envelope(
        event_type=event_type,
        phase="ENTER",
        mode=mode,
        priority=30,
        metrics={"gap": 1.2},
    )


def test_gap_hunt_tts_muted_in_practice_and_qualifying() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    assert director.observe([_hunt("PRACTICE")], None, 1.0) is None
    assert director.decisions(1)[-1]["reason"] == "gap_hunt_tts_disabled"
    assert director.observe([_hunt("QUALIFYING", "HUNTED")], None, 2.0) is None
    assert director.decisions(1)[-1]["reason"] == "gap_hunt_tts_disabled"


def test_gap_hunt_tts_speaks_in_race() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    spoken = director.observe([_hunt("RACE")], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "hunting"


def test_gap_hunt_tts_opt_in_practice() -> None:
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(
            enabled=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
            gap_hunt_tts_in_practice=True,
        ),
        sink=NullTtsSink(),
    )
    spoken = director.observe([_hunt("PRACTICE")], None, 1.0)
    assert spoken is not None
    assert spoken.node_id == "hunting"
