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
                "neutral": ["You take P{position} from {target_name}."],
                "pushing": ["Now. P{position} is yours."],
            },
            "cs": {"neutral": ["Bereš P{position}."]},
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


def test_speaks_filled_variant_and_binds_slots() -> None:
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=_graph(filled=True),
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=sink,
    )
    spoken = director.observe([_overtake()], None, 10.0)
    assert spoken is not None
    assert spoken.text == "You take P5 from Rossi."
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
    assert spoken.text == "Now. P5 is yours."


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
