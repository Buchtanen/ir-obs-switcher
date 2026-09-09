"""Offline LLM evaluation corpus and latency report (v2 #271).

Implementation-time tooling. Not live-wired. Composes #270 SemanticVerifier
and #269 latency milestones. Does not import commentary or overlay
and does not activate the live narrative actor.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, cast

from irswitch.contracts.primitives import canonical_sha256
from irswitch.events.qwen_transport import load_transport_goldens
from irswitch.events.semantic_verifier import (
    SemanticVerifier,
    VerifyIntent,
    load_verifier_contract,
    load_verifier_corpus,
)

SCHEMA_REPORT = "evaluation-report/2"
SCHEMA_LATENCY = "qwen-latency-report/2"
ENABLED_PROFILES = frozenset({"tight"})
PROFILES = ("tight", "balanced", "loose")
HOLDOUT_CATEGORY = "unknown_fragment"
MODEL_DEFAULT = "qwen3:4b-instruct-2507-q4_K_M"
SHAPE_CODES = frozenset(
    {
        "empty",
        "too_long",
        "sentence_count",
        "token_count",
        "non_en_contract",
        "meta_output",
    }
)
HARD_SEMANTIC_CODES = frozenset(
    {
        "unknown_fragment",
        "unknown_entity",
        "actor_reversed",
        "actor_ambiguous",
        "number_unbound",
        "number_mismatch",
        "unit_mismatch",
        "polarity_mismatch",
        "tense_mismatch",
        "required_missing",
        "forbidden_claim",
        "extra_claim",
        "causal_inference",
        "intent_inference",
        "emotion_inference",
        "medical_inference",
        "prediction_as_result",
        "result_as_prediction",
        "unsupported_certainty",
        "unsafe_negation",
    }
)
MATERIAL_FALSE_ACCEPT_CODES = frozenset(
    {
        "actor_reversed",
        "actor_ambiguous",
        "polarity_mismatch",
        "number_unbound",
        "number_mismatch",
        "unit_mismatch",
        "forbidden_claim",
        "extra_claim",
        "causal_inference",
        "intent_inference",
        "unknown_fragment",
        "unknown_entity",
        "prediction_as_result",
        "result_as_prediction",
        "unsafe_negation",
    }
)


def load_eval_contract() -> dict[str, Any]:
    return load_verifier_contract()


def load_eval_corpus() -> dict[str, Any]:
    return load_verifier_corpus()


def load_eval_model() -> str:
    goldens = load_transport_goldens()
    model = goldens.get("canonicalBackendRequest", {}).get("model")
    return str(model) if isinstance(model, str) and model else MODEL_DEFAULT


@dataclass(frozen=True, slots=True)
class VerdictClass:
    kind: str
    bucket: str
    material: bool


@dataclass(frozen=True, slots=True)
class ProfileGate:
    profile: str
    enabled: bool
    reason: str


@dataclass(frozen=True, slots=True)
class LatencySample:
    residency_evidence: str
    ttfb_ms: int | None
    ttft_ms: int | None
    total_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    token_source: str


@dataclass(frozen=True, slots=True)
class LatencyReport:
    schema_version: str
    residency: str
    retries: int
    metrics: dict[str, dict[str, float] | None]


@dataclass(frozen=True, slots=True)
class ConfigReplay:
    deterministic: bool
    reason: str | None
    apply_sequence: int
    effective_values: dict[str, object]


@dataclass(frozen=True, slots=True)
class AttemptBinding:
    bundle_hash: str
    text_hash: str
    accepted: bool


@dataclass(frozen=True, slots=True)
class EvalIntent:
    profile: str
    model_version: str
    bundle_hash: str
    now_ms: int
    deadline_mono_ms: int
    cancelled: bool = False
    stale_bundle: bool = False
    external_failure: bool = False


@dataclass(frozen=True, slots=True)
class CorpusReport:
    schema_version: str
    profile: str
    model_version: str
    bundle_hash: str
    family_count: int
    case_count: int
    release_count: int
    holdout_count: int
    attributed_cases: int
    false_accepts: int
    false_rejects: int
    material_false_accepts: int
    hard_semantic_rejects: int
    style_rejects: int
    shape_rejects: int
    false_accepts_by_family: dict[str, int]
    false_rejects_by_family: dict[str, int]
    counts_by_family: dict[str, dict[str, int]]
    gate: ProfileGate
    used_live_view: bool
    used_roster: bool
    used_config: bool
    repair_attempts: int


@dataclass(frozen=True, slots=True)
class EvalStep:
    outcome: str
    reason: str | None
    report: CorpusReport | None
    repair_attempts: int
    used_live_view: bool
    used_roster: bool
    used_config: bool


def classify_verdict(
    *,
    expected_accepted: bool,
    accepted: bool,
    reasons: tuple[str, ...],
) -> VerdictClass:
    if accepted:
        kind = "true_accept" if expected_accepted else "false_accept"
        material = (not expected_accepted) and (
            not reasons or any(code in MATERIAL_FALSE_ACCEPT_CODES for code in reasons)
        )
        return VerdictClass(kind, "style" if not reasons else "hard_semantic", material)
    if any(code in HARD_SEMANTIC_CODES for code in reasons):
        bucket = "hard_semantic"
    elif any(code in SHAPE_CODES for code in reasons):
        bucket = "shape"
    else:
        bucket = "style"
    kind = "true_reject" if not expected_accepted else "false_reject"
    return VerdictClass(kind, bucket, False)


def profile_gate(profile: str, material_false_accepts: int) -> ProfileGate:
    if profile not in ENABLED_PROFILES:
        return ProfileGate(profile, False, "holdout_not_promoted")
    if material_false_accepts:
        return ProfileGate(profile, False, "material_false_accept")
    return ProfileGate(profile, True, "holdout_passed")


def token_usage(
    source: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
) -> dict[str, int | str | None]:
    if (
        source == "server"
        and prompt_tokens is not None
        and completion_tokens is not None
        and total_tokens is not None
    ):
        return {
            "source": "server",
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "totalTokens": total_tokens,
        }
    return {
        "source": "unavailable",
        "promptTokens": None,
        "completionTokens": None,
        "totalTokens": None,
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _summarize(samples: tuple[LatencySample, ...], key: str) -> dict[str, float] | None:
    mapping = {"ttfbMs": "ttfb_ms", "ttftMs": "ttft_ms", "totalMs": "total_ms"}
    values = [
        float(getattr(row, mapping[key]))
        for row in samples
        if getattr(row, mapping[key]) is not None
    ]
    if not values:
        return None
    return {
        "median": statistics.median(values),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
        "maximum": max(values),
    }


def aggregate_latency(
    samples: tuple[LatencySample, ...],
    *,
    residency: str,
) -> LatencyReport | None:
    if not samples:
        return None
    evidences = {row.residency_evidence for row in samples}
    expected = "warmup_succeeded" if residency == "warm" else "not_requested"
    if evidences != {expected}:
        return None
    return LatencyReport(
        schema_version=SCHEMA_LATENCY,
        residency=residency,
        retries=0,
        metrics={key: _summarize(samples, key) for key in ("ttfbMs", "ttftMs", "totalMs")},
    )


def replay_config(
    manifest: dict[str, Any],
    transitions: tuple[dict[str, Any], ...],
    lost_sequences: tuple[int, ...] = (),
) -> ConfigReplay:
    sequence = int(manifest["configApplySequence"])
    current_hash = str(manifest["effectiveHash"])
    values = dict(cast(dict[str, object], manifest.get("effectiveValues") or {}))
    if any(int(item) > sequence for item in lost_sequences):
        return ConfigReplay(False, "config_transition_lost", sequence, dict(values))
    for row in transitions:
        apply_sequence = int(row["applySequence"])
        if apply_sequence != sequence + 1 or str(row["oldEffectiveHash"]) != current_hash:
            return ConfigReplay(False, "config_sequence_gap", sequence, dict(values))
        for patch in row["effectivePatch"]:
            key = str(patch["key"])
            if patch.get("redacted") is True:
                values.pop(key, None)
                continue
            values[key] = patch["value"]
        sequence = apply_sequence
        current_hash = str(row["newEffectiveHash"])
    return ConfigReplay(True, None, sequence, values)


def attribute_attempt(bundle_hash: str, text: str, *, accepted: bool) -> AttemptBinding:
    return AttemptBinding(bundle_hash, str(canonical_sha256(text)), accepted)


def _failed(reason: str) -> EvalStep:
    return EvalStep(
        outcome="failed",
        reason=reason,
        report=None,
        repair_attempts=0,
        used_live_view=False,
        used_roster=False,
        used_config=False,
    )


class CorpusEvaluator:
    """Scores the frozen 222-case corpus and emits a profile holdout gate."""

    def evaluate(self, intent: EvalIntent) -> EvalStep:
        if intent.cancelled:
            return _failed("realization_cancelled")
        if intent.now_ms >= intent.deadline_mono_ms:
            return _failed("realization_timeout")
        if intent.stale_bundle:
            return _failed("realization_input_invalid")
        if intent.external_failure:
            return _failed("realization_transport")
        corpus = load_eval_corpus()
        verifier = SemanticVerifier()
        false_accepts_by_family: dict[str, int] = {}
        false_rejects_by_family: dict[str, int] = {}
        counts_by_family: dict[str, dict[str, int]] = {}
        families: set[str] = set()
        release_count = 0
        holdout_count = 0
        false_accepts = 0
        false_rejects = 0
        material_false_accepts = 0
        hard_semantic_rejects = 0
        style_rejects = 0
        shape_rejects = 0
        attributed = 0
        for case in corpus["cases"]:
            family = str(case["family"])
            families.add(family)
            counts = counts_by_family.setdefault(family, {"cases": 0})
            counts["cases"] += 1
            if case["category"] == HOLDOUT_CATEGORY:
                holdout_count += 1
            else:
                release_count += 1
            step = verifier.verify(
                VerifyIntent(
                    text=str(case["text"]),
                    family=family,
                    subject_surface=str(case["surfaceBindings"]["subjectSurface"]),
                    required_claim_surface=str(case["surfaceBindings"]["requiredClaimSurface"]),
                    actor_bindings=(("hero", (str(case["surfaceBindings"]["subjectSurface"]),)),),
                    required_actors=frozenset({"hero"}),
                    now_ms=intent.now_ms,
                    deadline_mono_ms=intent.deadline_mono_ms,
                )
            )
            accepted = bool(step.result is not None and step.result.accepted)
            reasons = () if step.result is None else step.result.reasons
            verdict = classify_verdict(
                expected_accepted=bool(case["expectedAccepted"]),
                accepted=accepted,
                reasons=reasons,
            )
            attribute_attempt(intent.bundle_hash, str(case["text"]), accepted=accepted)
            attributed += 1
            if verdict.kind == "false_accept":
                false_accepts += 1
                false_accepts_by_family[family] = false_accepts_by_family.get(family, 0) + 1
                if verdict.material:
                    material_false_accepts += 1
            elif verdict.kind == "false_reject":
                false_rejects += 1
                false_rejects_by_family[family] = false_rejects_by_family.get(family, 0) + 1
            if not accepted:
                if verdict.bucket == "hard_semantic":
                    hard_semantic_rejects += 1
                elif verdict.bucket == "shape":
                    shape_rejects += 1
                else:
                    style_rejects += 1
        gate = profile_gate(intent.profile, material_false_accepts)
        report = CorpusReport(
            schema_version=SCHEMA_REPORT,
            profile=intent.profile,
            model_version=intent.model_version or load_eval_model(),
            bundle_hash=intent.bundle_hash,
            family_count=len(families),
            case_count=len(corpus["cases"]),
            release_count=release_count,
            holdout_count=holdout_count,
            attributed_cases=attributed,
            false_accepts=false_accepts,
            false_rejects=false_rejects,
            material_false_accepts=material_false_accepts,
            hard_semantic_rejects=hard_semantic_rejects,
            style_rejects=style_rejects,
            shape_rejects=shape_rejects,
            false_accepts_by_family=false_accepts_by_family,
            false_rejects_by_family=false_rejects_by_family,
            counts_by_family=counts_by_family,
            gate=gate,
            used_live_view=False,
            used_roster=False,
            used_config=False,
            repair_attempts=0,
        )
        return EvalStep(
            outcome="succeeded",
            reason=None,
            report=report,
            repair_attempts=0,
            used_live_view=False,
            used_roster=False,
            used_config=False,
        )
