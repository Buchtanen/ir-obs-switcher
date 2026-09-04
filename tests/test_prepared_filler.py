from __future__ import annotations

import asyncio
import json

import pytest

from irswitch.commentary.prepared_filler import (
    FactProposition,
    PreparedFillerBuffer,
    PreparedFillerCoordinator,
    PreparedFillerHealth,
    PreparedFillerPlan,
    _generation_request,
    build_prepared_filler_plans,
    result_band,
    validate_generated_variants,
)
from irswitch.overlay.settings import CommentarySettings, PreparedFillerSettings


def _plan(*, value: str = "Spa", stage: str = "STREAM_LOBBY_INTRO") -> PreparedFillerPlan:
    return PreparedFillerPlan.create(
        node_id="prepared.stream.venue",
        semantic_key="stream.venue",
        locale="en",
        scope_key="stream:1",
        stage_epoch=1,
        allowed_stages=(stage,),
        required=(FactProposition("track", value, "telemetry", "context:1", value),),
    )


def _variants(value: str = "Spa", count: int = 5) -> list[str]:
    return [f"We are live at {value}. This is prepared variant {name}." for name in "ABCDE"[:count]]


def test_plan_identity_changes_only_with_material_facts() -> None:
    first = _plan()
    same = _plan()
    changed = _plan(value="Monza")

    assert first.plan_id == same.plan_id
    assert first.situation_id == changed.situation_id
    assert first.plan_id != changed.plan_id


def test_buffer_requires_three_variants_and_rotates_exposure() -> None:
    settings = PreparedFillerSettings(variants_min=3, variants_max=5)
    buffer = PreparedFillerBuffer(settings)
    plan = _plan()
    buffer.reconcile([plan])

    buffer.merge(plan, _variants(count=2))
    assert buffer.select("STREAM_LOBBY_INTRO", 1) is None
    buffer.merge(plan, _variants(count=5))

    selected = buffer.select("STREAM_LOBBY_INTRO", 2)
    assert selected is not None
    assert buffer.mark_spoken(selected.variant.variant_id, 2)
    next_selected = buffer.select("STREAM_LOBBY_INTRO", 3)
    assert next_selected is not None
    assert next_selected.variant.variant_id != selected.variant.variant_id


def test_material_revision_invalidates_old_variants() -> None:
    buffer = PreparedFillerBuffer(PreparedFillerSettings())
    old = _plan()
    buffer.reconcile([old])
    buffer.merge(old, _variants())
    assert buffer.select("STREAM_LOBBY_INTRO", 1) is not None

    new = _plan(value="Monza")
    buffer.reconcile([new])

    assert buffer.select("STREAM_LOBBY_INTRO", 2) is None
    assert buffer.merge(old, _variants()) == 0


def test_validator_rejects_short_and_ungrounded_variants() -> None:
    plan = _plan()
    valid, errors = validate_generated_variants(
        plan,
        [
            "We are live at Spa.",
            "We are live at Spa. There are 12 cars here.",
            "We are live at Spa. The broadcast is ready.",
        ],
        PreparedFillerSettings(),
    )

    assert valid == ["We are live at Spa. The broadcast is ready."]
    assert errors == ["sentence_count", "grounding"]


def test_validator_rejects_forbidden_claim_and_reversed_result_relation() -> None:
    causal = PreparedFillerPlan.create(
        node_id="stream_intro_venue",
        semantic_key="stream_intro_venue",
        locale="en",
        scope_key="stream:1",
        stage_epoch=1,
        allowed_stages=("STREAM_LOBBY_INTRO",),
        required=(FactProposition("track", "Spa", "telemetry", "context:1", "Spa"),),
        forbidden_claims=("cause",),
    )
    valid, errors = validate_generated_variants(
        causal,
        ["We are at Spa. The surface is quick because the sun is out."],
        PreparedFillerSettings(),
    )
    assert valid == []
    assert errors == ["forbidden_claim:cause"]

    gain = next(
        plan
        for plan in build_prepared_filler_plans(
            _conclusion_context(
                "RACE",
                position=4,
                story={
                    "quali_bag": {
                        "class_position": 6,
                        "class_id": 7,
                        "subsession_id": "42",
                    }
                },
            ),
            "en",
        )
        if plan.node_id == "race_result_gain_vs_quali"
    )
    required = ". ".join(fact.spoken_value for fact in gain.required)
    valid, errors = validate_generated_variants(
        gain,
        [f"{required}. The finish was worse than qualifying."],
        PreparedFillerSettings(),
    )
    assert valid == []
    assert errors == ["relation_contradiction"]


