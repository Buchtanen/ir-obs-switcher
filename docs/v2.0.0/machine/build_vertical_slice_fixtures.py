#!/usr/bin/env python3
"""Build and execute the structured F01-F44 pre-implementation fixtures."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from build_dto_schemas import canonical

BASE = Path(__file__).parent
DOC_PATH = BASE.parent / "vertical-slice-fixtures.md"
REGISTRY_PATH = BASE / "freeze-registry.json"
OUTPUT_PATH = BASE / "vertical-slice-fixtures.json"
MUTATIONS_PATH = BASE / "vertical-slice-mutations.json"
HASH_INPUTS = (
    "beat-catalog.json",
    "successor-graph.json",
    "detector-catalog.json",
    "config-contract.json",
    "api-contract.json",
    "actor-transition-model.json",
    "realization-contract.json",
)
TAPE_ORDER = (
    "context_applied",
    "narrative_event",
    "fact_episode_opportunity_change",
    "director_decision",
    "llm_attempt",
    "playback_accepted",
    "speech_exposure_terminal",
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def titles() -> dict[str, str]:
    found = re.findall(
        r"^## (F\d{2}) — (.+)$",
        DOC_PATH.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    return dict(found)


def row(
    domains: str,
    inputs: str,
    expectations: str,
    channels: str = "",
    calculations: list[dict[str, Any]] | None = None,
    tape: tuple[str, ...] = TAPE_ORDER,
) -> dict[str, Any]:
    input_tokens = inputs.split()
    expectation_tokens = expectations.split()
    model_rules = []
    for expectation in expectation_tokens:
        model_rules.append({"whenAll": input_tokens, "emit": expectation})
    return {
        "domains": domains.split(),
        "inputs": input_tokens,
        "expectations": expectation_tokens,
        "modelRules": model_rules,
        "tapeChannels": channels.split(),
        "calculations": calculations or [],
        "expectedTapeOrder": list(tape),
    }


def specifications() -> dict[str, dict[str, Any]]:
    return {
        "F01": row(
            "timeline facts director speech silence",
            "stream_started no_session_ref playback_terminal",
            "stream_scope_identity_null authored_stream_start no_session_invented silence_after_terminal",
            "stream.lifecycle",
        ),
        "F02": row(
            "timeline facts lineage verifier",
            "practice_best qualifying_result race_start",
            "lineage_p0_q0_r0 current_facts_r0 historical_requires_past_marker no_absent_stage",
            "session.lifecycle session.qualifying.recap",
        ),
        "F03": row(
            "timeline lineage facts speech",
            "lineage_p0_q0_r0 rewind_to_q1 later_r1",
            "ordered_r0_end_q1_start no_session_rewound_command lineage_p0_q1 persistent_downstream cancel_old_speech lineage_p0_q1_r1",
            "session.lifecycle",
        ),
        "F04": row(
            "timeline facts opportunity",
            "same_ref_rewind_gt_5s confirm_100ms single_unconfirmed_sample",
            "one_session_restarted new_occurrence archive_by_scope invalidate_old_opportunities no_false_restart",
            "session.lifecycle",
        ),
        "F05": row(
            "director scoring episode",
            "battle_pursuit material_band",
            "score_70 threshold_pass opens_correlated_episode no_v4_priority_term",
            "race.battle.closing",
            [
                {"op": "sum", "values": [64, 6], "expected": 70},
                {"op": "gte", "left": 70, "right": 35, "expected": True},
            ],
        ),
        "F06": row(
            "director successor scoring",
            "focused_pursuit related_approach independent_weather",
            "deduplicate_event_successor score_76 select_related_event_update weather_pending_ttl",
            "race.battle.closing session.context.weather",
            [
                {"op": "sum", "values": [58, 6, 6, 6], "expected": 76},
                {"op": "gt", "left": 76, "right": 52, "expected": True},
            ],
        ),
        "F07": row(
            "director switching scoring",
            "focused_76 challenger_82 challenger_84 margin_8",
            "82_does_not_switch 84_switches_inclusive switch_margin_met breakdown_recorded",
            "race.battle.closing",
            [
                {
                    "op": "margin",
                    "incumbent": 76,
                    "margin": 8,
                    "challengers": [82, 84],
                    "expected": [False, True],
                }
            ],
        ),
        "F08": row(
            "speech opportunity episode director",
            "speaking_approach critical_pass ttl_45 terminal",
            "no_interrupt no_prepared_queue truth_updates_immediately terminal_replans_live expired_never_narrated",
            "race.battle.closing race.position.pass",
        ),
        "F09": row(
            "realization verifier planning_cycle",
            "qwen_actor_reversed context_score_46",
            "suppress_revision release_reservation no_retry_or_fallback distinct_attempt_2 cycle_exhausted_after_second",
            "race.battle.closing",
        ),
        "F10": row(
            "silence director scoring",
            "silence_elapsed out_lap_fact threshold_35",
            "score_36 filler_selected missing_fact_silence normal_rearm",
            "filler.track_state",
            [
                {"op": "sum", "values": [24, 12], "expected": 36},
                {"op": "gte", "left": 36, "right": 35, "expected": True},
            ],
        ),
        "F11": row(
            "qwen health director",
            "warmup_failed qwen_candidate authored_candidate",
            "qwen_hard_ineligible no_cold_timeout authored_may_win no_backend_fallback",
        ),
        "F12": row(
            "api manual speech",
            "commentary_disabled idle_tts_ready second_manual race_event",
            "manual_202_after_dispatch no_narrative_state second_busy race_truth_no_interrupt",
        ),
        "F13": row(
            "mailbox recovery",
            "ordinary_56 protected_7 protected_reset",
            "ordinary_eviction_first emergency_recovery latest_projection history_incomplete no_lost_opportunities producer_nonblocking",
        ),
        "F14": row(
            "speech ordering replay",
            "reset_then_accept accept_then_reset",
            "first_unconsumed_stale_accept second_consumed_exposed_interrupt reducer_sequence_authority",
        ),
        "F15": row(
            "facts episode director speech",
            "fact_only_batch closing_fact_expired",
            "apply_new_view close_episode cancel_preaccept no_opportunity no_director_pass later_cannot_continue",
        ),
        "F16": row(
            "config timeline run speech tape",
            "run3_broadcast2 disable reenable",
            "close_run3 commentary_disabled complete_trailer manual_independent allocate_run4 incomplete_history one_enabled_mid_stream no_state_leak",
            "stream.lifecycle",
        ),
        "F17": row(
            "silence facts verifier",
            "lobby no_session track_identity silence_elapsed",
            "stream_scope_filler null_occurrence exact_two_facts no_session_claim missing_track_guard_rearm",
            "filler.track_state",
        ),
        "F18": row(
            "context facts event ordering",
            "timeline31 factview88 event_view87 factview89_event89",
            "apply_88 reject_mismatch no_old_view_lookup no_batch_merge apply_89_one_director",
        ),
        "F19": row(
            "mailbox recovery replay",
            "evict_101_104 barrier_seq20 refresh_110 queued_105_109 revision111",
            "jump_110 full_loss_range no_invented_opportunities stale_105_109 apply_111 replay_equal",
        ),
        "F20": row(
            "api manual latch silence",
            "caller_abandon_first actor_claim_first timeout_1000 overrides_rejected",
            "abandon_returns_503_no_audio claim_linearized_202_or_error no_narrative_state tape_terminal_decision manual_silence_only",
        ),
        "F21": row(
            "fanout context ordering",
            "publication_130 result_at_64 result_at_129",
            "parts_64_64_2 first_two_protected last_ordinary same_revision_idempotent source_order_preserved three_impulses",
            "",
            [{"op": "partition", "total": 130, "maximum": 64, "expected": [64, 64, 2]}],
        ),
        "F22": row(
            "timeline run",
            "normal_start attach_live process_recovery enable_mid_stream unknown_resume",
            "exclusive_start_reasons completeness_flags resume_keeps_epochs no_duplicate_stream_started",
        ),
        "F23": row(
            "scoring ordering story_cap",
            "semantic_age90 pattern_age180 orders_40_3_40_4 public_cap3 story_cap2 accepted2",
            "fatigue_half_each stable_order_40_3 effective_cap2 nonclosing_ineligible closure_critical_eligible",
            "",
            [
                {"op": "half_life", "age": 90, "halfLife": 90, "expected": 0.5},
                {"op": "half_life", "age": 180, "halfLife": 180, "expected": 0.5},
                {"op": "minimum", "values": [3, 2], "expected": 2},
            ],
        ),
        "F24": row(
            "validity planning_cycle mailbox",
            "expires_50000 reduce_50000 mailbox_full reduce_50001",
            "half_open_invalid cancel_generation expired_ttl late_worker_stale no_director no_attempt2 skipped_admission_sweep_equal",
            "",
            [{"op": "half_open", "start": 40000, "end": 50000, "at": 50000, "expected": False}],
        ),
        "F25": row(
            "timeline schema ordering",
            "broadcast_and_race_start q0_to_r0 invalid_reason_lists",
            "ordered_broadcast_then_session ordered_end_then_start lineage_q0 exact_once invalid_lists_rejected",
        ),
        "F26": row(
            "speech watchdog health",
            "stall_preaccept stall_postaccept stall_postcancel stale_callbacks higher_generation_ready",
            "start_timeout_unconsumed playback_timeout_consumed stop_timeout_quarantine admission_blocked late_noop higher_generation_restores",
        ),
        "F27": row(
            "tape overflow capture",
            "sample_normal_full all_critical normal_arrival critical_terminal required_window",
            "evict_sample_then_normal fifo_equal bounded_loss_accumulator drop_notice trailer_counts capture_unavailable_one_detector main_loop_continues",
        ),
        "F28": row(
            "features detector ordering",
            "frames_10_12_12_11 lone_sample covered_buckets",
            "reduce_10_12 older_noop coverage_capped invalid_lone_sample ols_three_buckets identity_match",
        ),
        "F29": row(
            "api verifier actors",
            "complete_binding missing_target unused_actor alias_collision reversed_aliases",
            "only_complete_parses invalid_400_no_live_reads reversal_actor_reversed",
        ),
        "F30": row(
            "tts config speech",
            "auto_sapi_espeak sapi_failure explicit_supertonic later_rebuild",
            "snapshot_sapi no_same_text_fallback later_generation_only supertonic_explicit",
        ),
        "F31": row(
            "session_plan timeline",
            "seven_supported_subsets invalid_inputs partial_snapshot unsupported18 frozen_pq_changes",
            "seven_valid_ordered no_invented_stage conflict_empty_plan partial_suspends stable_revision append_future_only unsupported16_overflow2",
            "",
            [{"op": "count", "values": ["P", "Q", "R", "PQ", "PR", "QR", "PQR"], "expected": 7}],
        ),
        "F32": row(
            "facts episodes capacity",
            "facts512 semantic_update new_unpinned pinned_only episodes_capacity pinned_episodes",
            "update_no_growth deterministic_fact_evict unknown_not_false pinned_exhaustion_no_partial recover_degraded episode_eviction_order pinned_reject",
        ),
        "F33": row(
            "prompt freedom seed fatigue",
            "profile_product loose_requests confidence_0_89 promoted_context repetition failure",
            "closed_profiles least_permissive tight_baseline promoted_wider_if_safe canonical_seed card_choice_or_fatigue failure_no_widen",
            "",
            [
                {
                    "op": "seed",
                    "material": {
                        "beatId": "battle.approach",
                        "cycleAttemptOrdinal": 1,
                        "episodeId": "battle-ahead:3:17:22:4",
                        "episodeRevision": 4,
                        "opportunityId": "opp:401",
                        "streamEpoch": 3,
                    },
                    "expected": 16041955996680716084,
                }
            ],
        ),
        "F34": row(
            "detector tape replay capture",
            "frames_200_214 params7 rotation lose209 optional_repeat",
            "manifest_snapshot_repeated typed_frames exact_hash range_across_rotation required_loss_disables optional_loss_degrades no_interpolation",
        ),
        "F35": row(
            "director planning_cycle replacement",
            "cycle70_building critical_pass lower_event verifier_fail",
            "replace_without_suppression close70 new_cycle71_attempt1 one_alternative lower_event_no_replace accepted_event_only",
        ),
        "F36": row(
            "config ledger tape actor",
            "generation6_build generation7_mixed preflight_pending boundaries rotation barrier_full generation8_revert invalid_reload",
            "old_plan_keeps_gen6 exact_boundary_groups no_old_backend manifest_snapshot barrier_loss_explicit pending_recomputed invalid_no_generation atomic_disable",
        ),
        "F37": row(
            "director switching replacement",
            "focused76 story84 context90 critical36 filler100 building70_challenger78",
            "margin_switch lower_urgency_can_switch critical_priority filler_fallback_only replacement_inclusive_78 no_non_event_replace full_breakdown",
        ),
        "F38": row(
            "realization facts freshness tape",
            "factview90_r_g14 unrelated_change equal_copies g2_11 g_evicted alias_change missing_surface",
            "bundle_frozen equal_facts_pass alias_immutable changed_missing_stale malformed_input_rejected hashes_recorded",
        ),
        "F39": row(
            "tts callback speech duck",
            "normal preaccept_fail completion_before_accept duplicate_accept reset_orders stop_timeout duck_fail later_manual",
            "immutable_utterance callback_sequence consume_once protocol_quarantine reset_consumption_rules one_restore late_noop manual_new_token",
        ),
        "F40": row(
            "qwen prompt sse deadline mailbox tape",
            "golden_request split_sse invalid_sse deadline_orders replacement duplicate_results warmup_states mailbox_full",
            "exact_prompt_projection one_terminal_result fail_closed_sse deadline_authority protected_deadline no_request_queue duplicate_protocol warmup_no_retry exact_metrics",
        ),
        "F41": row(
            "tts adapters acknowledgement",
            "sapi_default sapi_waveout espeak supertonic preboundary_fail cancellation duplicate zero_exit watchdog_orders",
            "exact_software_boundaries no_early_consumption ordered_callbacks protocol_quarantine watchdog_authority no_backend_retry",
        ),
        "F42": row(
            "silence timeline config speech",
            "opening33 accepted20 busy33 no_filler obs_unknown_resume disable_manual reenable simultaneous config45",
            "run_origin acceptance_cancels busy_rearms inactive_no_credit generation_stale new_value_next_arm",
        ),
        "F43": row(
            "tape funnel event director replay",
            "accepted_started cooldown_reject visual_accept revised_expire alternative successor filler duplicate changed_payload tape_disabled gap",
            "candidate_protocol_identity exact_links once_only_counts terminal_stages live_counters_without_tape incomplete_replay valid_denominators",
        ),
        "F44": row(
            "capture detector mailbox tape",
            "all_profile_policy_rows required_losses saturated_queues duplicate_notices repair later_stream",
            "production_required_rejected optional_failsoft required_latch_disable_named atomic_health_context idempotent_notice no_same_run_reenable next_stream_restores",
        ),
    }


def build_fixtures() -> dict[str, Any]:
    human_titles = titles()
    specs = specifications()
    hashes = {name: digest(load(BASE / name)) for name in HASH_INPUTS}
    fixtures = []
    for fixture_id in sorted(specs):
        value = specs[fixture_id]
        fixtures.append(
            {
                "schemaVersion": "vertical-slice-fixture/2",
                "id": fixture_id,
                "title": human_titles[fixture_id],
                "source": f"docs/v2.0.0/vertical-slice-fixtures.md#{fixture_id.lower()}",
                "contractHashes": hashes,
                **value,
            }
        )
    return {
        "schemaVersion": "vertical-slice-fixtures/2",
        "sourceBaseline": "master@0ce75d4",
        "defaultEnvironment": {
            "selectionThreshold": 35,
            "switchMargin": 8,
            "globalIntervalSatisfied": True,
            "fatiguePressure": False,
            "qwenResidency": "warmup_succeeded",
            "ttsAvailable": True,
        },
        "fixtures": fixtures,
    }


def build_mutations() -> list[dict[str, str]]:
    return [
        {"id": "missing_f44", "errorContains": "fixture ID coverage differs"},
        {"id": "duplicate_f01", "errorContains": "fixture ID coverage differs"},
        {"id": "unknown_channel", "errorContains": "unknown tape channel"},
        {"id": "stale_contract_hash", "errorContains": "contract hashes differ"},
        {"id": "missing_expectation", "errorContains": "fixture fields are empty"},
        {"id": "tape_order_reversed", "errorContains": "tape order differs"},
        {"id": "f05_score_69", "errorContains": "calculation differs"},
        {"id": "f07_exclusive_margin", "errorContains": "calculation differs"},
        {"id": "f21_partition_loss", "errorContains": "calculation differs"},
        {"id": "f23_wrong_decay", "errorContains": "calculation differs"},
        {"id": "f24_closed_interval", "errorContains": "calculation differs"},
        {"id": "f31_six_subsets", "errorContains": "calculation differs"},
        {"id": "f33_wrong_seed", "errorContains": "calculation differs"},
        {"id": "f40_missing_qwen_domain", "errorContains": "required fixture coverage differs"},
        {
            "id": "f44_missing_capture_assertion",
            "errorContains": "model expectation differs",
        },
        {
            "id": "f36_model_rule_removed",
            "errorContains": "model expectation differs",
        },
    ]


def evaluate(calculation: dict[str, Any]) -> Any:
    operation = calculation["op"]
    if operation == "sum":
        return sum(calculation["values"])
    if operation == "gte":
        return calculation["left"] >= calculation["right"]
    if operation == "gt":
        return calculation["left"] > calculation["right"]
    if operation == "margin":
        boundary = calculation["incumbent"] + calculation["margin"]
        return [value >= boundary for value in calculation["challengers"]]
    if operation == "partition":
        total, maximum = calculation["total"], calculation["maximum"]
        parts = []
        while total:
            part = min(total, maximum)
            parts.append(part)
            total -= part
        return parts
    if operation == "half_life":
        return 0.5 ** (calculation["age"] / calculation["halfLife"])
    if operation == "minimum":
        return min(calculation["values"])
    if operation == "half_open":
        return calculation["start"] <= calculation["at"] < calculation["end"]
    if operation == "count":
        return len(calculation["values"])
    if operation == "seed":
        raw = hashlib.sha256(canonical(calculation["material"]).encode()).digest()
        return int.from_bytes(raw[:8], "big")
    raise ValueError(f"unknown calculation operation {operation}")


def execute_model(fixture: dict[str, Any]) -> list[str]:
    """Run the monotonic pre-implementation rule program for one scenario."""
    known = set(fixture["inputs"])
    emitted: list[str] = []
    pending = list(fixture["modelRules"])
    while pending:
        progressed = False
        for rule in list(pending):
            if set(rule["whenAll"]) <= known:
                if rule["emit"] in known:
                    raise ValueError("model emitted duplicate token")
                known.add(rule["emit"])
                emitted.append(rule["emit"])
                pending.remove(rule)
                progressed = True
        if not progressed:
            raise ValueError("model rule dependency is unreachable")
    return emitted


def fixture_errors(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fixtures = bundle["fixtures"]
    ids = [row["id"] for row in fixtures]
    expected_ids = [f"F{ordinal:02d}" for ordinal in range(1, 45)]
    if ids != expected_ids:
        errors.append("fixture ID coverage differs")
        return errors
    known_channels = set(load(REGISTRY_PATH)["tapeChannels"])
    expected_hashes = {name: digest(load(BASE / name)) for name in HASH_INPUTS}
    human_titles = titles()
    for fixture in fixtures:
        if not fixture["inputs"] or not fixture["expectations"] or not fixture["domains"]:
            errors.append("fixture fields are empty")
            return errors
        if not set(fixture["tapeChannels"]) <= known_channels:
            errors.append("unknown tape channel")
            return errors
        if fixture["contractHashes"] != expected_hashes:
            errors.append("contract hashes differ")
            return errors
        if fixture["title"] != human_titles[fixture["id"]]:
            errors.append("human source title differs")
            return errors
        try:
            modeled = execute_model(fixture)
        except ValueError as exc:
            errors.append(str(exc))
            return errors
        if modeled != fixture["expectations"]:
            errors.append("model expectation differs")
            return errors
        if any(set(rule["whenAll"]) != set(fixture["inputs"]) for rule in fixture["modelRules"]):
            errors.append("model precondition differs")
            return errors
        positions = [TAPE_ORDER.index(value) for value in fixture["expectedTapeOrder"]]
        if positions != sorted(set(positions)):
            errors.append("tape order differs")
            return errors
        for calculation in fixture["calculations"]:
            actual = evaluate(calculation)
            expected = calculation["expected"]
            if isinstance(actual, float):
                valid = math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12)
            else:
                valid = actual == expected
            if not valid:
                errors.append("calculation differs")
                return errors
    by_id = {row["id"]: row for row in fixtures}
    required = {
        "F13": ("mailbox", "emergency_recovery"),
        "F21": ("fanout", "parts_64_64_2"),
        "F28": ("detector", "coverage_capped"),
        "F31": ("session_plan", "seven_valid_ordered"),
        "F33": ("prompt", "canonical_seed"),
        "F36": ("config", "exact_boundary_groups"),
        "F40": ("qwen", "exact_prompt_projection"),
        "F44": ("capture", "required_latch_disable_named"),
    }
    for fixture_id, (domain, expectation) in required.items():
        if (
            domain not in by_id[fixture_id]["domains"]
            or expectation not in by_id[fixture_id]["expectations"]
        ):
            errors.append("required fixture coverage differs")
            return errors
    return errors


def mutate(bundle: dict[str, Any], mutation_id: str) -> dict[str, Any]:
    result = copy.deepcopy(bundle)
    fixtures = result["fixtures"]
    by_id = {row["id"]: row for row in fixtures}
    if mutation_id == "missing_f44":
        fixtures.pop()
    elif mutation_id == "duplicate_f01":
        fixtures[1] = copy.deepcopy(fixtures[0])
    elif mutation_id == "unknown_channel":
        fixtures[0]["tapeChannels"] = ["race.magic"]
    elif mutation_id == "stale_contract_hash":
        fixtures[0]["contractHashes"]["beat-catalog.json"] = "sha256:" + "0" * 64
    elif mutation_id == "missing_expectation":
        fixtures[0]["expectations"] = []
    elif mutation_id == "tape_order_reversed":
        fixtures[0]["expectedTapeOrder"] = list(reversed(TAPE_ORDER))
    elif mutation_id == "f05_score_69":
        by_id["F05"]["calculations"][0]["expected"] = 69
    elif mutation_id == "f07_exclusive_margin":
        by_id["F07"]["calculations"][0]["expected"] = [False, False]
    elif mutation_id == "f21_partition_loss":
        by_id["F21"]["calculations"][0]["expected"] = [64, 64, 1]
    elif mutation_id == "f23_wrong_decay":
        by_id["F23"]["calculations"][0]["expected"] = math.exp(-1)
    elif mutation_id == "f24_closed_interval":
        by_id["F24"]["calculations"][0]["expected"] = True
    elif mutation_id == "f31_six_subsets":
        by_id["F31"]["calculations"][0]["expected"] = 6
    elif mutation_id == "f33_wrong_seed":
        by_id["F33"]["calculations"][0]["expected"] = 0
    elif mutation_id == "f40_missing_qwen_domain":
        by_id["F40"]["domains"].remove("qwen")
    elif mutation_id == "f44_missing_capture_assertion":
        by_id["F44"]["expectations"].remove("required_latch_disable_named")
    elif mutation_id == "f36_model_rule_removed":
        by_id["F36"]["modelRules"].pop()
    else:
        raise ValueError(mutation_id)
    return result


def validate_all(bundle: dict[str, Any], mutations: list[dict[str, str]]) -> None:
    if canonical(bundle) != canonical(build_fixtures()) or canonical(mutations) != canonical(
        build_mutations()
    ):
        raise ValueError("vertical-slice artifacts are stale")
    errors = fixture_errors(bundle)
    if errors:
        raise ValueError("valid fixture bundle rejected: " + errors[0])
    for mutation in mutations:
        errors = fixture_errors(mutate(bundle, mutation["id"]))
        if not errors or mutation["errorContains"] not in errors[0]:
            raise ValueError(f"mutation {mutation['id']} failed for wrong reason: {errors[:1]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    bundle, mutations = build_fixtures(), build_mutations()
    if args.write:
        for path, value in ((OUTPUT_PATH, bundle), (MUTATIONS_PATH, mutations)):
            path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print("wrote structured F01-F44 fixtures and mutations")
        return 0
    validate_all(load(OUTPUT_PATH), load(MUTATIONS_PATH))
    calculations = sum(len(row["calculations"]) for row in bundle["fixtures"])
    model_rules = sum(len(row["modelRules"]) for row in bundle["fixtures"])
    print(
        "Vertical slice fixtures OK: 44 scenarios, "
        f"{model_rules} executable expectation rules + {calculations} calculations, "
        f"{len(HASH_INPUTS)} contract hashes each, "
        f"{len(mutations)} rejected mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
