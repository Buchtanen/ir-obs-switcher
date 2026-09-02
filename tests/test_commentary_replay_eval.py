"""Recorded commentary evaluation is deterministic and proposition-based."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.commentary.replay_eval import (
    EvaluationCase,
    evaluate_case,
    evaluate_corpus,
    load_corpus,
    load_polish_records,
    replay_live,
    resolve_cases,
    summarize,
)

RECORDINGS = Path("recordings")
CORPUS = Path("tests/fixtures/commentary/commentary_eval_cases.json")
TAPES = sorted(RECORDINGS.glob("overlay-20260901T*.jsonl"))


def test_recorded_baseline_reproduces_analysis_counts() -> None:
    summary = summarize(load_polish_records(TAPES))

    assert summary["operations"] == 106
    assert summary["modelCalls"] == 386
    assert summary["fallbacks"] == 65
    assert summary["fallbackRate"] == 0.6132
    assert summary["tokens"]["medianPrompt"] == 861.0
    assert summary["attempts"]["5"] == 64


def test_curated_corpus_is_broad_and_resolves_to_tape_rows() -> None:
    cases = load_corpus(CORPUS)
    records = load_polish_records(TAPES)
    categories = {case.category for case in cases}

    assert len(cases) >= 30
    assert {
        "hunting",
        "hunted",
        "two_front",
        "position_gained",
        "position_lost",
        "leader_change",
        "incident_aftermath",
        "finish",
        "sof_brief",
        "green",
    } <= categories
    assert len(resolve_cases(cases, records)) == len(cases)


def test_corpus_captures_known_semantic_and_source_defects() -> None:
    report = evaluate_corpus(load_corpus(CORPUS), load_polish_records(TAPES))

    assert report["issuesByCode"].get("source_contract_mismatch", 0) == 0
    assert report["issuesByCode"]["invalid_source_fact"] >= 2
    assert report["issuesByCode"]["ineligible_source_story"] >= 3
    assert report["issuesByCode"]["forbidden_term"] >= 3
    assert report["issuesByCode"]["invented_selected_fact_number"] >= 1


def test_live_replay_rejects_non_http_endpoint_before_opening() -> None:
    record = load_polish_records(TAPES)[0]

    with pytest.raises(ValueError, match="must use http or https"):
        replay_live(record, "file:///tmp/commentary-response.json")


def test_selected_fact_number_check_does_not_use_global_telemetry(tmp_path: Path) -> None:
    tape = tmp_path / "tape.jsonl"
    tape.write_text(
        json.dumps(
            {
                "type": "llm_polish",
                "eventType": "HUNTING",
                "nodeId": "hunting",
                "outcome": "ok",
                "attempts": 1,
                "latencyMs": 10,
                "skeleton": "He closes on Rossi at 0.7 seconds.",
                "polished": "He closes on Rossi at 0.7 seconds, only 99 laps to go.",
                "response": {"usage": {"prompt_tokens": 10, "completion_tokens": 8}},
                "request": {"model": "fake"},
                "factPack": {
                    "required_facts": [
                        {
                            "id": "beat:relation",
                            "text": "He closes on Rossi.",
                            "relation": "hero_closing_on_target",
                        }
                    ],
                    "optional_facts": [{"id": "target:gap", "required_numbers": ["0.7"]}],
                    "allowed_numbers": ["0.7", "99"],
                    "forbidden_claims": ["on_track_pass", "hero_leads"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    record = load_polish_records([tape])[0]
    case = EvaluationCase(
        id="selected_numbers",
        tape=tape.name,
        polish_ordinal=1,
        category="hunting",
        story_state="live",
        required_fact_ids=("beat:relation",),
        expected_relation="hero_closing_on_target",
        forbidden_claims=("on_track_pass", "hero_leads"),
        forbidden_terms=(),
        invalid_source_fact_ids=(),
        expected_eligibility="speak",
        note="",
    )

    issues = evaluate_case(case, record)

    assert any(
        issue.code == "invented_selected_fact_number" and "99" in issue.detail for issue in issues
    )
