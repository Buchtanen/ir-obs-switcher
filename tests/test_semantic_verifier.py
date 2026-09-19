"""#270 family-specific SemanticVerifier."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.contracts import __all__ as contracts_exports
from irswitch.events import __all__ as events_exports
from irswitch.events.semantic_verifier import (
    REJECTION_CODES,
    SCHEMA_CORPUS,
    SCHEMA_RESULT,
    SemanticVerifier,
    VerifyIntent,
    load_verifier_contract,
    load_verifier_corpus,
    surface_form_allowed,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "irswitch" / "events" / "semantic_verifier.py"
FIXTURES = ROOT / "tests" / "fixtures" / "semantic_verifier"


def _intent(**overrides: object) -> VerifyIntent:
    values: dict[str, object] = {
        "text": "Alex is closing on Morgan.",
        "family": "battle.closing",
        "subject_surface": "Alex",
        "required_claim_surface": "is closing on Morgan",
        "actor_bindings": (
            ("hero", ("Alex", "the driver")),
            ("car:22", ("Morgan", "the car ahead")),
        ),
        "required_actors": frozenset({"hero", "car:22"}),
        "now_ms": 10_000,
        "deadline_mono_ms": 20_000,
    }
    values.update(overrides)
    return VerifyIntent(**values)  # type: ignore[arg-type]


def test_frozen_contract_has_37_grammars_and_closed_rejection_codes() -> None:
    contract = load_verifier_contract()
    corpus = load_verifier_corpus()

    assert contract["schemaVersion"] == "realization-contract/2"
    assert len(contract["grammars"]) == 37
    assert contract["enabledFreedom"] == ["tight"]
    assert contract["authority"]["repairAttempts"] == 0
    assert contract["authority"]["sameBeatFallback"] is False
    assert contract["authority"]["hardFactGate"] == "deterministic_family_parser"
    assert contract["authority"]["embeddingUse"] == "repeat_penalty_only"
    assert contract["authority"]["secondLlmUse"] == "forbidden_as_fact_gate"
    assert set(contract["rejectionCodes"]) == REJECTION_CODES
    assert corpus["schemaVersion"] == SCHEMA_CORPUS
    assert len(corpus["cases"]) == 222
    assert corpus["maximumReportedReasons"] == 16


def test_corpus_all_37_families_match_acceptance_function() -> None:
    corpus = load_verifier_corpus()
    verifier = SemanticVerifier()
    families: set[str] = set()

    for case in corpus["cases"]:
        families.add(str(case["family"]))
        step = verifier.verify(
            _intent(
                text=case["text"],
                family=case["family"],
                subject_surface=case["surfaceBindings"]["subjectSurface"],
                required_claim_surface=case["surfaceBindings"]["requiredClaimSurface"],
                actor_bindings=(("hero", (case["surfaceBindings"]["subjectSurface"],)),),
                required_actors=frozenset({"hero"}),
            )
        )
        assert step.outcome == "succeeded"
        assert step.result is not None
        assert step.result.schema_version == SCHEMA_RESULT
        assert step.result.accepted is case["expectedAccepted"]
        assert list(step.result.reasons) == case["expectedReasons"]
        assert list(step.result.claims) == case["expectedClaims"]
        assert step.result.repair_attempts == 0
        assert step.result.used_live_view is False
        assert step.result.used_roster is False
        assert step.result.used_config is False

    assert len(families) == 37


def test_ab_ba_counterfactuals_cannot_both_pass() -> None:
    verifier = SemanticVerifier()
    forward = verifier.verify(_intent())
    reverse = verifier.verify(_intent(text="Morgan is closing on Alex."))

    assert forward.result is not None and forward.result.accepted is True
    assert reverse.result is not None and reverse.result.accepted is False
    assert "actor_reversed" in reverse.result.reasons
    assert not (forward.result.accepted and reverse.result.accepted)


def test_ambiguity_discards_without_repair() -> None:
    verifier = SemanticVerifier()
    colliding = verifier.verify(
        _intent(
            actor_bindings=(
                ("hero", ("Alex", "he")),
                ("car:22", ("Morgan", "HE")),
            )
        )
    )

    assert colliding.outcome == "failed"
    assert colliding.reason == "realization_input_invalid"
    assert colliding.result is None
    assert colliding.repair_attempts == 0


def test_actor_lexicon_rejects_missing_unused_and_casefold_collision_before_parse() -> None:
    verifier = SemanticVerifier()
    missing = verifier.verify(
        _intent(
            actor_bindings=(("hero", ("Alex", "the driver")),),
            required_actors=frozenset({"hero", "car:22"}),
        )
    )
    unused = verifier.verify(
        _intent(
            actor_bindings=(
                ("hero", ("Alex",)),
                ("car:22", ("Morgan",)),
                ("car:9", ("Taylor",)),
            )
        )
    )
    complete = verifier.verify(_intent())

    assert missing.reason == "realization_input_invalid"
    assert unused.reason == "realization_input_invalid"
    assert missing.result is None
    assert unused.result is None
    assert complete.result is not None and complete.result.accepted is True


def test_transport_forms_fail_before_semantic_parse() -> None:
    verifier = SemanticVerifier()
    thinking = verifier.verify(_intent(transport_form="thinking"))
    oversized = verifier.verify(_intent(transport_form="oversized"))

    assert thinking.reason == "realization_invalid_response"
    assert thinking.result is None
    assert oversized.reason == "realization_output_oversize"
    assert oversized.result is None


def test_shape_en_rejects_empty_long_meta_and_non_en() -> None:
    verifier = SemanticVerifier()
    empty = verifier.verify(_intent(text=""))
    meta = verifier.verify(_intent(text="<think>Alex is closing on Morgan.</think>"))
    non_en = verifier.verify(_intent(text="Alex se přibližuje k Morganovi."))

    assert empty.result is not None and "empty" in empty.result.reasons
    assert empty.result.accepted is False
    assert meta.result is not None and "meta_output" in meta.result.reasons
    assert non_en.result is not None and "non_en_contract" in non_en.result.reasons


def test_surface_value_cases_bound_forms_only() -> None:
    contract = load_verifier_contract()
    for case in contract["surfaceValueCases"]:
        for form in case["allowed"]:
            assert surface_form_allowed(str(case["kind"]), form) is True
        for form in case["rejected"]:
            assert surface_form_allowed(str(case["kind"]), form) is False


def test_timeout_cancel_stale_and_external_fail_closed() -> None:
    verifier = SemanticVerifier()
    timeout = verifier.verify(_intent(now_ms=20_000, deadline_mono_ms=15_000))
    cancelled = verifier.verify(_intent(cancelled=True))
    stale = verifier.verify(_intent(stale_bundle=True))
    external = verifier.verify(_intent(external_failure=True))

    assert timeout.reason == "realization_timeout"
    assert cancelled.reason == "realization_cancelled"
    assert stale.reason == "realization_input_invalid"
    assert external.reason == "realization_transport"
    assert timeout.result is None
    assert cancelled.result is None
    assert stale.result is None
    assert external.result is None
    assert timeout.repair_attempts == 0


def test_unknown_semantic_fragment_rejects() -> None:
    verifier = SemanticVerifier()
    step = verifier.verify(_intent(text="Alex is closing on Morgan beneath a purple moon."))

    assert step.result is not None
    assert step.result.accepted is False
    assert list(step.result.reasons) == ["unknown_fragment"]
    assert step.result.repair_attempts == 0


def test_listening_fixtures_cover_transition_identity_and_expiry() -> None:
    verifier = SemanticVerifier()
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))

    ok = verifier.verify(
        _intent(
            text=transition["text"],
            family=transition["family"],
            subject_surface=transition["subjectSurface"],
            required_claim_surface=transition["requiredClaimSurface"],
        )
    )
    assert ok.result is not None
    assert ok.result.accepted is transition["expectAccepted"]
    assert list(ok.result.reasons) == transition["expectReasons"]
    assert list(ok.result.claims) == transition["expectClaims"]

    reversed_step = verifier.verify(
        _intent(
            text=identity["text"],
            family=identity["family"],
            subject_surface=identity["subjectSurface"],
            required_claim_surface=identity["requiredClaimSurface"],
        )
    )
    assert reversed_step.result is not None
    assert reversed_step.result.accepted is identity["expectAccepted"]
    assert list(reversed_step.result.reasons) == identity["expectReasons"]

    late = verifier.verify(
        _intent(
            text=expiry["text"],
            now_ms=expiry["nowMs"],
            deadline_mono_ms=expiry["deadlineMonoMs"],
        )
    )
    assert late.outcome == expiry["expectOutcome"]
    assert late.reason == expiry["expectReason"]


def test_verifier_is_not_exported_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "semantic_verifier" not in events_exports
    assert "SemanticVerifier" not in contracts_exports
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay"):
        assert banned not in source
    assert "FactView" not in source
    assert "NarrativeRuntime" not in source
