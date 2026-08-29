"""TTS intonation validator."""

from __future__ import annotations

from irswitch.commentary.graph import GraphNode, SlotSpec, TtsLimits
from irswitch.commentary.validator import fill_slots, issues_as_codes, validate_utterance


def _node() -> GraphNode:
    return GraphNode(
        id="overtake",
        family="position",
        event_types=("OVERTAKE",),
        phases=("RESULT",),
        speak_priority=85,
        cooldown_s=8.0,
        slots=(
            SlotSpec("position", "int", "5"),
            SlotSpec("target_name", "name", "Rossi"),
        ),
        hr_states=("unknown", "pushing"),
        tts=TtsLimits(max_chars=90, max_seconds=5.5),
    )


def test_good_line_passes() -> None:
    issues = validate_utterance("You take P{position} from {target_name}.", _node())
    assert issues == []


def test_rejects_missing_terminal_punct_and_all_caps() -> None:
    node = _node()
    assert "terminal_punct" in issues_as_codes(validate_utterance("you take the place", node))
    assert "all_caps" in issues_as_codes(validate_utterance("HUGE OVERTAKE NOW.", node))


def test_rejects_stacked_punct_emoji_and_unknown_slot() -> None:
    node = _node()
    assert "multi_punct" in issues_as_codes(validate_utterance("Pass!!", node))
    assert "emoji" in issues_as_codes(validate_utterance("Nice pass 🔥.", node))
    assert "unknown_slot" in issues_as_codes(validate_utterance("Car {car_id} done.", node))


def test_ssml_break_and_bad_tag() -> None:
    node = _node()
    ok = validate_utterance(
        'Clear. <break time="200ms"/> You take P{position}.',
        node,
    )
    assert ok == []
    codes = issues_as_codes(validate_utterance("<audio src='x.wav'/> Hello.", node))
    assert "ssml_tag" in codes or "ssml_parse" in codes
    long_break = issues_as_codes(validate_utterance('Wait. <break time="900ms"/> Now.', node))
    assert "ssml_break" in long_break
    bad_unit = issues_as_codes(validate_utterance('Wait. <break time="200s"/> Now.', node))
    assert "ssml_break" in bad_unit


def test_fill_slots_leaves_unknown_placeholders() -> None:
    assert fill_slots("P{position} vs {target_name}.", {"position": 3}) == "P3 vs {target_name}."