def test_context_plan_is_stable_until_a_material_fact_changes() -> None:
    context = {
        "version": 1,
        "session_id": "42:0",
        "identity": {"overlay_mode": "RACE"},
        "editorial": {
            "stage": "STREAM_LOBBY_INTRO",
            "stage_epoch": 2,
            "stream_epoch": 1,
            "track_name": "Spa",
        },
        "race": {"class_field_size": 18},
        "story": {"weather": {"skies": "overcast"}},
        "prepared": {"air_temperature": 18.0},
    }
    first = build_prepared_filler_plans(context, "en")[0]
    same = build_prepared_filler_plans({**context, "version": 99}, "en")[0]
    changed = build_prepared_filler_plans(
        {**context, "editorial": {**context["editorial"], "track_name": "Monza"}},
        "en",
    )[0]

    assert first.plan_id == same.plan_id
    assert first.plan_id != changed.plan_id
    assert [fact.spoken_value for fact in first.required] == ["Spa"]
    plans = build_prepared_filler_plans(context, "en")
    assert {plan.node_id for plan in plans} == {
        "stream_intro_venue",
        "stream_intro_conditions",
        "stream_intro_field_class",
    }
    assert all(plan.contract_revision for plan in plans)
    assert all(plan.node_id == plan.semantic_key for plan in plans)


def test_generation_request_carries_the_graph_contract() -> None:
    plan = PreparedFillerPlan.create(
        node_id="race_result_gain_vs_quali",
        semantic_key="race_result_gain_vs_quali",
        locale="cs",
        scope_key="stream:2:session:42:run:4:stage:9",
        stage_epoch=9,
        allowed_stages=("SESSION_CONCLUSION",),
        required=(
            FactProposition("finish_position", 4, "telemetry", "context:1", "čtvrté místo"),
            FactProposition("result_relation", "gain", "derived", "context:1", "polepšení"),
        ),
        contract_revision="contract-123",
        relation="finish_better_than_qualifying",
        intent="Oznam potvrzené zlepšení proti kvalifikaci.",
        forbidden_claims=("cause", "blame"),
        anchors=("Výsledek je lepší než kvalifikace.",),
    )

    payload = _generation_request(CommentarySettings(), plan, 3, ("old-hash",))
    messages = payload["messages"]
    assert isinstance(messages, list)
    user_message = messages[1]
    assert isinstance(user_message, dict)
    request = json.loads(str(user_message["content"]))

    assert request["nodeId"] == plan.node_id
    assert request["contractRevision"] == "contract-123"
    assert request["relation"] == "finish_better_than_qualifying"
    assert request["intent"] == plan.intent
    assert request["forbiddenClaims"] == ["cause", "blame"]
    assert request["anchors"] == ["Výsledek je lepší než kvalifikace."]


def _stage_context(
    stage: str,
    mode: str,
    prepared: dict[str, object],
) -> dict[str, object]:
    return {
        "captured_monotonic_ms": 10_000,
        "session_id": "42:0",
        "identity": {
            "overlay_mode": mode,
            "run_epoch": 1,
            "subsession_id": "42",
        },
        "editorial": {
            "stage": stage,
            "stage_epoch": 3,
            "stream_epoch": 1,
            "stint_epoch": 2,
            "track_name": "Spa",
        },
        "race": {"player_car_class": 7},
        "story": {},
        "prepared": prepared,
    }


