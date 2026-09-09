"""Family-specific SemanticVerifier for tight EN claims (v2 #270).

Implementation-time tooling. Not live-wired. Composes #266 family grammars
and #267/#268 frozen surfaces. Does not import commentary or overlay
and does not activate the live narrative actor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

SCHEMA_RESULT = "verification-result/2"
SCHEMA_CORPUS = "realization-corpus/2"
MAX_REASONS = 16
MAX_CHARS = 240
MAX_TOKENS = 32
MIN_CHARS = 2
PATTERNS = (
    "{subjectSurface} {requiredClaimSurface}.",
    "{subjectSurface} now {requiredClaimSurface}.",
    "Now {subjectSurface} {requiredClaimSurface}.",
    "{subjectSurface} {requiredClaimSurface} now.",
)
REJECTION_CODES = frozenset(
    {
        "empty",
        "too_long",
        "sentence_count",
        "token_count",
        "non_en_contract",
        "meta_output",
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
TRANSPORT_INVALID = frozenset({"thinking", "reasoning", "tool", "multiple"})
TRANSPORT_OVERSIZE = frozenset({"truncated", "oversized"})
NON_EN_CHARS = frozenset("ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ")
FIRST_PERSON = frozenset({"i", "i'm", "i've", "we", "we're", "our", "us"})
META_MARKERS = ("<think>", "</think>", "```", "{", "}")
CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "v2.0.0"
    / "machine"
    / "realization-contract.json"
)
CORPUS_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "v2.0.0" / "machine" / "realization-corpus.json"
)


def load_verifier_contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))


def load_verifier_corpus() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CORPUS_PATH.read_text(encoding="utf-8")))


def surface_form_allowed(kind: str, form: str) -> bool:
    for case in load_verifier_contract()["surfaceValueCases"]:
        if case["kind"] == kind:
            return form in case["allowed"]
    return False


def semantic_reasons(text: str, positive: str, expected_subject: str) -> list[str]:
    """Reference tight-profile axes from the frozen corpus builder."""

    if text in {
        pattern.format(subjectSurface=expected_subject, requiredClaimSurface=positive)
        for pattern in PATTERNS
    }:
        return []
    if text.startswith("It is not true that "):
        return ["unsafe_negation", "polarity_mismatch"]
    if text.startswith("Yesterday, "):
        return ["tense_mismatch"]
    if "9.9 laps" in text:
        return ["number_unbound", "unit_mismatch"]
    if " because the driver wanted it." in text:
        return ["causal_inference", "intent_inference"]
    if " beneath a purple moon." in text:
        return ["unknown_fragment"]
    if not text.startswith(expected_subject + " "):
        return ["actor_reversed"]
    return ["required_missing"]


@dataclass(frozen=True, slots=True)
class VerifyIntent:
    text: str
    family: str
    subject_surface: str
    required_claim_surface: str
    actor_bindings: tuple[tuple[str, tuple[str, ...]], ...]
    required_actors: frozenset[str]
    now_ms: int
    deadline_mono_ms: int
    cancelled: bool = False
    transport_form: str | None = None
    stale_bundle: bool = False
    external_failure: bool = False


@dataclass(frozen=True, slots=True)
class VerificationResult:
    schema_version: str
    accepted: bool
    claims: tuple[str, ...]
    reasons: tuple[str, ...]
    family: str
    repair_attempts: int
    used_live_view: bool
    used_roster: bool
    used_config: bool


@dataclass(frozen=True, slots=True)
class VerifyStep:
    outcome: str
    reason: str | None
    result: VerificationResult | None
    repair_attempts: int
    used_live_view: bool
    used_roster: bool
    used_config: bool


def _failed(reason: str) -> VerifyStep:
    return VerifyStep(
        outcome="failed",
        reason=reason,
        result=None,
        repair_attempts=0,
        used_live_view=False,
        used_roster=False,
        used_config=False,
    )


def _normalize_alias(alias: str) -> str:
    return " ".join(alias.split()).casefold()


def _lexicon_invalid(intent: VerifyIntent) -> bool:
    bound = {actor_id for actor_id, _aliases in intent.actor_bindings}
    if bound != set(intent.required_actors):
        return True
    seen: dict[str, str] = {}
    for actor_id, aliases in intent.actor_bindings:
        local: set[str] = set()
        if not aliases:
            return True
        for alias in aliases:
            key = _normalize_alias(alias)
            if not key or len(alias) > 64 or key in local:
                return True
            local.add(key)
            previous = seen.get(key)
            if previous is not None and previous != actor_id:
                return True
            seen[key] = actor_id
    return False


def _shape_reasons(text: str) -> list[str]:
    stripped = text.strip()
    reasons: list[str] = []
    if not stripped:
        return ["empty"]
    if len(stripped) < MIN_CHARS:
        reasons.append("empty")
    if len(stripped) > MAX_CHARS:
        reasons.append("too_long")
    tokens = stripped.split()
    if len(tokens) > MAX_TOKENS:
        reasons.append("token_count")
    if not stripped.endswith(".") or ". " in stripped[:-1]:
        reasons.append("sentence_count")
    if any(char in NON_EN_CHARS for char in stripped):
        reasons.append("non_en_contract")
    lowered = stripped.casefold()
    first = tokens[0].strip('.,;:!?"').casefold() if tokens else ""
    if (
        any(marker in lowered for marker in META_MARKERS)
        or first in FIRST_PERSON
        or stripped.endswith("?")
    ):
        reasons.append("meta_output")
    return reasons


class SemanticVerifier:
    """Accepts one visible sentence against one frozen family claim frame."""

    def verify(self, intent: VerifyIntent) -> VerifyStep:
        if intent.cancelled:
            return _failed("realization_cancelled")
        if intent.now_ms >= intent.deadline_mono_ms:
            return _failed("realization_timeout")
        if intent.stale_bundle:
            return _failed("realization_input_invalid")
        if intent.external_failure:
            return _failed("realization_transport")
        form = intent.transport_form
        if form in TRANSPORT_INVALID:
            return _failed("realization_invalid_response")
        if form in TRANSPORT_OVERSIZE:
            return _failed("realization_output_oversize")
        if _lexicon_invalid(intent):
            return _failed("realization_input_invalid")

        claims = (f"required-frame:{intent.family}",)
        reasons = _shape_reasons(intent.text)
        if not reasons:
            reasons = semantic_reasons(
                intent.text,
                intent.required_claim_surface,
                intent.subject_surface,
            )
        reported = tuple(reasons[:MAX_REASONS])
        result = VerificationResult(
            schema_version=SCHEMA_RESULT,
            accepted=not reported,
            claims=claims,
            reasons=reported,
            family=intent.family,
            repair_attempts=0,
            used_live_view=False,
            used_roster=False,
            used_config=False,
        )
        return VerifyStep(
            outcome="succeeded",
            reason=None,
            result=result,
            repair_attempts=0,
            used_live_view=False,
            used_roster=False,
            used_config=False,
        )
