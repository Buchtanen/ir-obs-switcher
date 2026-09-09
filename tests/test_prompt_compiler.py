"""#268 dynamic compiled PromptOptions and prompt profiles."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.contracts import load_narrative_catalog
from irswitch.events import __all__ as events_exports
from irswitch.events.prompt_compiler import (
    PROFILES,
    SCHEMA_VERSION,
    TIGHT_CONTRACT,
    PromptCompiler,
    PromptWorld,
    prompt_options_for,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "irswitch" / "events" / "prompt_compiler.py"
FIXTURES = ROOT / "tests" / "fixtures" / "prompt_compiler"


def _world(**overrides: object) -> PromptWorld:
    values: dict[str, object] = {
        "beat_id": "battle.approach",
        "stream_epoch": 3,
        "opportunity_id": "opp:401",
        "episode_id": "battle-ahead:3:17:22:4",
        "episode_revision": 4,
        "cycle_attempt_ordinal": 1,
    }
    values.update(overrides)
    return PromptWorld(**values)  # type: ignore[arg-type]


def test_closed_profile_tuples_are_not_freely_combinable() -> None:
    tight = PROFILES["tight"]
    balanced = PROFILES["balanced"]
    loose = PROFILES["loose"]

    assert tight == ("tight", "fixed", 0, False, 1, 0.15, 0.75)
    assert balanced[:2] == ("balanced", "family_pool")
    assert balanced[4:7] == (1, 0.35, 0.85)
    assert loose[:2] == ("loose", "family_pool")
    assert loose[4:7] == (2, 0.55, 0.90)
    assert tight[2] == 0
    assert not tight[3]
    assert "tight" not in {balanced[0], loose[0]}


def test_production_catalog_always_compiles_tight() -> None:
    catalog = load_narrative_catalog().require_catalog()
    compiler = PromptCompiler()
    for beat in catalog.beats:
        step = compiler.realize(_world(beat_id=beat.id), now_ms=10_000)
        assert step.outcome == "succeeded"
        assert step.options is not None
        assert step.options.freedom == "tight"
        assert step.options.pattern_choice == "fixed"
        assert step.options.optional_claim_limit == 0
        assert step.options.max_sentences == 1
        assert step.prompt is not None
        assert step.prompt.prompt_contract_version == TIGHT_CONTRACT


def test_least_permissive_clamp_and_runtime_safety_caps() -> None:
    promoted = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="balanced",
            policy_id="context",
            beat_role="update",
            history_complete=True,
            min_selected_fact_confidence=0.94,
        )
    )
    critical = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="critical",
            beat_role="update",
        )
    )
    outcome = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="outcome",
        )
    )
    stale = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="update",
            history_complete=False,
        )
    )
    low = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="update",
            min_selected_fact_confidence=0.89,
        )
    )

    assert promoted.freedom == "balanced"
    assert promoted.pattern_choice == "family_pool"
    assert critical.freedom == outcome.freedom == stale.freedom == low.freedom == "tight"


def test_promoted_noncritical_context_may_compile_preferred_wider_tuple() -> None:
    options = prompt_options_for(
        _world(
            beat_id="session.preview.next",
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="update",
            history_complete=True,
            min_selected_fact_confidence=0.90,
            enabled_card_count=4,
        )
    )

    assert options.freedom == "loose"
    assert options.pattern_choice == "family_pool"
    assert options.optional_claim_limit == 2
    assert options.max_sentences == 2
    assert options.temperature == 0.55
    assert options.top_p == 0.90


def test_seed_matches_frozen_golden() -> None:
    options = prompt_options_for(_world())
    assert options.seed == 16041955996680716084


def test_family_pool_requires_two_enabled_cards() -> None:
    step = PromptCompiler().realize(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="balanced",
            policy_id="context",
            beat_role="update",
            enabled_card_count=1,
        ),
        now_ms=10_000,
    )
    assert step.outcome == "failed"
    assert step.reason == "realization_input_invalid"
    assert step.prompt is None


def test_tight_prompt_has_no_unrelated_family_examples() -> None:
    step = PromptCompiler().realize(_world(), now_ms=10_400)
    assert step.outcome == "succeeded"
    assert step.prompt is not None
    assert step.prompt.schema_version == SCHEMA_VERSION
    assert step.prompt.realization_family == "battle.closing"
    assert step.prompt.realization_pattern == "battle.approach:tight:1"
    assert "FAMILY GRAMMAR" in step.prompt.system_text
    assert "PATTERN CARD" in step.prompt.system_text
    assert "OUTPUT LIMITS" in step.prompt.system_text
    assert "timing.lap_result" not in step.prompt.system_text
    assert "session.weather" not in step.prompt.system_text
    assert step.prompt.user_text.startswith("{")
    assert "FactView" not in step.prompt.system_text
    assert step.used_live_view is False
    assert step.used_roster is False
    assert step.used_config is False
    assert step.latency_ms is not None
    assert step.latency_ms["plan_to_compile"] == 400
    assert step.prompt.prompt_id.startswith("prompt:")
    assert step.prompt.prompt_hash.startswith("sha256:")


def test_freedom_does_not_widen_on_repetition_or_failure() -> None:
    options = prompt_options_for(_world(widen_for_repetition=True, widen_for_failure=True))
    assert options.freedom == "tight"
    assert options.pattern_choice == "fixed"


def test_timeout_and_cancel_fail_closed() -> None:
    compiler = PromptCompiler()
    timeout = compiler.realize(_world(), now_ms=20_000, deadline_mono_ms=15_000)
    cancelled = compiler.realize(_world(), now_ms=10_000, cancelled=True)

    assert timeout.outcome == "failed"
    assert timeout.reason == "realization_timeout"
    assert timeout.prompt is None
    assert cancelled.reason == "realization_cancelled"
    assert cancelled.options is None


def test_stale_bundle_and_overflow_reject() -> None:
    compiler = PromptCompiler()
    stale = compiler.realize(
        _world(expected_catalog_hash="sha256:" + ("0" * 64)),
        now_ms=10_000,
    )
    oversized = compiler.realize(_world(max_chars=1), now_ms=10_000)

    assert stale.reason == "realization_input_invalid"
    assert oversized.reason == "realization_input_invalid"


def test_listening_fixtures_cover_transition_identity_and_expiry() -> None:
    compiler = PromptCompiler()
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))

    ok = compiler.realize(
        _world(beat_id=transition["beatId"]),
        now_ms=transition["nowMs"],
        deadline_mono_ms=transition["deadlineMonoMs"],
    )
    assert ok.outcome == transition["expectOutcome"]
    assert ok.options is not None
    assert ok.options.freedom == transition["expectFreedom"]
    assert ok.prompt is not None
    assert ok.prompt.prompt_contract_version == transition["expectContractVersion"]

    denied = compiler.realize(
        _world(
            beat_id=identity["beatId"],
            widen_for_repetition=identity["widenForRepetition"],
            widen_for_failure=identity["widenForFailure"],
        ),
        now_ms=identity["nowMs"],
        deadline_mono_ms=identity["deadlineMonoMs"],
    )
    assert denied.reason == identity["expectReason"]
    assert denied.options is not None
    assert denied.options.freedom == identity["expectFreedom"]

    late = compiler.realize(
        _world(expires_mono_ms=expiry["expiresMonoMs"]),
        now_ms=expiry["nowMs"],
        deadline_mono_ms=expiry["deadlineMonoMs"],
    )
    assert late.reason == expiry["expectReason"]


def test_compiler_is_not_exported_from_events_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "prompt_compiler" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay"):
        assert banned not in source
    assert "FactView" not in source
