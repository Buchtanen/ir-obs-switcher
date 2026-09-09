"""#271 LLM evaluation corpus and latency report."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.contracts import __all__ as contracts_exports
from irswitch.events import __all__ as events_exports
from irswitch.events.eval_corpus import (
    ENABLED_PROFILES,
    HARD_SEMANTIC_CODES,
    SCHEMA_REPORT,
    CorpusEvaluator,
    EvalIntent,
    LatencySample,
    aggregate_latency,
    attribute_attempt,
    classify_verdict,
    load_eval_contract,
    load_eval_corpus,
    profile_gate,
    replay_config,
    token_usage,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "irswitch" / "events" / "eval_corpus.py"
FIXTURES = ROOT / "tests" / "fixtures" / "eval_corpus"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
BUNDLE = "sha256:" + ("88" * 32)


def _intent(**overrides: object) -> EvalIntent:
    values: dict[str, object] = {
        "profile": "tight",
        "model_version": MODEL,
        "bundle_hash": BUNDLE,
        "now_ms": 10_000,
        "deadline_mono_ms": 20_000,
    }
    values.update(overrides)
    return EvalIntent(**values)  # type: ignore[arg-type]


def _sample(**overrides: object) -> LatencySample:
    values: dict[str, object] = {
        "residency_evidence": "warmup_succeeded",
        "ttfb_ms": 40,
        "ttft_ms": 80,
        "total_ms": 200,
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
        "token_source": "server",
    }
    values.update(overrides)
    return LatencySample(**values)  # type: ignore[arg-type]


def test_frozen_corpus_has_37_families_and_six_axes() -> None:
    contract = load_eval_contract()
    corpus = load_eval_corpus()

    assert contract["enabledFreedom"] == ["tight"]
    assert ENABLED_PROFILES == frozenset({"tight"})
    assert len(corpus["cases"]) == 222
    families = {case["family"] for case in corpus["cases"]}
    axes = {case["category"] for case in corpus["cases"]}
    assert len(families) == 37
    assert axes == {
        "positive",
        "actor_or_polarity_counterexample",
        "value_or_unit_counterexample",
        "temporal_counterexample",
        "forbidden_addition",
        "unknown_fragment",
    }


def test_tight_release_and_holdout_have_zero_material_false_accepts() -> None:
    step = CorpusEvaluator().evaluate(_intent())

    assert step.outcome == "succeeded"
    assert step.report is not None
    assert step.report.schema_version == SCHEMA_REPORT
    assert step.report.profile == "tight"
    assert step.report.model_version == MODEL
    assert step.report.family_count == 37
    assert step.report.case_count == 222
    assert step.report.release_count == 185
    assert step.report.holdout_count == 37
    assert step.report.material_false_accepts == 0
    assert step.report.false_accepts == 0
    assert step.report.gate.enabled is True
    assert step.report.gate.reason == "holdout_passed"
    assert step.report.used_live_view is False
    assert step.repair_attempts == 0


def test_false_accepts_and_rejects_are_reported_by_family_and_profile() -> None:
    step = CorpusEvaluator().evaluate(_intent())
    assert step.report is not None
    assert set(step.report.false_accepts_by_family) == set()
    assert set(step.report.false_rejects_by_family) == set()
    assert step.report.false_rejects == 0
    assert step.report.profile == "tight"
    by_family = step.report.counts_by_family
    assert len(by_family) == 37
    assert all(row["cases"] == 6 for row in by_family.values())


def test_hard_semantic_is_separated_from_style() -> None:
    hard = classify_verdict(
        expected_accepted=False,
        accepted=False,
        reasons=("actor_reversed",),
    )
    style = classify_verdict(expected_accepted=True, accepted=True, reasons=())
    shape = classify_verdict(expected_accepted=False, accepted=False, reasons=("meta_output",))

    assert hard.bucket == "hard_semantic"
    assert hard.kind == "true_reject"
    assert "actor_reversed" in HARD_SEMANTIC_CODES
    assert style.bucket == "style"
    assert style.kind == "true_accept"
    assert shape.bucket == "shape"
    step = CorpusEvaluator().evaluate(_intent())
    assert step.report is not None
    assert step.report.hard_semantic_rejects == 185
    assert step.report.style_rejects == 0
    assert step.report.shape_rejects == 0


def test_balanced_and_loose_stay_disabled_until_own_gate() -> None:
    balanced = profile_gate("balanced", material_false_accepts=0)
    loose = profile_gate("loose", material_false_accepts=0)
    tight_fail = profile_gate("tight", material_false_accepts=1)

    assert balanced.enabled is False
    assert balanced.reason == "holdout_not_promoted"
    assert loose.enabled is False
    assert loose.reason == "holdout_not_promoted"
    assert tight_fail.enabled is False
    assert tight_fail.reason == "material_false_accept"
    step = CorpusEvaluator().evaluate(_intent(profile="balanced"))
    assert step.report is not None
    assert step.report.gate.enabled is False
    assert step.report.gate.reason == "holdout_not_promoted"


def test_latency_separates_warm_and_cold_and_never_mixes_residency() -> None:
    warm = aggregate_latency(
        (_sample(total_ms=200), _sample(ttft_ms=90, total_ms=220)),
        residency="warm",
    )
    cold = aggregate_latency(
        (_sample(residency_evidence="not_requested", ttft_ms=800, total_ms=3400),),
        residency="cold",
    )
    mixed = aggregate_latency(
        (
            _sample(),
            _sample(residency_evidence="not_requested", total_ms=3400),
        ),
        residency="warm",
    )

    assert warm is not None
    assert warm.retries == 0
    assert warm.residency == "warm"
    assert warm.metrics["totalMs"] is not None
    assert warm.metrics["ttftMs"] is not None
    assert cold is not None
    assert cold.residency == "cold"
    assert mixed is None


def test_token_usage_is_never_estimated() -> None:
    server = token_usage("server", 12, 8, 20)
    missing = token_usage("server", 12, None, None)
    local = token_usage("unavailable", 12, 8, 20)

    assert server == {
        "source": "server",
        "promptTokens": 12,
        "completionTokens": 8,
        "totalTokens": 20,
    }
    assert missing == {
        "source": "unavailable",
        "promptTokens": None,
        "completionTokens": None,
        "totalTokens": None,
    }
    assert local == missing


def test_config_replay_starts_from_manifest_and_refuses_gaps() -> None:
    manifest = {
        "desiredHash": "sha256:" + ("11" * 32),
        "effectiveHash": "sha256:" + ("22" * 32),
        "configApplySequence": 4,
        "effectiveValues": {"commentary.enabled": True},
    }
    ok = replay_config(
        manifest,
        (
            {
                "applySequence": 5,
                "oldEffectiveHash": "sha256:" + ("22" * 32),
                "newEffectiveHash": "sha256:" + ("33" * 32),
                "effectivePatch": ({"key": "commentary.enabled", "value": False},),
            },
        ),
    )
    gap = replay_config(
        manifest,
        (
            {
                "applySequence": 7,
                "oldEffectiveHash": "sha256:" + ("22" * 32),
                "newEffectiveHash": "sha256:" + ("33" * 32),
                "effectivePatch": ({"key": "commentary.enabled", "value": False},),
            },
        ),
    )
    lost = replay_config(manifest, (), lost_sequences=(5,))
    redacted = replay_config(
        manifest,
        (
            {
                "applySequence": 5,
                "oldEffectiveHash": "sha256:" + ("22" * 32),
                "newEffectiveHash": "sha256:" + ("33" * 32),
                "effectivePatch": ({"key": "commentary.llm.base_url", "redacted": True},),
            },
        ),
    )

    assert ok.deterministic is True
    assert ok.effective_values["commentary.enabled"] is False
    assert ok.apply_sequence == 5
    assert gap.deterministic is False
    assert gap.reason == "config_sequence_gap"
    assert lost.deterministic is False
    assert lost.reason == "config_transition_lost"
    assert "commentary.llm.base_url" not in redacted.effective_values


def test_completion_and_verdict_bind_to_one_bundle() -> None:
    bound = attribute_attempt(BUNDLE, "Alex is closing on Morgan.", accepted=True)
    other = attribute_attempt("sha256:" + ("99" * 32), "Alex is closing on Morgan.", accepted=True)

    assert bound.bundle_hash == BUNDLE
    assert bound.accepted is True
    assert bound.text_hash.startswith("sha256:")
    assert bound.text_hash == other.text_hash
    assert bound.bundle_hash != other.bundle_hash
    step = CorpusEvaluator().evaluate(_intent())
    assert step.report is not None
    assert step.report.bundle_hash == BUNDLE
    assert step.report.attributed_cases == 222


def test_timeout_cancel_stale_and_external_fail_closed() -> None:
    evaluator = CorpusEvaluator()
    late = evaluator.evaluate(_intent(now_ms=21_000, deadline_mono_ms=20_000))
    cancelled = evaluator.evaluate(_intent(cancelled=True))
    stale = evaluator.evaluate(_intent(stale_bundle=True))
    external = evaluator.evaluate(_intent(external_failure=True))

    assert late.outcome == "failed"
    assert late.reason == "realization_timeout"
    assert late.report is None
    assert cancelled.reason == "realization_cancelled"
    assert stale.reason == "realization_input_invalid"
    assert external.reason == "realization_transport"
    assert cancelled.repair_attempts == 0


def test_listening_fixtures_cover_transition_identity_and_expiry() -> None:
    evaluator = CorpusEvaluator()
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))

    ok = evaluator.evaluate(
        _intent(
            profile=transition["profile"],
            model_version=transition["modelVersion"],
            bundle_hash=transition["bundleHash"],
        )
    )
    assert ok.report is not None
    assert ok.report.material_false_accepts == transition["expectMaterialFalseAccepts"]
    assert ok.report.gate.enabled is transition["expectGateEnabled"]

    reversed_case = classify_verdict(
        expected_accepted=identity["expectAccepted"],
        accepted=False,
        reasons=tuple(identity["expectReasons"]),
    )
    assert reversed_case.kind == "true_reject"
    assert reversed_case.bucket == "hard_semantic"

    late = evaluator.evaluate(
        _intent(now_ms=expiry["nowMs"], deadline_mono_ms=expiry["deadlineMonoMs"])
    )
    assert late.outcome == expiry["expectOutcome"]
    assert late.reason == expiry["expectReason"]


def test_evaluator_is_not_exported_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "eval_corpus" not in events_exports
    assert "CorpusEvaluator" not in contracts_exports
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay"):
        assert banned not in source
    assert "FactView" not in source
    assert "NarrativeRuntime" not in source