def test_prepared_context_activates_every_non_result_stage_branch() -> None:
    lobby = build_prepared_filler_plans(
        _stage_context(
            "STREAM_LOBBY_INTRO",
            "PRACTICE",
            {
                "circuit_length": 7.004,
                "turn_count": 19,
                "sky": "overcast",
                "air_temperature": 18.0,
                "surface_wetness": "dry",
                "field_size": 20,
                "class_field_size": 12,
                "ai_count": 4,
                "ai_ratio": 0.2,
                "circulating_cars": 2,
            },
        ),
        "en",
    )
    in_car = build_prepared_filler_plans(
        _stage_context(
            "IN_CAR_PREP",
            "PRACTICE",
            {
                "engine_state": "started",
                "rollout_state": "moving",
                "returned_to_car": True,
                "circulating_cars": 2,
            },
        ),
        "en",
    )
    out_lap = build_prepared_filler_plans(
        _stage_context("OUT_LAP", "QUALIFYING", {"traffic_band": "nearby"}),
        "en",
    )
    grid = build_prepared_filler_plans(
        _stage_context(
            "GRID_PREP",
            "RACE",
            {
                "qualifying_position": 6,
                "start_position": 8,
                "class_field_size": 12,
                "highest_rated_driver": "Fast Rival",
                "start_mode": "rolling",
            },
        ),
        "en",
    )
    formation = build_prepared_filler_plans(
        _stage_context(
            "FORMATION_OR_LIGHTS",
            "RACE",
            {
                "start_mode": "rolling",
                "start_position": 8,
                "distance_to_start": "near",
                "hr_band": "high",
            },
        ),
        "en",
    )
    standing = build_prepared_filler_plans(
        _stage_context(
            "FORMATION_OR_LIGHTS",
            "RACE",
            {"start_mode": "standing", "start_position": 3},
        ),
        "en",
    )
    lights = build_prepared_filler_plans(
        _stage_context(
            "FORMATION_OR_LIGHTS",
            "RACE",
            {"start_mode": "standing", "start_ready": True, "start_set": True},
        ),
        "en",
    )

    assert {plan.node_id for plan in lobby} == {
        "stream_intro_venue",
        "stream_intro_circuit_character",
        "stream_intro_conditions",
        "stream_intro_surface_state",
        "stream_intro_field_overall",
        "stream_intro_field_class",
        "stream_intro_ai_field",
        "practice_quiet_track",
    }
    assert {plan.node_id for plan in in_car} == {
        "hero_prepares_to_drive",
        "engine_started",
        "rollout_started",
        "returned_to_car",
        "practice_quiet_track",
    }
    assert {plan.node_id for plan in out_lap} == {
        "out_lap_preparation",
        "out_lap_field_context",
    }
    assert {plan.node_id for plan in grid} == {
        "race_quali_recap_result",
        "race_grid_field",
        "race_grid_highest_rated",
        "rolling_start_setup",
    }
    assert {plan.node_id for plan in formation} == {
        "rolling_start_setup",
        "formation_lap_preparation",
        "formation_lap_tension",
    }
    assert {plan.node_id for plan in standing} == {
        "standing_start_setup",
    }
    assert [plan.node_id for plan in lights] == ["start_lights_set"]


def test_start_light_plan_enforces_short_graph_tts_limit() -> None:
    plans = build_prepared_filler_plans(
        _stage_context(
            "FORMATION_OR_LIGHTS",
            "RACE",
            {"start_mode": "standing", "start_set": True},
        ),
        "en",
    )
    plan = next(item for item in plans if item.node_id == "start_lights_set")

    valid, errors = validate_generated_variants(
        plan,
        [
            "The start lights are set. The field now waits together in complete silence."
        ],
        PreparedFillerSettings(max_utterance_s=13.0),
    )

    assert plan.tts_max_seconds == 4.0
    assert valid == []
    assert errors == ["duration"]


def test_coordinator_stops_top_up_after_attempt_budget() -> None:
    calls = 0

    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        nonlocal calls
        calls += 1
        return _variants(count=3) if calls == 1 else []

    async def exercise() -> None:
        coordinator = PreparedFillerCoordinator(
            PreparedFillerSettings(mode="shadow", generation_max_attempts=2), generator
        )
        coordinator.reconcile([_plan()])
        await asyncio.wait_for(coordinator.wait_idle(), timeout=1)
        assert calls == 2
        assert coordinator.health == PreparedFillerHealth.READY
        assert coordinator.status()["inflight"] == 0
        await coordinator.close()

    asyncio.run(exercise())


def test_fatal_notice_is_once_per_episode_after_spoken_ack() -> None:
    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        return []

    async def exercise() -> None:
        coordinator = PreparedFillerCoordinator(
            PreparedFillerSettings(mode="active", generation_max_attempts=1), generator
        )
        coordinator.reconcile([_plan()])
        await coordinator.wait_idle()
        assert coordinator.health == PreparedFillerHealth.FATAL
        notice = coordinator.fatal_notice("cs")
        assert notice == (1, "LLM fatal error, nemám texty.")
        assert coordinator.fatal_notice("cs") == notice
        assert coordinator.mark_fatal_notice_spoken(1)
        assert coordinator.fatal_notice("cs") is None
        assert not coordinator.mark_fatal_notice_spoken(1)
        await coordinator.close()

    asyncio.run(exercise())


