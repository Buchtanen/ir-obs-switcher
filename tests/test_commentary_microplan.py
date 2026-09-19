"""Selected-fact contracts; no Ollama required for these regressions."""

import json

import pytest

from irswitch.commentary.composer import build_skeleton
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.polish import build_polish_request, fact_violation_codes, polish_skeleton
from irswitch.events.envelope import make_envelope
from irswitch.overlay.settings import CommentarySettings


def plan(event="POSITION_LOST", node_id="position_lost", **bindings):
    graph = load_sequence_graph()
    result = build_skeleton(
        make_envelope(event_type=event, phase="RESULT", correlation_id="relation:12"),
        graph.nodes[node_id],
        graph=graph,
        story={"race": {"class_position": 13}, "situation": {"current_lap": 99}},
        bindings=bindings,
        emotion="unknown",
        language="en",
    )
    assert result is not None
    return result


def test_selected_facts_replace_skeleton_as_validator_authority():
    result = plan(position=13, target_name="Rossi")
    assert result.fact_pack["version"] == "commentary-facts/3"
    assert result.fact_count == 1
    assert "P13" in result.text and "Rossi" in result.text
    assert not fact_violation_codes(
        "Position lost.", "He drops behind Rossi to P13.", fact_pack=result.fact_pack
    )
    assert "invented_number" in fact_violation_codes(
        result.text, "He drops behind Rossi to P13 on lap 99.", fact_pack=result.fact_pack
    )


def test_position_gain_is_not_evidence_of_an_on_track_pass():
    result = plan("POSITION_GAINED", "position_gained", position=8, target_name="Rossi")
    assert "passes" not in result.text
    assert "forbidden_pass" in fact_violation_codes(
        result.text, "He passes Rossi to take P8.", fact_pack=result.fact_pack
    )


def test_two_front_does_not_match_direction_across_other_actor():
    result = plan(
        "BATTLE_FOR_POSITION",
        "two_front_battle",
        front_target_name="Rossi",
        rear_target_name="Meyer",
    )
    assert not fact_violation_codes(
        result.text,
        "He attacks Rossi ahead while Meyer applies pressure behind.",
        fact_pack=result.fact_pack,
    )
    for bad in (
        "He attacks Meyer ahead while Rossi applies pressure behind.",
        "He follows Rossi and Meyer.",
        "Rossi attacks ahead while Meyer applies pressure behind.",
        "Rossi accelerates forward and he attacks; Meyer pressures from behind.",
    ):
        assert fact_violation_codes(result.text, bad, fact_pack=result.fact_pack)


def test_numeric_precision_is_not_changed_by_normalization():
    result = plan("HUNTING", "hunting", target_name="Rossi", gap="0.05 seconds")
    assert "invented_number" in fact_violation_codes(
        result.text, "He closes on Rossi, 0.5 seconds ahead.", fact_pack=result.fact_pack
    )
    assert not fact_violation_codes(
        result.text, "He closes on Rossi, 0.050 seconds ahead.", fact_pack=result.fact_pack
    )


def test_invalid_source_metrics_are_not_selected_for_realization():
    for invalid in ("nan", "inf", "-0.5 seconds", "0 seconds"):
        result = plan("HUNTING", "hunting", target_name="Rossi", gap=invalid)
        selected = " ".join(
            fact["text"]
            for key in ("required_facts", "optional_facts")
            for fact in result.fact_pack[key]
        )
        assert invalid not in selected
        assert result.fact_pack["target"].get("gap") is None


def test_position_event_retains_outcome_but_omits_invalid_position():
    result = plan("POSITION_GAINED", "position_gained", position=0)
    assert result.text == "He gains a position."
    assert not result.fact_pack["allowed_numbers"]


def test_compact_request_omits_anchor_telemetry_and_changes_retry():
    result = plan(position=13, target_name="Rossi")
    settings = CommentarySettings()
    first = build_polish_request("Do not copy this anchor.", settings, fact_pack=result.fact_pack)
    strict = build_polish_request(
        result.text, settings, fact_pack=result.fact_pack, rejected=["invented_number"]
    )
    prompt = " ".join(message["content"] for message in first["messages"])
    assert "Do not copy" not in prompt and "99" not in prompt
    assert "allowed_numbers" not in prompt and "provenance" not in prompt
    assert first["messages"] != strict["messages"]
    assert len(prompt) < 1400


def test_style_warning_does_not_retry_and_attempts_are_recorded():
    result = plan(position=13, target_name="Rossi")
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return json.dumps(
            {"choices": [{"message": {"content": "He drops behind Rossi to P13"}}]}
        ).encode()

    outcome = polish_skeleton(
        result.text,
        load_sequence_graph().nodes["position_lost"],
        CommentarySettings(llm_polish=True),
        fact_pack=result.fact_pack,
        opener=opener,
    )
    assert outcome.outcome == "ok" and len(calls) == 1
    assert outcome.text.endswith(".")
    assert outcome.debug_record(node_id="position_lost", event_type="POSITION_LOST")["attemptLog"]


def test_only_one_semantic_retry_then_complete_canonical_fallback():
    result = plan(position=13, target_name="Rossi")
    calls = []

    def opener(req, timeout):
        calls.append(json.loads(req.data))
        return json.dumps(
            {"choices": [{"message": {"content": "Hamilton wins on lap 99."}}]}
        ).encode()

    outcome = polish_skeleton(
        result.text,
        load_sequence_graph().nodes["position_lost"],
        CommentarySettings(llm_polish=True, llm_max_attempts=8),
        fact_pack=result.fact_pack,
        opener=opener,
    )
    assert outcome.attempts == len(calls) == 2
    assert calls[0]["messages"] != calls[1]["messages"]
    assert outcome.text == result.text


@pytest.mark.parametrize("error", [TimeoutError(), OSError("offline")])
def test_outage_does_not_retry_identical_request(error):
    result = plan(position=13, target_name="Rossi")

    def opener(req, timeout):
        raise error

    outcome = polish_skeleton(
        result.text,
        load_sequence_graph().nodes["position_lost"],
        CommentarySettings(llm_polish=True),
        fact_pack=result.fact_pack,
        opener=opener,
    )
    assert outcome.attempts == 1
    assert outcome.text == result.text
