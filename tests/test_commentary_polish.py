"""Tests for optional commentary LLM polish."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.polish import (
    build_polish_request,
    fact_violation_codes,
    polish_skeleton,
)
from irswitch.commentary.tts import ProcessTtsSink, build_tts_sink
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import (
    CommentarySettings,
    OverlaySettings,
    OverlayTapeSettings,
    OverlayV4Settings,
)
from irswitch.overlay.tape import OverlaySessionTape
from irswitch.util.logging import set_runtime_log_level


def _open_tape(tmp_path: Path) -> OverlaySessionTape:
    tape = OverlaySessionTape(get_version=lambda: "test")
    settings = OverlaySettings(
        v4=OverlayV4Settings(renderer=True),
        tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)),
    )
    tape.observe(
        RaceState(
            connected=True,
            overlay_mode="RACE",
            session_state=4,
            subsession_id="1",
            session_num=0,
        ),
        10.0,
        settings,
    )
    return tape


def test_polish_disabled_returns_skeleton() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=False)
    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings)
    assert outcome.outcome == "fallback_disabled"
    assert outcome.text == "Gap 0.42 to Smith."


def test_polish_uses_mock_http_response() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_timeout_s=5.0)

    def opener(req, timeout):  # noqa: ARG001
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "He is closing on Smith, gap 0.42 seconds.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }
        return json.dumps(payload).encode("utf-8")

    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings, opener=opener)
    assert outcome.outcome == "ok"
    assert "0.42" in outcome.text
    assert outcome.request["model"] == settings.llm_model


def test_polish_rejects_non_http_scheme() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(
        llm_polish=True,
        llm_base_url="file:///tmp/evil",
    )
    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings)
    assert outcome.outcome == "fallback_error"
    assert outcome.text == ""


def test_polish_timeout_skips_skeleton() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_max_attempts=3)

    def opener(_req, timeout):  # noqa: ARG001
        raise TimeoutError

    skeleton = "Gap 0.42 to Smith."
    outcome = polish_skeleton(skeleton, node, settings, opener=opener)
    assert outcome.outcome == "fallback_timeout"
    assert outcome.text == ""
    assert outcome.attempts == 3


def test_tape_commentary_and_llm_rows(tmp_path: Path) -> None:
    tape = _open_tape(tmp_path)
    tape.record_commentary(
        {
            "action": "spoken",
            "reason": "spoken",
            "eventType": "HUNTING",
            "nodeId": "hunting",
            "text": "Gap 0.42.",
        },
        11.0,
        None,
    )
    tape.record_llm_polish(
        {
            "nodeId": "hunting",
            "outcome": "ok",
            "skeleton": "Gap 0.42.",
            "spoken": "He closes on Smith.",
        },
        11.5,
        None,
    )
    path = tape.path
    assert path is not None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    types = [row["type"] for row in rows]
    assert "commentary" in types
    assert "llm_polish" in types


def test_build_polish_request_shape() -> None:
    settings = CommentarySettings(llm_model="qwen2.5:3b")
    req = build_polish_request("Line one.", settings)
    assert req["model"] == "qwen2.5:3b"
    assert req["think"] is False
    assert req["reasoning_effort"] == "none"
    assert req["messages"][0]["role"] == "system"
    assert "Line one." in req["messages"][1]["content"]


def test_czech_prompt_and_compact_fact_pack_are_forwarded() -> None:
    req = build_polish_request(
        "Dokončuje osmé kolo na sedmém místě.",
        CommentarySettings(),
        locale="cs",
        fact_pack={"version": "commentary-facts/1", "beat": {"node": "lap_complete"}},
        composition_path=("beat", "session"),
    )

    system = req["messages"][0]["content"]
    user = req["messages"][1]["content"]
    assert "diváky" in system
    assert "FACTS:" in user
    assert '"lap_complete"' in user
    assert "COMPOSITION_PATH: beat -> session" in user


def test_live_prompt_fits_node_tts_budget() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    req = build_polish_request("Gap to Smith.", CommentarySettings(llm_max_tokens=220), node=node)
    system = req["messages"][0]["content"]
    lowered = system.lower()
    assert "same sentence count" in lowered
    assert "you are polishing" not in lowered
    assert "two sentences preferred" not in lowered
    assert "do not reintroduce abbreviations" in lowered
    assert "not pole" in lowered
    assert "not a lead" in lowered
    assert "compass" in lowered
    cap = str(len("Gap to Smith.") + 40)
    assert cap in system
    assert f"{node.tts.max_seconds:g}" in system
    assert req["max_tokens"] <= len("Gap to Smith.") + 40 + 16
    assert req["max_tokens"] < 220


def test_grounded_prompt_uses_full_node_budget_and_explicit_fact_roles() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    facts = {
        "version": "commentary-facts/2",
        "anchor": "He is closing on Rossi.",
        "required_facts": [
            {
                "id": "beat:relation",
                "text": "He is closing on Rossi",
                "required_terms": ["Rossi"],
            }
        ],
        "optional_facts": [
            {"id": "target:gap", "text": "the gap is zero point seven seconds"}
        ],
        "forbidden_claims": ["on_track_pass", "hero_leads"],
        "allowed_numbers": ["0.7"],
        "recent": ["Rossi was P4."],
    }

    req = build_polish_request(
        facts["anchor"],
        CommentarySettings(llm_max_tokens=360),
        node=node,
        fact_pack=facts,
    )

    system = req["messages"][0]["content"].lower()
    user = req["messages"][1]["content"]
    assert "one or two sentences" in system
    assert "same sentence count" not in system
    assert str(node.tts.max_chars) in system
    assert req["max_tokens"] > len(facts["anchor"]) + 40
    assert "ANCHOR:" in user
    assert "REQUIRED_FACTS:" in user
    assert "OPTIONAL_FACTS:" in user
    assert "Rossi was P4" not in user


def test_grounded_fact_lock_rejects_forbidden_pass_and_new_number() -> None:
    facts = {
        "version": "commentary-facts/2",
        "anchor": "Meyer takes the lead from Rossi.",
        "required_facts": [
            {
                "id": "beat:leader_change",
                "text": "Meyer takes the lead from Rossi",
                "required_terms": ["Meyer", "Rossi"],
                "relation": "class_leader_changed",
            }
        ],
        "optional_facts": [],
        "forbidden_claims": ["on_track_pass"],
        "allowed_numbers": [],
    }
    codes = fact_violation_codes(
        facts["anchor"],
        "Meyer passes Rossi for the lead on lap 99.",
        fact_pack=facts,
    )
    assert "forbidden_pass" in codes
    assert "invented_number" in codes

    invented_name = fact_violation_codes(
        facts["anchor"],
        "Meyer takes the lead from Hamilton.",
        fact_pack={**facts, "allowed_names": ["Meyer", "Rossi"]},
    )
    assert "invented_name" in invented_name

    missing_relation = fact_violation_codes(
        facts["anchor"],
        "Meyer and Rossi remain in view.",
        fact_pack=facts,
    )
    assert "missing_required_fact" in missing_relation

    result_facts = {
        **facts,
        "anchor": "He finishes the session in P29.",
        "required_facts": [
            {
                "id": "beat:wrap",
                "text": "He finishes the session in P29.",
                "required_terms": [],
                "required_numbers": ["29"],
                "relation": "session_result",
            }
        ],
        "forbidden_claims": [],
        "allowed_names": [],
        "allowed_numbers": ["29"],
    }
    assert "missing_required_fact" in fact_violation_codes(
        result_facts["anchor"],
        "The session ends.",
        fact_pack=result_facts,
    )


def test_grounded_generation_may_expand_anchor_with_optional_fact() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True)
    facts = {
        "version": "commentary-facts/2",
        "anchor": "The chase is building.",
        "required_facts": [
            {
                "id": "beat:relation",
                "text": "He is closing on Rossi.",
                "required_terms": ["Rossi"],
                "relation": "hero_closing_on_target",
            }
        ],
        "optional_facts": [{"id": "target:gap", "text": "The gap is 0.7 seconds."}],
        "forbidden_claims": ["on_track_pass", "hero_leads"],
        "allowed_names": ["Rossi"],
        "allowed_numbers": ["0.7"],
    }
    generated = "The chase is building as he closes on Rossi. The gap is down to 0.7 seconds."

    def opener(_req, timeout):  # noqa: ARG001
        return json.dumps({"choices": [{"message": {"content": generated}}]}).encode("utf-8")

    outcome = polish_skeleton(
        facts["anchor"],
        node,
        settings,
        fact_pack=facts,
        opener=opener,
    )
    assert len(generated) > len(facts["anchor"]) + 40
    assert outcome.outcome == "ok"
    assert outcome.text == generated


def test_polish_prompt_keeps_featured_driver() -> None:
    req = build_polish_request(
        "He closes the gap.",
        CommentarySettings(),
        driver_names=("Richard", "Buchtanen"),
    )
    system = req["messages"][0]["content"]
    assert "featured driver is Richard / Buchtanen" in system
    assert "stream viewers" in system.lower() or "protagonist" in system.lower()
    assert "you/your" in system.lower() or "never address" in system.lower()
    assert "comma" in system.lower() or "vocative" in system.lower()


def test_past_prompt_also_states_tts_budget() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    req = build_polish_request("Gap to Smith.", CommentarySettings(), node=node, past=True)
    system = req["messages"][0]["content"]
    assert "do not invent that a pass" in system.lower()
    assert str(len("Gap to Smith.") + 40) in system


def test_similar_length_restyle_is_kept() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True)
    skeleton = "Gap 0.42 to Smith."
    restyle = "He closes on Smith, gap 0.42 seconds."

    def opener(_req, timeout):  # noqa: ARG001
        return json.dumps({"choices": [{"message": {"content": restyle}}]}).encode("utf-8")

    outcome = polish_skeleton(skeleton, node, settings, opener=opener)
    assert outcome.outcome == "ok"
    assert outcome.text == restyle


def test_added_sentence_retries_then_skips_skeleton() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_max_attempts=2)
    richer = (
        "He is closing on Smith, the gap sitting at 0.42 seconds. "
        "Viewers still have a live chase on screen."
    )
    calls: list[int] = []

    def opener(_req, timeout):  # noqa: ARG001
        calls.append(1)
        return json.dumps({"choices": [{"message": {"content": richer}}]}).encode("utf-8")

    skeleton = "Gap 0.42 to Smith."
    outcome = polish_skeleton(skeleton, node, settings, opener=opener)
    assert outcome.outcome == "retry_exhausted"
    assert outcome.text == ""
    assert len(calls) == 2
    assert "expanded" in (outcome.response or {}).get("validatorCodes", [])


def test_three_sentence_polish_retries_then_skips_skeleton() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_max_attempts=2)
    long_copy = (
        "Melillo continues to lead, but the pack is closing fast. "
        "The race is heating up, and the lead could change at any moment. "
        "Stay tuned for the latest developments on this broadcast!"
    )

    def opener(_req, timeout):  # noqa: ARG001
        return json.dumps({"choices": [{"message": {"content": long_copy}}]}).encode("utf-8")

    skeleton = "Melillo remains ahead, but the pressure is changing."
    outcome = polish_skeleton(skeleton, node, settings, opener=opener)
    assert outcome.outcome == "retry_exhausted"
    assert outcome.text == ""
    codes = (outcome.response or {}).get("validatorCodes", [])
    assert "banned_phrase" in codes or "expanded" in codes or "invented_lead" in codes


def test_process_sink_polish_hook_called(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    captured: list[dict] = []
    forwarded: dict[str, object] = {}
    final_spoken: list[str] = []

    def fake_polish(
        skeleton,
        _node,
        settings,
        *,
        opener=None,
        past=False,
        driver_names=(),
        **extra,
    ):  # noqa: ARG001
        forwarded.update(extra)
        return type(
            "O",
            (),
            {
                "text": "Polished line.",
                "outcome": "ok",
                "latency_ms": 1.0,
                "skeleton": skeleton,
                "request": {},
                "response": None,
                "debug_record": lambda self, node_id="", event_type="": {
                    "outcome": "ok",
                    "spoken": "Polished line.",
                },
            },
        )()

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", fake_polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda *args, **kwargs: type("R", (), {"backend": "null", "spoken": True, "error": None})(),
    )

    settings = CommentarySettings(llm_polish=True, tts_backend="null")
    sink = ProcessTtsSink(
        settings=settings,
        on_polish_debug=captured.append,
        on_spoken_text=final_spoken.append,
    )
    from irswitch.commentary.tts import CommentaryUtterance

    sink._speak(
        CommentaryUtterance(
            node_id="hunting",
            locale="en",
            emotion="focused",
            text="Skeleton.",
            event_type="HUNTING",
            event_id="e1",
            correlation_id="c1",
            estimated_seconds=2.0,
            node=node,
            fact_pack={"version": "commentary-facts/1"},
            composition_path=("beat", "detail"),
        )
    )
    assert captured
    assert captured[0]["outcome"] == "ok"
    assert forwarded["locale"] == "en"
    assert forwarded["fact_pack"] == {"version": "commentary-facts/1"}
    assert forwarded["composition_path"] == ("beat", "detail")
    assert final_spoken == ["Polished line."]


def test_build_tts_sink_omits_hook_when_polish_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("irswitch.commentary.tts.detect_backend", lambda preferred="auto": "sapi")
    sink = build_tts_sink(CommentarySettings(llm_polish=False, tts_backend="sapi"))
    assert isinstance(sink, ProcessTtsSink)
    assert sink.on_polish_debug is None


def test_fact_violation_codes_from_vod_inversions() -> None:
    assert "invented_lead" in fact_violation_codes(
        "Wind two meters per second across the circuit.",
        "Richard maintains his lead at two meters per second.",
    )
    assert "invented_pole" in fact_violation_codes(
        "He holds P two.",
        "Richard holds pole position.",
    )
    assert "polarity_flip" in fact_violation_codes(
        "Adamson is ahead by zero point eight seven seconds.",
        "Richard maintains a narrow lead.",
    )
    assert "invented_pass" in fact_violation_codes(
        "He is closing on Maestre, gap zero point six six seconds.",
        "Richard inches past Maestre by six centimeters.",
    )
    assert "surname_as_direction" in fact_violation_codes(
        "West is coming back.",
        "Richard is looking westward.",
    )
    assert "hero_name_fusion" in fact_violation_codes(
        "Richard. Ohanian is closing.",
        "Richard Ohanian is closing.",
    )
    assert "hero_vocative" in fact_violation_codes(
        "That's a best lap without fuss.",
        "Richard, that's a best lap without fuss.",
        driver_names=("Richard",),
    )
    assert "hero_vocative" in fact_violation_codes(
        "That's a best lap without fuss.",
        "Richard. That's a best lap without fuss.",
        driver_names=("Richard",),
    )
    assert (
        fact_violation_codes(
            "He closes the gap.",
            "Richard closes the gap.",
            driver_names=("Richard",),
        )
        == []
    )


def test_fact_lock_rejects_two_front_role_swap() -> None:
    facts = {
        "front_target": {"name": "Rossi", "gap": "zero point seven seconds"},
        "rear_target": {"name": "Berg", "gap": "zero point five seconds"},
    }
    codes = fact_violation_codes(
        "He attacks Rossi ahead while Berg applies pressure behind.",
        "Berg is the target ahead while Rossi attacks from behind.",
        fact_pack=facts,
    )
    assert "two_front_polarity_conflict" in codes
    assert "live_call_prefix" in fact_violation_codes(
        "Gap zero point four two to Smith.",
        "Live Call: He is closing on Smith.",
    )
    assert (
        fact_violation_codes(
            "Gap 0.42 to Smith.",
            "He is closing on Smith, gap 0.42 seconds.",
        )
        == []
    )


def test_polish_retries_when_model_addresses_the_driver() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_max_attempts=2)
    calls: list[int] = []

    def opener(_req, timeout):  # noqa: ARG001
        calls.append(1)
        return json.dumps(
            {"choices": [{"message": {"content": "You keep closing on Smith, gap 0.42 seconds."}}]}
        ).encode("utf-8")

    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings, opener=opener)
    assert outcome.outcome == "retry_exhausted"
    assert outcome.text == ""
    assert len(calls) == 2
    assert "address_driver" in (outcome.response or {}).get("validatorCodes", [])


def test_polish_retries_when_model_uses_hero_vocative() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_max_attempts=2)
    calls: list[int] = []

    def opener(_req, timeout):  # noqa: ARG001
        calls.append(1)
        return json.dumps(
            {"choices": [{"message": {"content": "Richard, the gap to Smith is 0.42 seconds."}}]}
        ).encode("utf-8")

    outcome = polish_skeleton(
        "Gap 0.42 to Smith.",
        node,
        settings,
        opener=opener,
        driver_names=("Richard",),
    )
    assert outcome.outcome == "retry_exhausted"
    assert outcome.text == ""
    assert len(calls) == 2
    assert "hero_vocative" in (outcome.response or {}).get("validatorCodes", [])


def test_polish_retries_fact_break_then_keeps_good_rewrite() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_max_attempts=5)
    calls = {"n": 0}

    def opener(_req, timeout):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] < 3:
            content = "Richard maintains a narrow lead over Adamson."
        else:
            content = "Adamson is still ahead by zero point eight seven seconds."
        return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")

    skeleton = "Adamson is ahead by zero point eight seven seconds."
    outcome = polish_skeleton(skeleton, node, settings, opener=opener)
    assert outcome.outcome == "ok"
    assert outcome.attempts == 3
    assert "ahead" in outcome.text.lower()
    assert "lead" not in outcome.text.lower()


def test_process_sink_speaks_skeleton_when_retry_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    spoken: list[str] = []

    def fake_polish(
        skeleton, _node, settings, *, opener=None, past=False, driver_names=()
    ):  # noqa: ARG001
        return type(
            "O",
            (),
            {
                "text": "",
                "outcome": "retry_exhausted",
                "latency_ms": 1.0,
                "skeleton": skeleton,
                "request": {},
                "response": {"content": "Richard maintains a narrow lead."},
                "debug_record": lambda self, node_id="", event_type="": {
                    "outcome": "retry_exhausted",
                    "spoken": "",
                },
            },
        )()

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", fake_polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda text, **kwargs: spoken.append(text)
        or type("R", (), {"backend": "null", "spoken": True, "error": None})(),
    )

    settings = CommentarySettings(llm_polish=True, tts_backend="null")
    sink = ProcessTtsSink(settings=settings)
    from irswitch.commentary.tts import CommentaryUtterance

    sink._speak(
        CommentaryUtterance(
            node_id="hunting",
            locale="en",
            emotion="focused",
            text="Adamson is ahead.",
            event_type="HUNTING",
            event_id="e1",
            correlation_id="c1",
            estimated_seconds=2.0,
            node=node,
        )
    )
    assert spoken == ["Adamson is ahead."]


def test_runtime_debug_gate_for_tape(monkeypatch: pytest.MonkeyPatch) -> None:
    set_runtime_log_level("INFO")
    assert logging.getLogger().getEffectiveLevel() == logging.INFO
    set_runtime_log_level("DEBUG")
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
    set_runtime_log_level("INFO")