def test_buffer_reserves_capacity_for_current_and_next_stage() -> None:
    settings = PreparedFillerSettings(
        max_ready_plans=6, reserved_current_stage=3, reserved_next_stage=2
    )
    buffer = PreparedFillerBuffer(settings)
    current = [
        PreparedFillerPlan.create(
            node_id=f"current.{index}",
            semantic_key=f"current.{index}",
            locale="en",
            scope_key="stream:1:stage:1",
            stage_epoch=1,
            allowed_stages=("GRID_PREP",),
            required=(FactProposition("track", "Spa", "telemetry", "r1", "Spa"),),
            tier=index,
        )
        for index in range(5)
    ]
    following = [
        PreparedFillerPlan.create(
            node_id=f"next.{index}",
            semantic_key=f"next.{index}",
            locale="en",
            scope_key="stream:1:stage:2",
            stage_epoch=2,
            allowed_stages=("FORMATION_OR_LIGHTS",),
            required=(FactProposition("track", "Spa", "telemetry", "r1", "Spa"),),
            tier=index,
        )
        for index in range(5)
    ]

    buffer.reconcile([*current, *following], current_stage="GRID_PREP")

    desired = buffer.desired
    assert len(desired) == 6
    assert sum("GRID_PREP" in plan.allowed_stages for plan in desired) >= 3
    assert sum("FORMATION_OR_LIGHTS" in plan.allowed_stages for plan in desired) >= 2


def test_prepared_next_stage_plan_survives_expected_transition() -> None:
    base = {
        "session_id": "42:0",
        "identity": {"overlay_mode": "RACE", "run_epoch": 3},
        "race": {"class_field_size": 18, "class_position": 6, "player_car_class": 7},
        "story": {},
        "prepared": {"start_mode": "rolling"},
    }
    before = {
        **base,
        "editorial": {
            "stage": "GRID_PREP",
            "next_stage": "FORMATION_OR_LIGHTS",
            "stage_epoch": 5,
            "stream_epoch": 2,
            "stint_epoch": 0,
            "track_name": "Spa",
        },
    }
    after = {
        **base,
        "editorial": {
            "stage": "FORMATION_OR_LIGHTS",
            "next_stage": "LIVE_SESSION",
            "stage_epoch": 6,
            "stream_epoch": 2,
            "stint_epoch": 0,
            "track_name": "Spa",
        },
    }

    prefetched = next(
        plan
        for plan in build_prepared_filler_plans(before, "en")
        if "FORMATION_OR_LIGHTS" in plan.allowed_stages and plan.stage_epoch == 6
    )
    current = next(
        plan
        for plan in build_prepared_filler_plans(after, "en")
        if "FORMATION_OR_LIGHTS" in plan.allowed_stages
    )

    assert prefetched.plan_id == current.plan_id
    assert ":run:3:" in current.scope_key


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (1, ["pole"]),
        (2, ["pole", "podium"]),
        (3, ["pole", "podium", "podium"]),
        (4, ["pole", "podium", "podium", "classified"]),
        (5, ["pole", "podium", "podium", "classified", "classified"]),
        (6, ["pole", "podium", "podium", "middle_third", "rear_third", "rear_third"]),
        (
            7,
            [
                "pole",
                "podium",
                "podium",
                "middle_third",
                "middle_third",
                "middle_third",
                "rear_third",
            ],
        ),
        (
            8,
            [
                "pole",
                "podium",
                "podium",
                "middle_third",
                "middle_third",
                "middle_third",
                "rear_third",
                "rear_third",
            ],
        ),
        (
            9,
            [
                "pole",
                "podium",
                "podium",
                "middle_third",
                "middle_third",
                "middle_third",
                "rear_third",
                "rear_third",
                "rear_third",
            ],
        ),
        (
            10,
            [
                "pole",
                "podium",
                "podium",
                "top_third",
                "middle_third",
                "middle_third",
                "middle_third",
                "middle_third",
                "rear_third",
                "rear_third",
            ],
        ),
        (
            11,
            [
                "pole",
                "podium",
                "podium",
                "top_third",
                "middle_third",
                "middle_third",
                "middle_third",
                "middle_third",
                "rear_third",
                "rear_third",
                "rear_third",
            ],
        ),
        (
            12,
            [
                "pole",
                "podium",
                "podium",
                "top_third",
                "middle_third",
                "middle_third",
                "middle_third",
                "middle_third",
                "rear_third",
                "rear_third",
                "rear_third",
                "rear_third",
            ],
        ),
    ],
)
def test_result_bands_cover_every_position_for_fields_one_to_twelve(
    size: int, expected: list[str]
) -> None:
    assert [result_band(position, size) for position in range(1, size + 1)] == expected
    assert result_band(size + 1, size) == "unclassified"


def test_confirmed_position_without_field_size_uses_classified_fallback() -> None:
    assert result_band(1, None) == "pole"
    assert result_band(2, None) == "podium"
    assert result_band(7, None) == "classified"


def _conclusion_context(
    mode: str,
    *,
    position: int | None,
    field_size: int = 12,
    confirmed: bool = True,
    story: dict[str, object] | None = None,
    captured_ms: int = 10_000,
) -> dict[str, object]:
    return {
        "captured_monotonic_ms": captured_ms,
        "session_id": "42:2",
        "identity": {
            "overlay_mode": mode,
            "run_epoch": 4,
            "subsession_id": "42",
        },
        "editorial": {
            "stage": "SESSION_CONCLUSION",
            "next_stage": "BETWEEN_SESSIONS",
            "stage_epoch": 9,
            "stage_started_monotonic_ms": 1_000,
            "stream_epoch": 2,
            "stint_epoch": 1,
            "track_name": "Spa",
        },
        "race": {
            "class_position": position,
            "class_field_size": field_size,
            "player_car_class": 7,
            "player_finished": confirmed,
            "session_finished": confirmed,
            "lap_completed": 12,
            "best_lap_time": 91.234,
        },
        "story": story or {},
    }


def test_quali_and_practice_conclusion_branches_are_independent() -> None:
    quali = build_prepared_filler_plans(_conclusion_context("QUALIFYING", position=4), "en")
    practice = build_prepared_filler_plans(_conclusion_context("PRACTICE", position=7), "en")

    assert {plan.semantic_key for plan in quali} == {
        "quali_result_top_third",
        "quali_to_race_bridge",
        "stream_chapter_bridge",
    }
    assert {plan.semantic_key for plan in practice} == {
        "practice_checkered_summary",
        "practice_value_debrief",
        "stream_chapter_bridge",
    }


def test_race_result_prefers_podium_then_same_scope_quali_comparison() -> None:
    same_quali = {
        "quali_bag": {
            "class_position": 6,
            "best_lap_s": 90.0,
            "class_id": 7,
            "subsession_id": "42",
        }
    }
    podium = build_prepared_filler_plans(
        _conclusion_context("RACE", position=2, story=same_quali), "en"
    )
    gain = build_prepared_filler_plans(
        _conclusion_context("RACE", position=4, story=same_quali), "en"
    )

    assert [plan.semantic_key for plan in podium] == [
        "race_result_podium",
        "stream_chapter_bridge",
    ]
    assert [plan.semantic_key for plan in gain] == [
        "race_result_gain_vs_quali",
        "stream_chapter_bridge",
    ]
    assert any(fact.proposition_id == "result_relation" for fact in gain[0].required)


@pytest.mark.parametrize(
    ("finish", "qualifying", "relation"),
    [(4, 6, "gain"), (6, 6, "hold"), (8, 6, "loss")],
)
def test_race_result_covers_each_quali_comparison(
    finish: int, qualifying: int, relation: str
) -> None:
    plans = build_prepared_filler_plans(
        _conclusion_context(
            "RACE",
            position=finish,
            story={
                "quali_bag": {
                    "class_position": qualifying,
                    "class_id": 7,
                    "subsession_id": "42",
                }
            },
        ),
        "en",
    )
    assert [plan.semantic_key for plan in plans] == [
        f"race_result_{relation}_vs_quali",
        "stream_chapter_bridge",
    ]


def test_race_result_uses_grid_only_for_matching_scope() -> None:
    grid = {
        "race_grid_position": 8,
        "race_grid_class_id": 7,
        "race_grid_subsession_id": "42",
    }
    plans = build_prepared_filler_plans(_conclusion_context("RACE", position=6, story=grid), "en")
    assert [plan.semantic_key for plan in plans] == [
        "race_result_gain_vs_grid",
        "stream_chapter_bridge",
    ]


def test_race_result_rejects_stale_comparisons_and_uses_safe_fallbacks() -> None:
    stale = {
        "quali_bag": {
            "class_position": 10,
            "class_id": 99,
            "subsession_id": "old",
        },
        "race_grid_position": 10,
        "race_grid_class_id": 99,
        "race_grid_subsession_id": "old",
    }
    absolute = build_prepared_filler_plans(
        _conclusion_context("RACE", position=9, story=stale), "en"
    )
    unclassified = build_prepared_filler_plans(
        _conclusion_context("RACE", position=None, story=stale), "en"
    )

    assert [plan.semantic_key for plan in absolute] == [
        "race_result_rear_third",
        "stream_chapter_bridge",
    ]
    assert [plan.semantic_key for plan in unclassified] == [
        "race_result_unclassified",
        "stream_chapter_bridge",
    ]


def test_unconfirmed_result_waits_then_uses_generic_close() -> None:
    waiting = build_prepared_filler_plans(
        _conclusion_context("QUALIFYING", position=3, confirmed=False, captured_ms=8_999),
        "en",
    )
    timed_out = build_prepared_filler_plans(
        _conclusion_context("QUALIFYING", position=3, confirmed=False, captured_ms=9_000),
        "en",
    )

    assert [plan.semantic_key for plan in waiting] == ["stream_chapter_bridge"]
    assert [plan.semantic_key for plan in timed_out] == [
        "result_unconfirmed",
        "stream_chapter_bridge",
    ]


def test_coordinator_can_reopen_after_supervisor_restart() -> None:
    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        return _variants(count=count)

    async def exercise() -> None:
        coordinator = PreparedFillerCoordinator(PreparedFillerSettings(mode="shadow"), generator)
        await coordinator.close()
        coordinator.reopen()
        coordinator.reconcile([_plan()], current_stage="STREAM_LOBBY_INTRO")
        await coordinator.wait_idle()
        assert coordinator.health == PreparedFillerHealth.READY
        assert coordinator.status()["inflight"] == 0
        await coordinator.close()

    asyncio.run(exercise())


def test_context_invalidation_cancels_inflight_generation() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def exercise() -> None:
        coordinator = PreparedFillerCoordinator(PreparedFillerSettings(mode="shadow"), generator)
        coordinator.reconcile([_plan()], current_stage="STREAM_LOBBY_INTRO")
        await asyncio.wait_for(started.wait(), timeout=1)
        coordinator.reconcile((), current_stage="WAIT_CONTEXT")
        await asyncio.wait_for(cancelled.wait(), timeout=1)
        await asyncio.sleep(0)
        assert coordinator.status()["inflight"] == 0
        assert coordinator.buffer.desired == ()
        await coordinator.close()

    asyncio.run(exercise())


def test_next_stage_readiness_does_not_mask_current_stage_fatal() -> None:
    calls: list[str] = []
    current = _plan(stage="GRID_PREP")
    following = PreparedFillerPlan.create(
        node_id="prepared.formation",
        semantic_key="formation.setup",
        locale="en",
        scope_key="stream:1:stage:2",
        stage_epoch=2,
        allowed_stages=("FORMATION_OR_LIGHTS",),
        required=(FactProposition("track", "Spa", "telemetry", "r1", "Spa"),),
    )

    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        calls.append(plan.allowed_stages[0])
        return [] if plan is current else _variants(count=count)

    async def exercise() -> None:
        coordinator = PreparedFillerCoordinator(
            PreparedFillerSettings(mode="active", max_inflight=1, generation_max_attempts=1),
            generator,
        )
        coordinator.reconcile([following, current], current_stage="GRID_PREP")
        await coordinator.wait_idle()

        assert calls[0] == "GRID_PREP"
        assert coordinator.status()["readyNextStage"] == 1
        assert coordinator.status()["readyCurrentStage"] == 0
        assert coordinator.health == PreparedFillerHealth.FATAL
        await coordinator.close()

    asyncio.run(exercise())
