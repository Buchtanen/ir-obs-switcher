"""#284 NarrativeRuntime — thin library slice."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from test_episode_registry import _intent as _episode_intent
from test_narrative_context_batch import _event, _fact_view, _timeline
from test_opportunity_queue import _intent as _opportunity_intent
from test_story_director import _cand as _director_cand
from test_story_director import _world as _director_world

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts import NarrativeEvent
from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.beat_plan import CandidateOrder
from irswitch.events.episode_registry import EpisodeRegistry
from irswitch.events.exposure_store import ExposureStore
from irswitch.events.freshness_commit import (
    SCHEMA_VERSION,
    CommitToken,
    CommitWorld,
    FreshnessGate,
)
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_runtime import NarrativeRuntime, ReduceResult, RuntimeStatus
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.semantic_verifier import SemanticVerifier
from irswitch.events.story_director import StoryDirector

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_runtime.py"
)

RESULT_OK = {
    "schemaVersion": "realization-result/2",
    "resultId": "result:1",
    "requestId": "request:1",
    "requestOrdinal": 1,
    "dispatchGeneration": 1,
    "backend": "authored",
    "outcome": "succeeded",
    "text": "Clear sentence.",
    "textHash": "sha256:" + "1" * 64,
    "failureReason": None,
    "modelReported": None,
    "transportStartedMonoMs": 1,
    "responseStartedMonoMs": 1,
    "firstContentMonoMs": 1,
    "completedMonoMs": 2,
    "promptTokens": None,
    "completionTokens": None,
    "totalTokens": None,
    "usageSource": "unavailable",
    "finishReason": None,
    "resultHash": "sha256:" + "2" * 64,
}


def _pure_fact(command_id: str, *, revision: int = 3, fanout: int = 11) -> NarrativeCommand:
    part = partition_context_batches(
        timeline=_timeline(revision=revision),
        fact_view=_fact_view(1, revision=revision + 6),
        events=(),
        fanout_stream_sequence=fanout,
    )[0]
    return NarrativeCommand.context_batch(command_id, 1000, part)


def _event_impulse(
    command_id: str, *, revision: int = 3, fanout: int = 11, index: int = 0
) -> NarrativeCommand:
    part = partition_context_batches(
        timeline=_timeline(revision=revision),
        fact_view=_fact_view(1, revision=9),
        events=(_event(index, fanout=fanout),),
        fanout_stream_sequence=fanout,
    )[0]
    return NarrativeCommand.context_batch(command_id, 1000, part)


def _result_for(token: dict[str, object], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        **RESULT_OK,
        "requestId": token["requestId"],
        "requestOrdinal": token["requestOrdinal"],
        "dispatchGeneration": token["dispatchGeneration"],
    }
    payload.update(overrides)
    return payload


def _minimal_commit_pair(
    *,
    episode_revision: int = 1,
    world_episode_revision: int | None = None,
    lane: str = "building",
) -> tuple[CommitToken, CommitWorld]:
    token = CommitToken(
        schema_version=SCHEMA_VERSION,
        token_id="commit:test",
        plan_id="plan:test",
        beat_id="beat:test",
        episode_id="episode:test",
        episode_revision=episode_revision,
        stream_epoch=1,
        occurrence_id=None,
        lineage_id=None,
        target_identity=(),
        selected_facts=(),
        opportunity_id=None,
        reservation_token=None,
        opportunity_material_revision=None,
        opportunity_expires_mono_ms=None,
        planned_mono_ms=0,
        fact_view_revision=1,
    )
    world = CommitWorld(
        now_ms=100,
        lane=lane,
        stream_epoch=1,
        occurrence_id=None,
        lineage_id=None,
        episode_id="episode:test",
        episode_revision=(
            episode_revision if world_episode_revision is None else world_episode_revision
        ),
        episode_state="active",
        target_identity=(),
        facts=(),
        fact_view_revision=1,
        opportunity_state=None,
        opportunity_material_revision=None,
        opportunity_expires_mono_ms=None,
        reservation_token=None,
        critical_conflict=False,
    )
    return token, world


def test_not_exported_and_not_live_wired() -> None:
    assert "NarrativeRuntime" not in events_exports
    text = SOURCE.read_text(encoding="utf-8")
    assert "irswitch.overlay" not in text
    assert "irswitch.commentary.consumer" not in text
    assert "eval(" not in text


def test_enable_and_immutable_status() -> None:
    runtime = NarrativeRuntime()
    assert runtime.status().runtime_state == "disabled"
    runtime.enable()
    status = runtime.status()
    assert isinstance(status, RuntimeStatus)
    assert status.runtime_state == "ready"
    assert status.lane == "idle"
    assert status.reducer_sequence == 0
    assert status.history_complete is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.lane = "building"  # type: ignore[misc]


def test_reducer_sequence_follows_mailbox_order() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    assert runtime.admit(_pure_fact("c1")).accepted
    assert runtime.admit(
        NarrativeCommand.config_update("c2", 1100, valid=False, ledger=None, diagnostics=())
    ).accepted
    assert runtime.admit(NarrativeCommand.shutdown("c3", 1200, "application_exit")).accepted

    results = list(runtime.drain())
    assert [item.reducer_sequence for item in results] == [1, 2, 3]
    assert [item.command_id for item in results] == ["c1", "c2", "c3"]
    assert results[-1].kind == "SHUTDOWN"
    assert runtime.status().runtime_state == "stopped"


def test_pure_fact_skips_director_event_caps_two_plans() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()

    runtime.admit(_pure_fact("fact:1"))
    pure = runtime.reduce_next()
    assert isinstance(pure, ReduceResult)
    assert pure.disposition == "handled"
    assert pure.planning_cycle_id == 0
    assert pure.plans_dispatched == 0
    assert "director_skipped_pure_fact" in pure.effects

    runtime.admit(_event_impulse("e1", fanout=11))
    first = runtime.reduce_next()
    assert first is not None
    assert first.planning_cycle_id == 1
    assert first.plans_dispatched == 1
    assert first.lane_after == "building"
    assert "planning_cycle_opened:event_impulse" in first.effects

    # Same-cycle alternate after in-cycle failure (plans_in_cycle == 1).
    runtime.fail_current_realization_for_test()
    runtime.admit(_event_impulse("e2", revision=4, fanout=12))
    second = runtime.reduce_next()
    assert second is not None
    assert second.planning_cycle_id == 1
    assert second.plans_dispatched == 2

    # New accepted event after the cycle budget is spent opens a fresh cycle.
    runtime.fail_current_realization_for_test()
    runtime.admit(_event_impulse("e3", revision=5, fanout=13))
    third = runtime.reduce_next()
    assert third is not None
    assert third.planning_cycle_id == 2
    assert third.plans_dispatched == 1
    assert "planning_cycle_opened:event_after_exhausted" in third.effects


def test_stale_token_manual_busy_recovery_shutdown() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(_event_impulse("e1"))
    runtime.reduce_next()

    runtime.admit(
        NarrativeCommand.realization_result(
            "rz:stale",
            "REALIZATION_SUCCEEDED",
            2000,
            request_id="request:other",
            request_ordinal=9,
            dispatch_generation=9,
            result=_result_for(
                {
                    "requestId": "request:other",
                    "requestOrdinal": 9,
                    "dispatchGeneration": 9,
                },
                resultId="result:stale",
            ),
        )
    )
    stale = runtime.reduce_next()
    assert stale is not None
    assert stale.disposition == "ignored_stale_or_inapplicable"
    assert runtime.status().lane == "building"

    runtime.admit(
        NarrativeCommand.manual_speak("manual:1", 3000, text="Hello there", admission_ordinal=1)
    )
    busy = runtime.reduce_next()
    assert busy is not None
    assert busy.disposition == "rejected_busy"

    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "rz:ok",
            "REALIZATION_SUCCEEDED",
            2100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"

    latest = _pure_fact("latest", revision=9, fanout=20)
    runtime.admit(
        NarrativeCommand.recovery(
            "recovery:1",
            4000,
            latest_context=latest.context_part,
            loss_first_sequence=2,
            loss_last_sequence=4,
            safety_effects=(latest.safety_effect(),),
        )
    )
    recovered = runtime.reduce_next()
    assert recovered is not None
    assert recovered.disposition == "handled"
    status = runtime.status()
    assert status.history_complete is False
    assert status.timeline_revision == 9

    async def _shutdown() -> str:
        task = asyncio.create_task(runtime.run())
        runtime.admit(NarrativeCommand.shutdown("shutdown:1", 9000, "application_exit"))
        await asyncio.wait_for(task, timeout=2)
        return runtime.status().runtime_state

    assert asyncio.run(_shutdown()) == "stopped"


def test_same_admissions_replay_identically() -> None:
    batch = [
        _pure_fact("r1"),
        NarrativeCommand.deadline(
            "r2", "LONG_SILENCE_ELAPSED", 2, generation=1, deadline_mono_ms=2
        ),
        NarrativeCommand.shutdown("r3", 3, "application_exit"),
    ]

    def play() -> list[tuple[int, str, str]]:
        runtime = NarrativeRuntime(mailbox=NarrativeMailbox())
        runtime.enable()
        for command in batch:
            assert runtime.admit(command).accepted
        return [
            (item.reducer_sequence, item.command_id, item.disposition) for item in runtime.drain()
        ]

    assert play() == play()


def _tts_callback(
    kind: str,
    token: dict[str, object],
    *,
    command_id: str | None = None,
    stale: bool = False,
) -> NarrativeCommand:
    kind_map = {
        "PLAYBACK_ACCEPTED": ("playback_accepted", None),
        "SPEECH_COMPLETED": ("completed", None),
        "SPEECH_INTERRUPTED": ("interrupted", "backend_cancelled"),
        "SPEECH_FAILED": ("failed", "backend_rejected"),
    }
    callback_kind, detail = kind_map[kind]
    utterance_id = "utterance:stale" if stale else str(token["utteranceId"])
    utterance_ordinal = 9 if stale else int(token["utteranceOrdinal"])  # type: ignore[arg-type]
    backend_generation = 9 if stale else int(token["backendGeneration"])  # type: ignore[arg-type]
    dispatch_generation = 9 if stale else int(token["dispatchGeneration"])  # type: ignore[arg-type]
    return NarrativeCommand.tts_callback(
        command_id or f"tts:{kind}:{utterance_id}",
        kind,  # type: ignore[arg-type]
        5000,
        utterance_id=utterance_id,
        utterance_ordinal=utterance_ordinal,
        backend_generation=backend_generation,
        dispatch_generation=dispatch_generation,
        callback={
            "schemaVersion": "tts-callback/2",
            "callbackId": f"cb:{kind}:{utterance_id}",
            "kind": callback_kind,
            "utteranceId": utterance_id,
            "utteranceOrdinal": utterance_ordinal,
            "backend": "sapi",
            "backendGeneration": backend_generation,
            "dispatchGeneration": dispatch_generation,
            "workerSequence": 1,
            "observedMonoMs": 10,
            "detailCode": detail,
        },
    )


def _drive_to(lane: str) -> NarrativeRuntime:
    runtime = NarrativeRuntime()
    runtime.enable()
    if lane == "idle":
        return runtime
    runtime.admit(_event_impulse(f"drive:{lane}:event", fanout=21))
    assert runtime.reduce_next() is not None
    if lane == "building":
        assert runtime.status().lane == "building"
        return runtime
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            f"drive:{lane}:rz",
            "REALIZATION_SUCCEEDED",
            2100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    assert runtime.reduce_next() is not None
    if lane == "committed":
        assert runtime.status().lane == "committed"
        return runtime
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    if lane == "stopping":
        runtime.admit(
            NarrativeCommand.speech_deadline(
                f"drive:{lane}:deadline",
                2200,
                utterance_id=str(utterance["utteranceId"]),
                utterance_ordinal=int(utterance["utteranceOrdinal"]),  # type: ignore[arg-type]
                backend_generation=int(utterance["backendGeneration"]),  # type: ignore[arg-type]
                dispatch_generation=int(utterance["dispatchGeneration"]),  # type: ignore[arg-type]
                stage="start",
                deadline_mono_ms=2200,
            )
        )
        assert runtime.reduce_next() is not None
        assert runtime.status().lane == "stopping"
        return runtime
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id=f"drive:{lane}:pb"))
    assert runtime.reduce_next() is not None
    assert runtime.status().lane == "speaking"
    if lane == "speaking":
        return runtime
    raise AssertionError(f"unsupported lane {lane}")


def _command_for_matrix(
    runtime: NarrativeRuntime,
    *,
    lane: str,
    command: str,
    disposition: str,
) -> NarrativeCommand:
    realization = runtime.current_realization_token()
    utterance = runtime.current_utterance_token()
    stale_realization = disposition == "ignored_stale_or_inapplicable"
    stale_utterance = disposition == "ignored_stale_or_inapplicable"

    if command == "APPLY_CONTEXT_BATCH":
        return _pure_fact(f"matrix:{lane}:{command}", revision=30, fanout=30)
    if command == "CONFIG_UPDATE":
        return NarrativeCommand.config_update(
            f"matrix:{lane}:{command}",
            3000,
            valid=False,
            ledger=None,
            diagnostics=(),
        )
    if command == "LONG_SILENCE_ELAPSED":
        generation = 1 if disposition == "handled" else 0
        return NarrativeCommand.deadline(
            f"matrix:{lane}:{command}",
            "LONG_SILENCE_ELAPSED",
            3000,
            generation=generation,
            deadline_mono_ms=3000,
        )
    if command == "VALIDITY_DEADLINE_ELAPSED":
        generation = max(1, runtime.status().planning_cycle_id)
        if disposition == "ignored_stale_or_inapplicable":
            generation = 0
        return NarrativeCommand.deadline(
            f"matrix:{lane}:{command}",
            "VALIDITY_DEADLINE_ELAPSED",
            3000,
            generation=generation,
            deadline_mono_ms=3000,
        )
    if command in {"REALIZATION_SUCCEEDED", "REALIZATION_FAILED"}:
        token = {
            "requestId": "request:stale",
            "requestOrdinal": 9,
            "dispatchGeneration": 9,
        }
        if realization is not None and not stale_realization:
            token = realization
        if command == "REALIZATION_SUCCEEDED":
            result = _result_for(token, resultId=f"result:{lane}:{command}")
        else:
            result = _result_for(
                token,
                outcome="failed",
                text=None,
                textHash=None,
                failureReason="realization_transport",
                resultId=f"result:{lane}:{command}",
            )
        return NarrativeCommand.realization_result(
            f"matrix:{lane}:{command}",
            command,  # type: ignore[arg-type]
            3000,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=result,
        )
    if command == "REALIZATION_DEADLINE_ELAPSED":
        token = {
            "requestId": "request:stale",
            "requestOrdinal": 9,
            "dispatchGeneration": 9,
        }
        if realization is not None and not stale_realization:
            token = realization
        return NarrativeCommand.realization_deadline(
            f"matrix:{lane}:{command}",
            3000,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            deadline_mono_ms=3000,
        )
    if command in {
        "PLAYBACK_ACCEPTED",
        "SPEECH_COMPLETED",
        "SPEECH_INTERRUPTED",
        "SPEECH_FAILED",
    }:
        token = {
            "utteranceId": "utterance:stale",
            "utteranceOrdinal": 9,
            "backendGeneration": 9,
            "dispatchGeneration": 9,
        }
        if utterance is not None and not stale_utterance:
            token = utterance
        return _tts_callback(command, token, stale=False)
    if command == "SPEECH_DEADLINE_ELAPSED":
        token = {
            "utteranceId": "utterance:stale",
            "utteranceOrdinal": 9,
            "backendGeneration": 9,
            "dispatchGeneration": 9,
        }
        if utterance is not None and not stale_utterance:
            token = utterance
        return NarrativeCommand.speech_deadline(
            f"matrix:{lane}:{command}",
            3000,
            utterance_id=str(token["utteranceId"]),
            utterance_ordinal=int(token["utteranceOrdinal"]),  # type: ignore[arg-type]
            backend_generation=int(token["backendGeneration"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            stage="playback",
            deadline_mono_ms=3000,
        )
    if command == "MANUAL_SPEAK_REQUEST":
        return NarrativeCommand.manual_speak(
            f"matrix:{lane}:{command}",
            3000,
            text="Matrix manual line.",
            admission_ordinal=1,
        )
    if command == "TAPE_HEALTH_CHANGED":
        return NarrativeCommand.tape_health(
            f"matrix:{lane}:{command}",
            3000,
            recorder_generation=1,
            status="degraded",
            affected_detector_ids=("battle",),
            first_lost_sequence=1,
            last_lost_sequence=1,
        )
    if command == "COMPONENT_HEALTH_CHANGED":
        return NarrativeCommand.component_health(
            f"matrix:{lane}:{command}",
            3000,
            component="llm",
            generation=1,
            status="ready",
            reason=None,
        )
    if command == "MAILBOX_RECOVERY":
        latest = _pure_fact(f"matrix:{lane}:latest", revision=40, fanout=40)
        return NarrativeCommand.recovery(
            f"matrix:{lane}:{command}",
            3000,
            latest_context=latest.context_part,
            loss_first_sequence=1,
            loss_last_sequence=2,
            safety_effects=(latest.safety_effect(),),
        )
    if command == "SHUTDOWN":
        return NarrativeCommand.shutdown(f"matrix:{lane}:{command}", 3000, "application_exit")
    raise AssertionError(command)


def _load_matrix() -> list[dict[str, object]]:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1] / "docs/v2.0.0/machine/actor-transition-model.json"
        ).read_text(encoding="utf-8")
    )
    key = next(name for name in payload if "trans" in name.lower())
    return list(payload[key])


@pytest.mark.parametrize(
    "row",
    _load_matrix(),
    ids=lambda row: f"{row['lane']}__{row['command']}__{row['disposition']}",
)
def test_actor_transition_matrix_row(row: dict[str, object]) -> None:
    lane = str(row["lane"])
    command_kind = str(row["command"])
    disposition = str(row["disposition"])
    possible = set(row["possibleNextLanes"])  # type: ignore[arg-type]

    runtime = _drive_to(lane)
    command = _command_for_matrix(runtime, lane=lane, command=command_kind, disposition=disposition)
    assert runtime.admit(command).accepted
    result = runtime.reduce_next()
    assert result is not None
    assert result.kind == command_kind
    assert result.disposition == disposition
    if runtime.status().runtime_state == "stopped":
        # Terminal shutdown may settle the speech lane to idle once tokens clear.
        assert result.lane_after in possible | {"idle"}
    else:
        assert result.lane_after in possible


def test_duplicate_speech_callback_is_ignored() -> None:
    runtime = _drive_to("speaking")
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="dup:1"))
    first = runtime.reduce_next()
    assert first is not None
    assert first.disposition == "handled"
    assert first.lane_after == "idle"
    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="dup:2"))
    second = runtime.reduce_next()
    assert second is not None
    assert second.disposition == "ignored_stale_or_inapplicable"
    assert runtime.status().lane == "idle"


def test_config_update_cancels_building_and_rearms_deadlines() -> None:
    runtime = _drive_to("building")
    runtime.admit(
        NarrativeCommand.config_update(
            "config:cancel", 4000, valid=False, ledger=None, diagnostics=()
        )
    )
    result = runtime.reduce_next()
    assert result is not None
    assert result.disposition == "handled"
    assert result.lane_after == "building"
    assert "effect:cancel_realization" not in result.effects
    assert "effect:cancel_silence_deadline" in result.effects
    assert "effect:arm_silence_deadline" in result.effects


def test_realization_and_manual_dispatch_tts_effect() -> None:
    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "rz:effect",
            "REALIZATION_SUCCEEDED",
            4100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert "effect:dispatch_tts" in committed.effects

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "manual:effect", 4200, text="Effect line.", admission_ordinal=1
        )
    )
    manual = runtime.reduce_next()
    assert manual is not None
    assert manual.lane_after == "committed"
    assert "effect:dispatch_tts" in manual.effects


def test_shutdown_while_building_cancels_realization_effect() -> None:
    runtime = _drive_to("building")
    assert runtime.admit(
        NarrativeCommand.shutdown("shutdown:race", 5000, "application_exit")
    ).accepted
    result = runtime.reduce_next()
    assert result is not None
    assert result.disposition == "handled"
    assert "effect:cancel_realization" in result.effects
    assert result.lane_after == "idle"
    assert runtime.status().runtime_state == "stopped"
    assert runtime.status().lane == "idle"


@pytest.mark.asyncio
async def test_realization_effect_task_admits_command_only() -> None:
    seen: list[dict[str, object]] = []

    async def realize(token: dict[str, object]) -> NarrativeCommand:
        seen.append(dict(token))
        await asyncio.sleep(0)
        return NarrativeCommand.realization_result(
            "effect:rz:ok",
            "REALIZATION_SUCCEEDED",
            6000,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )

    runtime = NarrativeRuntime(realization_effect=realize)
    runtime.enable()
    assert runtime.admit(_event_impulse("effect:plan", revision=5, fanout=5)).accepted
    planned = runtime.reduce_next()
    assert planned is not None
    assert "effect:dispatch_realization" in planned.effects
    await runtime.apply_effects(planned.effects)
    assert runtime.realization_task_active()
    await runtime.wait_effects_idle()
    assert not runtime.realization_task_active()
    assert seen and str(seen[0]["requestId"]).startswith("request:")
    completed = runtime.reduce_next()
    assert completed is not None
    assert completed.kind == "REALIZATION_SUCCEEDED"
    assert completed.disposition == "handled"
    assert completed.lane_after == "committed"
    assert "effect:dispatch_tts" in completed.effects


@pytest.mark.asyncio
async def test_cancel_realization_drops_stale_completion() -> None:
    release = asyncio.Event()

    async def slow_realize(token: dict[str, object]) -> NarrativeCommand:
        await release.wait()
        return NarrativeCommand.realization_result(
            "effect:rz:stale",
            "REALIZATION_SUCCEEDED",
            6100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )

    runtime = NarrativeRuntime(realization_effect=slow_realize)
    runtime.enable()
    runtime.admit(_event_impulse("effect:cancel-plan", revision=6, fanout=6))
    planned = runtime.reduce_next()
    assert planned is not None
    await runtime.apply_effects(planned.effects)
    assert runtime.realization_task_active()

    runtime.admit(NarrativeCommand.shutdown("effect:cancel-shutdown", 6200, "application_exit"))
    shutdown = runtime.reduce_next()
    assert shutdown is not None
    assert "effect:cancel_realization" in shutdown.effects
    await runtime.apply_effects(shutdown.effects)
    release.set()
    await runtime.wait_effects_idle()
    assert runtime.mailbox_empty()
    assert runtime.reduce_next() is None
    assert runtime.status().runtime_state == "stopped"


@pytest.mark.asyncio
async def test_at_most_one_realization_and_one_tts_task() -> None:
    rz_starts = 0
    tts_starts = 0
    gate = asyncio.Event()

    async def realize(token: dict[str, object]) -> NarrativeCommand:
        nonlocal rz_starts
        rz_starts += 1
        await gate.wait()
        return NarrativeCommand.realization_result(
            f"effect:rz:{rz_starts}",
            "REALIZATION_FAILED",
            6300,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(
                token,
                outcome="failed",
                text=None,
                textHash=None,
                failureReason="library_test",
            ),
        )

    async def speak(token: dict[str, object]) -> NarrativeCommand:
        nonlocal tts_starts
        tts_starts += 1
        await gate.wait()
        return _tts_callback("SPEECH_COMPLETED", token, command_id=f"effect:tts:{tts_starts}")

    runtime = NarrativeRuntime(realization_effect=realize, tts_effect=speak)
    runtime.enable()
    runtime.admit(_event_impulse("effect:one-rz", revision=7, fanout=7))
    first = runtime.reduce_next()
    assert first is not None
    await runtime.apply_effects(first.effects)
    runtime.fail_current_realization_for_test()
    runtime.admit(_event_impulse("effect:two-rz", revision=8, fanout=8))
    second = runtime.reduce_next()
    assert second is not None
    await runtime.apply_effects(second.effects)
    assert runtime.realization_task_active()
    assert rz_starts == 2

    runtime = NarrativeRuntime(tts_effect=speak)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak("effect:tts-a", 6500, text="One.", admission_ordinal=1)
    )
    manual = runtime.reduce_next()
    assert manual is not None
    await runtime.apply_effects(manual.effects)
    assert runtime.tts_task_active()
    rejected = runtime.admit(
        NarrativeCommand.manual_speak("effect:tts-b", 6510, text="Two.", admission_ordinal=2)
    )
    assert rejected.accepted
    busy = runtime.reduce_next()
    assert busy is not None
    assert busy.disposition == "rejected_busy"
    assert "effect:dispatch_tts" not in busy.effects
    assert tts_starts == 1
    gate.set()
    await runtime.wait_effects_idle()


@pytest.mark.asyncio
async def test_run_loop_applies_effects_through_commit() -> None:
    async def realize(token: dict[str, object]) -> NarrativeCommand:
        await asyncio.sleep(0)
        return NarrativeCommand.realization_result(
            "run:rz",
            "REALIZATION_SUCCEEDED",
            7000,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )

    runtime = NarrativeRuntime(realization_effect=realize)
    runtime.enable()
    runtime.admit(_event_impulse("run:plan", revision=9, fanout=9))

    task = asyncio.create_task(runtime.run())
    for _ in range(50):
        if runtime.status().lane == "committed" and runtime.status().reducer_sequence >= 2:
            break
        await asyncio.sleep(0.01)
    assert runtime.status().lane == "committed"
    runtime.admit(NarrativeCommand.shutdown("run:stop", 7100, "application_exit"))
    await asyncio.wait_for(task, timeout=2.0)
    assert runtime.status().runtime_state == "stopped"
    assert runtime.status().reducer_sequence >= 2


def test_admission_diagnostics_surface_coalesce_and_overflow_reasons() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    first = NarrativeCommand.deadline(
        "diag:silence:1", "LONG_SILENCE_ELAPSED", 8000, generation=1, deadline_mono_ms=8000
    )
    second = NarrativeCommand.deadline(
        "diag:silence:2", "LONG_SILENCE_ELAPSED", 8010, generation=1, deadline_mono_ms=8010
    )
    assert runtime.admit(first).reason == "accepted"
    coalesced = runtime.admit(second)
    assert coalesced.reason == "coalesced"
    status = runtime.status()
    assert status.last_admission_reason == "coalesced"
    assert status.mailbox_depth == 1
    assert status.mailbox_capacity == NarrativeMailbox.TOTAL_CAPACITY
    assert "coalesced" in status.admission_diagnostics
    assert status.mailbox_overflows == 0

    for index in range(NarrativeMailbox.ORDINARY_CELLS - 1):
        runtime.admit(
            NarrativeCommand.deadline(
                f"diag:fill:{index}",
                "LONG_SILENCE_ELAPSED",
                8100 + index,
                generation=2 + index,
                deadline_mono_ms=8100 + index,
            )
        )
    runtime.admit(
        NarrativeCommand.deadline(
            "diag:fill:last",
            "LONG_SILENCE_ELAPSED",
            8200,
            generation=100,
            deadline_mono_ms=8200,
        )
    )
    assert len(runtime._mailbox) == NarrativeMailbox.ORDINARY_CELLS  # noqa: SLF001
    evict = runtime.admit(_event_impulse("diag:evict", revision=50, fanout=50))
    assert evict.reason == "mailbox_evicted_update"
    status = runtime.status()
    assert status.last_admission_reason == "mailbox_evicted_update"
    assert "mailbox_evicted_update" in status.admission_diagnostics
    assert status.mailbox_overflows >= 1
    # Freeze-registry actor/recovery codes projected for health/API (#284).
    assert "mailbox_evicted_update" in status.reason_codes
    assert "mailbox_overloaded" in status.reason_codes


def test_status_reason_codes_for_recovery_health_and_tape() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    assert runtime.status().reason_codes == ()

    latest = _pure_fact("reason:latest", revision=60, fanout=60)
    runtime.admit(
        NarrativeCommand.recovery(
            "reason:recovery",
            9000,
            latest_context=latest.context_part,
            loss_first_sequence=1,
            loss_last_sequence=2,
            safety_effects=(latest.safety_effect(),),
        )
    )
    recovered = runtime.reduce_next()
    assert recovered is not None
    status = runtime.status()
    assert status.history_complete is False
    assert "history_incomplete" in status.reason_codes
    assert "mailbox_history_incomplete" in status.reason_codes
    assert "mailbox_recovery" in status.reason_codes

    runtime.admit(
        NarrativeCommand.tape_health(
            "reason:tape",
            9010,
            recorder_generation=1,
            status="unavailable",
            affected_detector_ids=("battle",),
            first_lost_sequence=1,
            last_lost_sequence=1,
        )
    )
    runtime.reduce_next()
    status = runtime.status()
    assert "capture_unavailable" in status.reason_codes
    assert status.runtime_state == "degraded"

    runtime.admit(
        NarrativeCommand.component_health(
            "reason:llm",
            9020,
            component="llm",
            generation=1,
            status="unavailable",
            reason=None,
        )
    )
    runtime.reduce_next()
    status = runtime.status()
    assert "component_unavailable" in status.reason_codes


def test_status_reason_codes_include_deadline_admission_skipped() -> None:
    """deadline_admission_skipped is a freeze-registry mailbox/tape health code."""

    runtime = NarrativeRuntime()
    runtime.enable()
    # Saturate ordinary cells with distinct silence generations.
    for index in range(NarrativeMailbox.ORDINARY_CELLS):
        admitted = runtime.admit(
            NarrativeCommand.deadline(
                f"skip:fill:{index}",
                "LONG_SILENCE_ELAPSED",
                9000 + index,
                generation=1 + index,
                deadline_mono_ms=9000 + index,
            )
        )
        assert admitted.accepted
    # Validity deadline is skipped (not protected) when ordinary partition is full.
    skipped = runtime.admit(
        NarrativeCommand.deadline(
            "skip:validity",
            "VALIDITY_DEADLINE_ELAPSED",
            9500,
            generation=1,
            deadline_mono_ms=9500,
        )
    )
    assert skipped.reason == "deadline_admission_skipped"
    status = runtime.status()
    assert "deadline_admission_skipped" in status.reason_codes
    assert status.last_admission_reason == "deadline_admission_skipped"


@pytest.mark.asyncio
async def test_silence_and_validity_deadline_timers_admit_commands_only() -> None:
    runtime = NarrativeRuntime(
        silence_deadline_delay_s=0.02,
        validity_deadline_delay_s=0.02,
    )
    runtime.enable()
    runtime.admit(
        NarrativeCommand.config_update(
            "deadline:arm", 9000, valid=False, ledger=None, diagnostics=()
        )
    )
    armed = runtime.reduce_next()
    assert armed is not None
    assert "effect:arm_silence_deadline" in armed.effects
    assert "effect:arm_validity_deadline" in armed.effects
    await runtime.apply_effects(armed.effects)
    assert runtime.silence_deadline_task_active()
    assert runtime.validity_deadline_task_active()

    await runtime.wait_deadline_timers_idle()
    assert not runtime.silence_deadline_task_active()
    assert not runtime.validity_deadline_task_active()

    first = runtime.reduce_next()
    second = runtime.reduce_next()
    assert first is not None and second is not None
    kinds = {first.kind, second.kind}
    assert kinds == {"LONG_SILENCE_ELAPSED", "VALIDITY_DEADLINE_ELAPSED"}
    assert first.disposition == "handled"
    assert second.disposition == "handled"
    assert runtime.mailbox_empty()


@pytest.mark.asyncio
async def test_deadline_timer_cancel_drops_stale_generation() -> None:
    runtime = NarrativeRuntime(
        silence_deadline_delay_s=0.05,
        validity_deadline_delay_s=3600.0,
    )
    runtime.enable()
    runtime.admit(
        NarrativeCommand.config_update(
            "deadline:first", 9100, valid=False, ledger=None, diagnostics=()
        )
    )
    first = runtime.reduce_next()
    assert first is not None
    await runtime.apply_effects(first.effects)
    assert runtime.silence_deadline_task_active()
    first_generation = runtime._silence_generation  # noqa: SLF001

    runtime.admit(
        NarrativeCommand.config_update(
            "deadline:rearm", 9110, valid=False, ledger=None, diagnostics=()
        )
    )
    rearmed = runtime.reduce_next()
    assert rearmed is not None
    assert "effect:cancel_silence_deadline" in rearmed.effects
    assert "effect:arm_silence_deadline" in rearmed.effects
    await runtime.apply_effects(rearmed.effects)
    assert runtime.silence_deadline_task_active()
    assert runtime._silence_generation == first_generation + 1  # noqa: SLF001

    for _ in range(50):
        if not runtime.silence_deadline_task_active():
            break
        await asyncio.sleep(0.01)
    assert not runtime.silence_deadline_task_active()
    elapsed = runtime.reduce_next()
    assert elapsed is not None
    assert elapsed.kind == "LONG_SILENCE_ELAPSED"
    assert elapsed.disposition == "handled"
    # Cancelled first generation must not leave a second silence command.
    assert runtime.reduce_next() is None
    await runtime.apply_effects(("effect:cancel_validity_deadline",))


@pytest.mark.asyncio
async def test_run_loop_fires_silence_deadline_when_idle() -> None:
    runtime = NarrativeRuntime(silence_deadline_delay_s=0.02, validity_deadline_delay_s=3600.0)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.config_update(
            "run:deadline", 9200, valid=False, ledger=None, diagnostics=()
        )
    )

    task = asyncio.create_task(runtime.run())
    for _ in range(100):
        if runtime.status().lane == "building" and runtime.status().reducer_sequence >= 2:
            break
        await asyncio.sleep(0.01)
    assert runtime.status().lane == "building"
    assert runtime.status().reducer_sequence >= 2
    runtime.admit(NarrativeCommand.shutdown("run:deadline-stop", 9300, "application_exit"))
    await asyncio.wait_for(task, timeout=2.0)
    assert runtime.status().runtime_state == "stopped"


def test_recovery_diagnostics_project_loss_range_and_counts() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    status = runtime.status()
    assert status.recovery_count == 0
    assert status.last_recovery_loss_first is None
    assert status.last_recovery_loss_last is None
    assert status.last_recovery_safety_effect_count == 0
    assert status.last_recovery_cancelled_lane is None

    first = _pure_fact("recovery:ctx:1", revision=10, fanout=10)
    runtime.admit(
        NarrativeCommand.recovery(
            "recovery:diag:1",
            9400,
            latest_context=first.context_part,
            loss_first_sequence=3,
            loss_last_sequence=7,
            safety_effects=(first.safety_effect(),),
        )
    )
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert reduced.disposition == "handled"
    status = runtime.status()
    assert status.history_complete is False
    assert status.recovery_count == 1
    assert status.last_recovery_loss_first == 3
    assert status.last_recovery_loss_last == 7
    assert status.last_recovery_safety_effect_count == 1
    assert status.last_recovery_cancelled_lane is None
    assert status.timeline_revision == 10
    assert "mailbox_recovery" in status.reason_codes

    second = _pure_fact("recovery:ctx:2", revision=12, fanout=12)
    effect_a = second.safety_effect()
    effect_b = {
        **effect_a,
        "identity": "recovery:extra",
        "payloadHash": "sha256:" + "a" * 64,
    }
    runtime.admit(
        NarrativeCommand.recovery(
            "recovery:diag:2",
            9410,
            latest_context=second.context_part,
            loss_first_sequence=8,
            loss_last_sequence=11,
            safety_effects=(effect_a, effect_b),
        )
    )
    runtime.reduce_next()
    status = runtime.status()
    assert status.recovery_count == 2
    assert status.last_recovery_loss_first == 8
    assert status.last_recovery_loss_last == 11
    assert status.last_recovery_safety_effect_count == 2
    assert status.timeline_revision == 12


def test_recovery_diagnostics_record_cancelled_building_lane() -> None:
    runtime = _drive_to("building")
    assert runtime.status().lane == "building"
    latest = _pure_fact("recovery:cancel:ctx", revision=20, fanout=20)
    runtime.admit(
        NarrativeCommand.recovery(
            "recovery:cancel:building",
            9500,
            latest_context=latest.context_part,
            loss_first_sequence=1,
            loss_last_sequence=4,
            safety_effects=(latest.safety_effect(),),
        )
    )
    result = runtime.reduce_next()
    assert result is not None
    assert "building_cancelled" in result.effects
    assert result.lane_after == "idle"
    status = runtime.status()
    assert status.recovery_count == 1
    assert status.last_recovery_cancelled_lane == "building"
    assert status.last_recovery_loss_first == 1
    assert status.last_recovery_loss_last == 4


def test_recovery_diagnostics_record_cancelled_speech_lane() -> None:
    runtime = _drive_to("committed")
    assert runtime.status().lane == "committed"
    latest = _pure_fact("recovery:speech:ctx", revision=21, fanout=21)
    runtime.admit(
        NarrativeCommand.recovery(
            "recovery:cancel:speech",
            9510,
            latest_context=latest.context_part,
            loss_first_sequence=5,
            loss_last_sequence=6,
            safety_effects=(latest.safety_effect(),),
        )
    )
    result = runtime.reduce_next()
    assert result is not None
    assert result.lane_after == "stopping"
    status = runtime.status()
    assert status.recovery_count == 1
    assert status.last_recovery_cancelled_lane == "committed"


@pytest.mark.asyncio
async def test_realization_deadline_timer_admits_matching_token() -> None:
    runtime = NarrativeRuntime(realization_deadline_delay_s=0.02)
    runtime.enable()
    runtime.admit(_event_impulse("rz-deadline:plan", revision=30, fanout=30))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "effect:dispatch_realization" in planned.effects
    assert "effect:arm_realization_deadline" in planned.effects
    token = runtime.current_realization_token()
    assert token is not None
    await runtime.apply_effects(planned.effects)
    assert runtime.realization_deadline_task_active()

    await runtime.wait_deadline_timers_idle()
    assert not runtime.realization_deadline_task_active()
    elapsed = runtime.reduce_next()
    assert elapsed is not None
    assert elapsed.kind == "REALIZATION_DEADLINE_ELAPSED"
    assert elapsed.disposition == "handled"
    assert elapsed.lane_after == "idle"
    assert runtime.current_realization_token() is None
    assert runtime.mailbox_empty()


@pytest.mark.asyncio
async def test_realization_success_cancels_deadline_before_stale_fire() -> None:
    runtime = NarrativeRuntime(realization_deadline_delay_s=0.05)
    runtime.enable()
    runtime.admit(_event_impulse("rz-deadline:cancel", revision=31, fanout=31))
    planned = runtime.reduce_next()
    assert planned is not None
    await runtime.apply_effects(planned.effects)
    assert runtime.realization_deadline_task_active()
    token = runtime.current_realization_token()
    assert token is not None

    runtime.admit(
        NarrativeCommand.realization_result(
            "rz-deadline:ok",
            "REALIZATION_SUCCEEDED",
            9600,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert "effect:cancel_realization_deadline" in committed.effects
    assert "effect:dispatch_tts" in committed.effects
    assert "effect:arm_speech_deadline" in committed.effects
    await runtime.apply_effects(committed.effects)
    assert not runtime.realization_deadline_task_active()
    assert runtime.speech_deadline_task_active()

    for _ in range(20):
        if not runtime.realization_deadline_task_active():
            break
        await asyncio.sleep(0.01)
    kinds: list[str] = []
    while True:
        nxt = runtime.reduce_next()
        if nxt is None:
            break
        kinds.append(nxt.kind)
        await runtime.apply_effects(nxt.effects)
    assert "REALIZATION_DEADLINE_ELAPSED" not in kinds
    await runtime.apply_effects(("effect:cancel_speech_deadline",))


@pytest.mark.asyncio
async def test_speech_deadline_stages_start_then_stop() -> None:
    runtime = NarrativeRuntime(speech_deadline_delay_s=0.02)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "speech-deadline:manual", 9700, text="Watchdog line.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert "effect:dispatch_tts" in committed.effects
    assert "effect:arm_speech_deadline" in committed.effects
    await runtime.apply_effects(committed.effects)
    assert runtime.speech_deadline_task_active()
    utterance = runtime.current_utterance_token()
    assert utterance is not None

    await runtime.wait_deadline_timers_idle()
    start_elapsed = runtime.reduce_next()
    assert start_elapsed is not None
    assert start_elapsed.kind == "SPEECH_DEADLINE_ELAPSED"
    assert start_elapsed.lane_after == "stopping"
    assert "effect:cancel_tts" in start_elapsed.effects
    assert "effect:cancel_speech_deadline" in start_elapsed.effects
    assert "effect:arm_speech_deadline" in start_elapsed.effects
    await runtime.apply_effects(start_elapsed.effects)
    assert runtime.speech_deadline_task_active()

    await runtime.wait_deadline_timers_idle()
    stop_elapsed = runtime.reduce_next()
    assert stop_elapsed is not None
    assert stop_elapsed.kind == "SPEECH_DEADLINE_ELAPSED"
    assert stop_elapsed.lane_after == "idle"
    assert runtime.current_utterance_token() is None
    await runtime.apply_effects(stop_elapsed.effects)
    assert not runtime.speech_deadline_task_active()
    status = runtime.status()
    assert status.speech_quarantined_generation == 1
    assert status.speech_quarantine_reason == "tts_start_timeout"
    assert status.component_health["tts"] == "unavailable"
    assert status.runtime_state == "degraded"
    assert "tts_backend_quarantined" in stop_elapsed.effects


@pytest.mark.asyncio
async def test_tts_quarantine_clears_only_when_health_generation_advances() -> None:
    """COMPONENT_HEALTH ready clears quarantine only when generation > quarantined."""
    runtime = NarrativeRuntime(speech_deadline_delay_s=0.02)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "tts-quarantine:manual", 9900, text="Quarantine line.", admission_ordinal=3
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    await runtime.apply_effects(committed.effects)
    await runtime.wait_deadline_timers_idle()
    start_elapsed = runtime.reduce_next()
    assert start_elapsed is not None
    await runtime.apply_effects(start_elapsed.effects)
    await runtime.wait_deadline_timers_idle()
    stop_elapsed = runtime.reduce_next()
    assert stop_elapsed is not None
    await runtime.apply_effects(stop_elapsed.effects)
    assert runtime.status().speech_quarantined_generation == 1

    runtime.admit(
        NarrativeCommand.component_health(
            "tts-quarantine:hold",
            9910,
            component="tts",
            generation=1,
            status="ready",
            reason=None,
        )
    )
    held = runtime.reduce_next()
    assert held is not None
    assert "tts_quarantine_held" in held.effects
    status = runtime.status()
    assert status.speech_quarantined_generation == 1
    assert status.component_health["tts"] == "unavailable"

    runtime.admit(
        NarrativeCommand.component_health(
            "tts-quarantine:clear",
            9920,
            component="tts",
            generation=2,
            status="ready",
            reason=None,
        )
    )
    cleared = runtime.reduce_next()
    assert cleared is not None
    assert "tts_quarantine_cleared" in cleared.effects
    status = runtime.status()
    assert status.speech_quarantined_generation is None
    assert status.component_health["tts"] == "ready"


@pytest.mark.asyncio
async def test_playback_accepted_rearms_speech_deadline_to_playback_stage() -> None:
    runtime = NarrativeRuntime(speech_deadline_delay_s=0.03)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "speech-deadline:pb", 9800, text="Playback line.", admission_ordinal=2
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    await runtime.apply_effects(committed.effects)
    assert runtime.speech_deadline_task_active()
    utterance = runtime.current_utterance_token()
    assert utterance is not None

    runtime.admit(
        _tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="speech-deadline:accept")
    )
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    assert "effect:cancel_speech_deadline" in accepted.effects
    assert "effect:arm_speech_deadline" in accepted.effects
    await runtime.apply_effects(accepted.effects)
    assert runtime.speech_deadline_task_active()

    await runtime.wait_deadline_timers_idle()
    playback_elapsed = runtime.reduce_next()
    assert playback_elapsed is not None
    assert playback_elapsed.kind == "SPEECH_DEADLINE_ELAPSED"
    assert playback_elapsed.lane_after == "stopping"
    await runtime.apply_effects(playback_elapsed.effects)
    await runtime.apply_effects(("effect:cancel_speech_deadline",))


def test_freshness_gate_absent_keeps_legacy_commit_path() -> None:
    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "fresh:legacy",
            "REALIZATION_SUCCEEDED",
            9900,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert "effect:dispatch_tts" in committed.effects
    assert "realization_freshness_rejected" not in committed.effects


def test_freshness_gate_current_allows_tts_dispatch() -> None:
    gate = FreshnessGate()
    token, world = _minimal_commit_pair()
    runtime = NarrativeRuntime(
        freshness_gate=gate,
        commit_world_provider=lambda: world,
    )
    runtime.enable()
    runtime.admit(_event_impulse("fresh:pass", revision=40, fanout=40))
    planned = runtime.reduce_next()
    assert planned is not None
    # Runtime-owned commit token is armed with the plan; tests may override via seed.
    runtime.seed_commit_token_for_test(token)
    rz = runtime.current_realization_token()
    assert rz is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "fresh:pass:ok",
            "REALIZATION_SUCCEEDED",
            9910,
            request_id=str(rz["requestId"]),
            request_ordinal=int(rz["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(rz["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(rz),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert "realization_committed" in committed.effects
    assert "effect:dispatch_tts" in committed.effects
    assert "freshness_verdict:current" in committed.effects
    assert gate.evaluate_count == 1
    assert gate.pass_count == 1


def test_freshness_gate_stale_rejects_without_tts() -> None:
    gate = FreshnessGate()
    token, world = _minimal_commit_pair(episode_revision=1, world_episode_revision=99)
    runtime = NarrativeRuntime(
        freshness_gate=gate,
        commit_world_provider=lambda: world,
    )
    runtime.enable()
    runtime.admit(_event_impulse("fresh:stale", revision=41, fanout=41))
    planned = runtime.reduce_next()
    assert planned is not None
    runtime.seed_commit_token_for_test(token)
    rz = runtime.current_realization_token()
    assert rz is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "fresh:stale:ok",
            "REALIZATION_SUCCEEDED",
            9920,
            request_id=str(rz["requestId"]),
            request_ordinal=int(rz["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(rz["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(rz),
        )
    )
    rejected = runtime.reduce_next()
    assert rejected is not None
    assert rejected.lane_after == "idle"
    assert "realization_freshness_rejected" in rejected.effects
    assert "freshness_verdict:freshness_stale" in rejected.effects
    assert "freshness_evidence:episode_revision" in rejected.effects
    assert "effect:dispatch_tts" not in rejected.effects
    assert "effect:cancel_realization_deadline" in rejected.effects
    assert runtime.current_realization_token() is None
    assert runtime.current_utterance_token() is None
    assert gate.fail_count == 1


def test_semantic_verifier_accepts_then_dispatches_tts() -> None:
    """#270/#284: after freshness, accepted verification still reaches TTS."""
    gate = FreshnessGate()
    token, world = _minimal_commit_pair()
    runtime = NarrativeRuntime(
        freshness_gate=gate,
        commit_world_provider=lambda: world,
        semantic_verifier=SemanticVerifier(),
    )
    runtime.enable()
    runtime.admit(_event_impulse("verify:pass", revision=50, fanout=50))
    planned = runtime.reduce_next()
    assert planned is not None
    runtime.seed_commit_token_for_test(token)
    runtime.seed_semantic_frame_for_test(
        family="battle.closing",
        subject_surface="Alex",
        required_claim_surface="is closing on Morgan",
        actor_bindings=(
            ("hero", ("Alex", "the driver")),
            ("car:22", ("Morgan", "the car ahead")),
        ),
        required_actors=frozenset({"hero", "car:22"}),
    )
    rz = runtime.current_realization_token()
    assert rz is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "verify:pass:ok",
            "REALIZATION_SUCCEEDED",
            10_200,
            request_id=str(rz["requestId"]),
            request_ordinal=int(rz["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(rz["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(rz, text="Alex is closing on Morgan."),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert "realization_committed" in committed.effects
    assert "effect:dispatch_tts" in committed.effects
    assert "semantic_verdict:accepted" in committed.effects


def test_semantic_verifier_rejects_without_tts() -> None:
    """#270/#284: failed verification blocks TTS after freshness passes."""
    gate = FreshnessGate()
    token, world = _minimal_commit_pair()
    runtime = NarrativeRuntime(
        freshness_gate=gate,
        commit_world_provider=lambda: world,
        semantic_verifier=SemanticVerifier(),
    )
    runtime.enable()
    runtime.admit(_event_impulse("verify:fail", revision=51, fanout=51))
    planned = runtime.reduce_next()
    assert planned is not None
    runtime.seed_commit_token_for_test(token)
    runtime.seed_semantic_frame_for_test(
        family="battle.closing",
        subject_surface="Alex",
        required_claim_surface="is closing on Morgan",
        actor_bindings=(
            ("hero", ("Alex", "the driver")),
            ("car:22", ("Morgan", "the car ahead")),
        ),
        required_actors=frozenset({"hero", "car:22"}),
    )
    rz = runtime.current_realization_token()
    assert rz is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "verify:fail:ok",
            "REALIZATION_SUCCEEDED",
            10_210,
            request_id=str(rz["requestId"]),
            request_ordinal=int(rz["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(rz["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(rz, text="I think Alex might be closing?"),
        )
    )
    rejected = runtime.reduce_next()
    assert rejected is not None
    assert rejected.lane_after == "idle"
    assert "realization_verify_rejected" in rejected.effects
    assert "effect:dispatch_tts" not in rejected.effects
    assert runtime.current_utterance_token() is None


def test_semantic_verifier_rejects_when_frame_missing() -> None:
    """#349: verifier without a frame rejects (fail-closed, no TTS)."""
    gate = FreshnessGate()
    token, world = _minimal_commit_pair()
    runtime = NarrativeRuntime(
        freshness_gate=gate,
        commit_world_provider=lambda: world,
        semantic_verifier=SemanticVerifier(),
    )
    runtime.enable()
    runtime.admit(_event_impulse("verify:skip", revision=52, fanout=52))
    planned = runtime.reduce_next()
    assert planned is not None
    runtime.seed_commit_token_for_test(token)
    rz = runtime.current_realization_token()
    assert rz is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "verify:skip:ok",
            "REALIZATION_SUCCEEDED",
            10_220,
            request_id=str(rz["requestId"]),
            request_ordinal=int(rz["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(rz["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(rz, text="Clear sentence."),
        )
    )
    rejected = runtime.reduce_next()
    assert rejected is not None
    assert rejected.lane_after == "idle"
    assert "realization_verify_rejected" in rejected.effects
    assert "semantic_verdict:rejected" in rejected.effects
    assert "semantic_reason:missing_verify_frame" in rejected.effects
    assert "effect:dispatch_tts" not in rejected.effects
    assert "semantic_verdict:skipped_no_frame" not in rejected.effects
    assert runtime.current_utterance_token() is None


def test_opportunity_queue_absent_keeps_legacy_dispatch() -> None:
    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "opp:legacy",
            "REALIZATION_SUCCEEDED",
            10_100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert "effect:dispatch_tts" in committed.effects
    assert not any(effect.startswith("opportunity_") for effect in committed.effects)


def test_opportunity_reserve_on_dispatch_release_on_realization_failed() -> None:
    queue = OpportunityQueue()
    admitted = queue.admit(_opportunity_intent())
    assert admitted.reason == "queued"
    runtime = NarrativeRuntime(opportunity_queue=queue)
    runtime.enable()
    runtime.seed_opportunity_for_test(
        opportunity_id="opp:1", beat_id="battle.pursuit", now_ms=10_000
    )
    runtime.admit(_event_impulse("opp:reserve", revision=50, fanout=50))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "plan_dispatched" in planned.effects
    assert "opportunity_reserved" in planned.effects
    assert "opportunity_step:reserved" in planned.effects
    live = queue.live_ids()
    assert "opp:1" in live
    # reservation held
    token = runtime.current_realization_token()
    assert token is not None
    assert runtime.reservation_token_for_test() == "res:opp:1"

    runtime.admit(
        NarrativeCommand.realization_result(
            "opp:fail",
            "REALIZATION_FAILED",
            10_200,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(
                token,
                outcome="failed",
                text=None,
                textHash=None,
                failureReason="realization_transport",
            ),
        )
    )
    failed = runtime.reduce_next()
    assert failed is not None
    assert failed.lane_after == "idle"
    assert "opportunity_attempt_released" in failed.effects
    assert "opportunity_step:attempt_released" in failed.effects
    assert runtime.reservation_token_for_test() is None


def test_opportunity_consume_on_playback_accepted() -> None:
    queue = OpportunityQueue()
    assert queue.admit(_opportunity_intent()).reason == "queued"
    runtime = NarrativeRuntime(opportunity_queue=queue)
    runtime.enable()
    runtime.seed_opportunity_for_test(
        opportunity_id="opp:1", beat_id="battle.pursuit", now_ms=10_000
    )
    runtime.admit(_event_impulse("opp:consume", revision=51, fanout=51))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "opportunity_reserved" in planned.effects
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "opp:ok",
            "REALIZATION_SUCCEEDED",
            10_300,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="opp:pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    assert "opportunity_consumed" in accepted.effects
    assert "opportunity_step:consumed" in accepted.effects
    assert runtime.reservation_token_for_test() is None
    assert queue.live_ids() == ()


def test_episode_registry_absent_keeps_legacy_dispatch() -> None:
    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "ep:legacy",
            "REALIZATION_SUCCEEDED",
            11_100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert "effect:dispatch_tts" in committed.effects
    assert not any(effect.startswith("episode_") for effect in committed.effects)


def test_episode_open_activate_on_dispatch_invalidate_on_realization_failed() -> None:
    registry = EpisodeRegistry()
    runtime = NarrativeRuntime(episode_registry=registry)
    runtime.enable()
    runtime.seed_episode_for_test(
        intent=_episode_intent(now_ms=10_000),
        beat_id="battle.pursuit",
        now_ms=10_000,
    )
    runtime.admit(_event_impulse("ep:open", revision=60, fanout=60))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "plan_dispatched" in planned.effects
    assert "episode_opened" in planned.effects
    assert "episode_activated" in planned.effects
    assert "episode_step:opened" in planned.effects
    assert "episode_step:activated" in planned.effects
    episode_id = runtime.episode_id_for_test()
    assert episode_id is not None
    episode = registry.get(episode_id)
    assert episode is not None
    assert episode.state == "active"

    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "ep:fail",
            "REALIZATION_FAILED",
            11_200,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(
                token,
                outcome="failed",
                text=None,
                textHash=None,
                failureReason="realization_transport",
            ),
        )
    )
    failed = runtime.reduce_next()
    assert failed is not None
    assert failed.lane_after == "idle"
    assert "episode_invalidated" in failed.effects
    assert "episode_step:evidence_invalidated" in failed.effects
    assert runtime.episode_id_for_test() is None
    terminal = registry.get(episode_id)
    assert terminal is not None
    assert terminal.state == "invalidated"
    assert terminal.resolution_reason == "evidence_invalidated"


def test_episode_mark_spoken_and_resolve_on_speech_completed() -> None:
    registry = EpisodeRegistry()
    runtime = NarrativeRuntime(episode_registry=registry)
    runtime.enable()
    runtime.seed_episode_for_test(
        intent=_episode_intent(now_ms=10_000),
        beat_id="battle.pursuit",
        now_ms=10_000,
    )
    runtime.admit(_event_impulse("ep:speak", revision=61, fanout=61))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "episode_activated" in planned.effects
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "ep:ok",
            "REALIZATION_SUCCEEDED",
            11_300,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    episode_id = runtime.episode_id_for_test()
    assert episode_id is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="ep:pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    assert "episode_spoken" in accepted.effects
    assert "episode_step:spoken_beat" in accepted.effects
    spoken = registry.get(episode_id)
    assert spoken is not None
    assert spoken.last_spoken_beat_id == "battle.pursuit"

    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="ep:done"))
    done = runtime.reduce_next()
    assert done is not None
    assert done.lane_after == "idle"
    assert "episode_resolved" in done.effects
    assert "episode_step:natural_exit" in done.effects
    assert runtime.episode_id_for_test() is None
    resolved = registry.get(episode_id)
    assert resolved is not None
    assert resolved.state == "resolved"
    assert resolved.resolution_reason == "natural_exit"


def test_exposure_recorded_on_playback_accepted_as_sole_writer() -> None:
    registry = EpisodeRegistry()
    store = ExposureStore()
    runtime = NarrativeRuntime(episode_registry=registry, exposure_store=store)
    runtime.enable()
    runtime.seed_episode_for_test(
        intent=_episode_intent(now_ms=10_000),
        beat_id="battle.pursuit",
        now_ms=10_000,
    )
    runtime.admit(_event_impulse("exp:speak", revision=62, fanout=62))
    planned = runtime.reduce_next()
    assert planned is not None
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "exp:ok",
            "REALIZATION_SUCCEEDED",
            11_400,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert store.size == 0
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="exp:pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    assert "exposure_recorded" in accepted.effects
    assert "exposure_step:recorded" in accepted.effects
    assert store.size == 1
    episode_id = runtime.episode_id_for_test()
    assert episode_id is not None
    episode = registry.get(episode_id)
    assert episode is not None
    view = store.query(
        semantic_identity=tuple(episode.semantic_identity),
        pattern="battle.pursuit:tight:1",
        text=str(utterance["text"]),
        tape_channel="race.battle.closing",
        policy_id="live_story",
        now_ms=11_400,
    )
    assert view.semantic_fatigue > 0.0
    assert view.pattern_fatigue > 0.0
    assert view.channel_pressure > 0.0


def test_manual_playback_does_not_record_exposure() -> None:
    store = ExposureStore()
    runtime = NarrativeRuntime(exposure_store=store)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "exp:manual", 12_000, text="Manual line.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="exp:manual-pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    assert "exposure_recorded" not in accepted.effects
    assert store.size == 0


def test_exposure_store_absent_keeps_legacy_playback() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(_event_impulse("exp:legacy", revision=63, fanout=63))
    planned = runtime.reduce_next()
    assert planned is not None
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "exp:legacy-ok",
            "REALIZATION_SUCCEEDED",
            11_500,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="exp:legacy-pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    assert not any(effect.startswith("exposure_") for effect in accepted.effects)


def test_story_director_absent_keeps_legacy_dispatch() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(_event_impulse("dir:legacy", revision=70, fanout=70))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "plan_dispatched" in planned.effects
    assert "effect:dispatch_realization" in planned.effects
    assert not any(
        effect.startswith("director_") and effect != "director_skipped_pure_fact"
        for effect in planned.effects
    )


def test_story_director_selects_and_dispatches_plan() -> None:
    director = StoryDirector()
    runtime = NarrativeRuntime(story_director=director)
    runtime.enable()
    runtime.seed_director_for_test(world=_director_world(), candidates=(_director_cand(),))
    runtime.admit(_event_impulse("dir:select", revision=71, fanout=71))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_evaluated" in planned.effects
    assert "director_selected" in planned.effects
    assert "director_step:active_story_continuation" in planned.effects
    assert "plan_dispatched" in planned.effects
    assert "effect:dispatch_realization" in planned.effects
    assert planned.lane_after == "building"
    assert runtime.director_selected_beat_for_test() == "battle.approach"


def test_story_director_silence_skips_dispatch() -> None:
    director = StoryDirector()
    runtime = NarrativeRuntime(story_director=director)
    runtime.enable()
    runtime.seed_director_for_test(
        world=_director_world(lane="building", impulse="timer"),
        candidates=(_director_cand(),),
    )
    runtime.admit(_event_impulse("dir:silence", revision=72, fanout=72))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_evaluated" in planned.effects
    assert "director_silenced" in planned.effects
    assert "director_step:incumbent_held" in planned.effects
    assert "plan_dispatched" not in planned.effects
    assert "effect:dispatch_realization" not in planned.effects
    assert planned.lane_after == "idle"
    assert runtime.director_selected_beat_for_test() is None
    assert runtime.current_realization_token() is None


def test_story_director_notes_failure_on_realization_failed() -> None:
    director = StoryDirector()
    runtime = NarrativeRuntime(story_director=director)
    runtime.enable()
    runtime.seed_director_for_test(world=_director_world(), candidates=(_director_cand(),))
    runtime.admit(_event_impulse("dir:fail", revision=73, fanout=73))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_selected" in planned.effects
    token = runtime.current_realization_token()
    assert token is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "dir:fail-rz",
            "REALIZATION_FAILED",
            12_200,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(
                token,
                outcome="failed",
                text=None,
                textHash=None,
                failureReason="realization_transport",
            ),
        )
    )
    failed = runtime.reduce_next()
    assert failed is not None
    assert failed.lane_after == "idle"
    assert "director_failure_noted" in failed.effects
    assert runtime.director_selected_beat_for_test() is None

    runtime.seed_director_for_test(
        world=_director_world(),
        candidates=(
            _director_cand(
                beat_id="battle.pursuit",
                candidate_order=CandidateOrder(41, 4),
            ),
        ),
    )
    runtime.admit(_event_impulse("dir:fail-2", revision=74, fanout=74))
    second = runtime.reduce_next()
    assert second is not None
    assert "director_selected" in second.effects
    assert runtime.director_selected_beat_for_test() == "battle.pursuit"
    token2 = runtime.current_realization_token()
    assert token2 is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "dir:fail-rz-2",
            "REALIZATION_FAILED",
            12_300,
            request_id=str(token2["requestId"]),
            request_ordinal=int(token2["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token2["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(
                token2,
                outcome="failed",
                text=None,
                textHash=None,
                failureReason="realization_transport",
            ),
        )
    )
    failed2 = runtime.reduce_next()
    assert failed2 is not None
    assert "director_failure_noted" in failed2.effects

    # Runtime planning-cycle cap is already 2 after two dispatches; prove the
    # shared StoryDirector instance itself is exhausted for a further consult.
    exhausted = director.evaluate(_director_world(), (_director_cand(),))
    assert exhausted.speech == "silence"
    assert exhausted.reason == "planning_cycle_exhausted"


@pytest.mark.asyncio
async def test_manual_admission_latch_claim_and_abandon_race() -> None:
    from irswitch.events.narrative_manual_latch import ManualAdmissionLatch
    from irswitch.events.narrative_runtime import ManualSpeakOutcome

    latch = ManualAdmissionLatch()
    assert latch.claim_actor() is True
    assert latch.state == "actor_claimed"
    assert latch.abandon_caller() is False
    latch.resolve(
        ManualSpeakOutcome(kind="accepted", request_id="manual:1", admitted_state="committed")
    )
    assert (await latch.wait(0.01)) is not None

    abandoned = ManualAdmissionLatch()
    assert abandoned.abandon_caller() is True
    assert abandoned.claim_actor() is False


@pytest.mark.asyncio
async def test_try_manual_speak_admission_timeout_abandons_later_reduce() -> None:
    from irswitch.contracts.command import NarrativeCommand
    from irswitch.events.narrative_manual_latch import ManualAdmissionLatch
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    latch = ManualAdmissionLatch()
    runtime.register_manual_latch("manual:timeout", latch)
    admitted = runtime.admit(
        NarrativeCommand.manual_speak(
            "manual:timeout", 9000, text="Late admission.", admission_ordinal=1
        )
    )
    assert admitted.accepted
    assert await latch.wait(0.01) is None
    assert latch.abandon_caller() is True
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert reduced.disposition == "ignored_stale_or_inapplicable"
    assert runtime.status().lane == "idle"
    assert "manual_abandoned" in reduced.effects


@pytest.mark.asyncio
async def test_try_manual_speak_timeout_kwarg_returns_admission_timeout() -> None:
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    # Actor loop not running + reduce_inline=False leaves command queued → timeout.
    outcome = await runtime.try_manual_speak(
        "Will time out.",
        request_id="manual:to2",
        now_ms=9100,
        timeout_s=0.01,
        reduce_inline=False,
    )
    assert outcome.kind == "admission_timeout"
    # Later inline reduce must not speak.
    later = runtime.reduce_next()
    assert later is not None
    assert later.disposition == "ignored_stale_or_inapplicable"
    assert runtime.status().lane == "idle"


@pytest.mark.asyncio
async def test_shutdown_flushes_tape_effect() -> None:
    """#284: SHUTDOWN owns a cancellable tape flush effect before stop settles."""
    flushed: list[dict[str, object]] = []

    async def tape_flush(token: dict[str, object]) -> None:
        flushed.append(dict(token))
        await asyncio.sleep(0)

    runtime = NarrativeRuntime(tape_effect=tape_flush, shutdown_flush_timeout_s=1.0)
    runtime.enable()
    assert runtime.admit(NarrativeCommand.shutdown("tape:flush", 8000, "application_exit")).accepted
    shutdown = runtime.reduce_next()
    assert shutdown is not None
    assert "effect:flush_tape" in shutdown.effects
    await runtime.apply_effects(shutdown.effects)
    assert runtime.tape_task_active() or flushed  # may finish immediately
    await runtime.wait_effects_idle()
    assert flushed
    assert flushed[0]["reason"] == "shutdown"
    assert not runtime.tape_task_active()


@pytest.mark.asyncio
async def test_tape_flush_timeout_is_fail_soft() -> None:
    """#284: tape flush timeout admits degraded health and does not raise."""

    async def slow_flush(token: dict[str, object]) -> None:
        await asyncio.sleep(1.0)

    runtime = NarrativeRuntime(tape_effect=slow_flush, shutdown_flush_timeout_s=0.05)
    runtime.enable()
    runtime.admit(NarrativeCommand.shutdown("tape:timeout", 8100, "application_exit"))
    shutdown = runtime.reduce_next()
    assert shutdown is not None
    await runtime.apply_effects(shutdown.effects)
    await runtime.wait_effects_idle()
    # Ingress is closed by SHUTDOWN, so timeout reports via local tape_status.
    assert runtime.status().tape_status == "degraded"


@pytest.mark.asyncio
async def test_cancel_tape_flush_effect() -> None:
    """#284: effect:cancel_tape drops an in-flight flush without crashing."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_flush(token: dict[str, object]) -> None:
        started.set()
        await release.wait()

    runtime = NarrativeRuntime(tape_effect=blocked_flush, shutdown_flush_timeout_s=5.0)
    runtime.enable()
    runtime.admit(NarrativeCommand.shutdown("tape:cancel", 8200, "application_exit"))
    shutdown = runtime.reduce_next()
    assert shutdown is not None
    await runtime.apply_effects(shutdown.effects)
    await started.wait()
    assert runtime.tape_task_active()
    await runtime.apply_effects(["effect:cancel_tape"])
    assert not runtime.tape_task_active()


def test_event_replacement_opens_new_planning_cycle() -> None:
    """#284: accepted event while building closes replaced_precommit and bumps cycle."""
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(_event_impulse("rep:1", revision=10, fanout=10))
    first = runtime.reduce_next()
    assert first is not None
    assert first.planning_cycle_id == 1
    assert first.lane_after == "building"

    runtime.admit(_event_impulse("rep:2", revision=11, fanout=11))
    second = runtime.reduce_next()
    assert second is not None
    assert "replaced_precommit" in second.effects
    assert "planning_cycle_opened:event_replacement" in second.effects
    assert second.planning_cycle_id == 2
    assert second.plans_dispatched == 1
    assert second.lane_after == "building"


def test_manual_speak_never_opens_planning_cycle() -> None:
    """#284: manual terminal never opens a planning cycle."""
    runtime = NarrativeRuntime()
    runtime.enable()
    before = runtime.status().planning_cycle_id
    runtime.admit(
        NarrativeCommand.manual_speak(
            "manual:cycle", 5000, text="Manual line.", admission_ordinal=1
        )
    )
    result = runtime.reduce_next()
    assert result is not None
    assert result.planning_cycle_id == before
    assert not any(effect.startswith("planning_cycle_opened:") for effect in result.effects)


def _timeline_run(
    *,
    revision: int,
    stream_epoch: int,
    narrative_run_active: bool,
    transition_reasons: list[str] | None = None,
) -> dict:
    timeline = _timeline(revision=revision, transition_reasons=transition_reasons)
    timeline["streamEpoch"] = stream_epoch
    timeline["narrativeRunActive"] = narrative_run_active
    return timeline


def _fact_view_for_timeline(timeline: dict, *, count: int = 1) -> dict:
    """FactView aligned to timeline identity + a stable revision offset."""

    revision = int(timeline["timelineRevision"]) + 6
    stream_epoch = int(timeline["streamEpoch"])
    view = _fact_view(count, revision=revision)
    view["streamEpoch"] = stream_epoch
    for fact in view["facts"]:
        fact["streamEpoch"] = stream_epoch
    return view


def _context_with_timeline(
    command_id: str,
    timeline: dict,
    *,
    fanout: int,
    with_event: bool = False,
) -> NarrativeCommand:
    fact_view = _fact_view_for_timeline(timeline)
    events = ()
    if with_event:
        event = _event(0, fanout=fanout, fact_revision=int(fact_view["viewRevision"]))
        # NarrativeEvent is frozen; rebuild with matching streamEpoch.
        payload = event.to_dict()
        payload["streamEpoch"] = int(timeline["streamEpoch"])
        events = (NarrativeEvent.from_dict(payload),)
    part = partition_context_batches(
        timeline=timeline,
        fact_view=fact_view,
        events=events,
        fanout_stream_sequence=fanout,
    )[0]
    return NarrativeCommand.context_batch(command_id, 1000, part)


def test_disable_closes_run_and_reenable_allocates_stream_epoch() -> None:
    """#284: disable closes narrative run; re-enable under same broadcast allocates streamEpoch."""
    runtime = NarrativeRuntime()
    runtime.enable()

    runtime.admit(
        _context_with_timeline(
            "run:open",
            _timeline_run(revision=20, stream_epoch=1, narrative_run_active=True),
            fanout=20,
            with_event=True,
        )
    )
    opened = runtime.reduce_next()
    assert opened is not None
    assert runtime.status().narrative_run_active is True
    assert runtime.status().stream_epoch == 1
    assert opened.lane_after == "building"

    runtime.admit(
        _context_with_timeline(
            "run:disable",
            _timeline_run(
                revision=21,
                stream_epoch=1,
                narrative_run_active=False,
                transition_reasons=["narrative_disabled"],
            ),
            fanout=21,
        )
    )
    disabled = runtime.reduce_next()
    assert disabled is not None
    assert "narrative_run_closed" in disabled.effects
    assert "building_cancelled_on_disable" in disabled.effects
    assert runtime.status().narrative_run_active is False
    assert runtime.status().stream_epoch == 1
    assert runtime.status().lane == "idle"

    runtime.admit(
        _context_with_timeline(
            "run:enable",
            _timeline_run(
                revision=22,
                stream_epoch=2,
                narrative_run_active=True,
                transition_reasons=["narrative_enabled"],
            ),
            fanout=22,
            with_event=True,
        )
    )
    enabled = runtime.reduce_next()
    assert enabled is not None
    assert "narrative_run_opened" in enabled.effects
    assert "stream_epoch_allocated:2" in enabled.effects
    assert runtime.status().narrative_run_active is True
    assert runtime.status().stream_epoch == 2


def test_timeline_transition_cancels_building_and_stale_deadline_generations() -> None:
    """#284: occurrence/stream transition cancels building and bumps deadline gens."""

    runtime = _drive_to("building")
    stale_silence_generation = runtime._silence_generation  # noqa: SLF001
    stale_validity_generation = runtime._validity_generation  # noqa: SLF001
    runtime.admit(
        _context_with_timeline(
            "transition:restart",
            _timeline_run(
                revision=99,
                stream_epoch=1,
                narrative_run_active=True,
                transition_reasons=["session_restarted"],
            ),
            fanout=99,
        )
    )
    result = runtime.reduce_next()
    assert result is not None
    assert result.lane_after == "idle"
    assert "building_cancelled" in result.effects
    assert "effect:cancel_realization" in result.effects
    assert "effect:cancel_realization_deadline" in result.effects
    assert "effect:cancel_silence_deadline" in result.effects
    assert "effect:cancel_validity_deadline" in result.effects
    assert "effect:arm_silence_deadline" in result.effects
    assert "effect:arm_validity_deadline" in result.effects
    assert "narrative_run_closed" not in result.effects
    assert runtime._silence_generation == stale_silence_generation + 1  # noqa: SLF001
    assert runtime._validity_generation == stale_validity_generation + 1  # noqa: SLF001

    runtime.admit(
        NarrativeCommand.deadline(
            "transition:stale-silence",
            "LONG_SILENCE_ELAPSED",
            12_000,
            generation=stale_silence_generation,
            deadline_mono_ms=12_000,
        )
    )
    stale_silence = runtime.reduce_next()
    assert stale_silence is not None
    assert stale_silence.disposition == "ignored_stale_or_inapplicable"
    assert "stale_silence_generation" in stale_silence.effects

    runtime.admit(
        NarrativeCommand.deadline(
            "transition:stale-validity",
            "VALIDITY_DEADLINE_ELAPSED",
            12_010,
            generation=stale_validity_generation,
            deadline_mono_ms=12_010,
        )
    )
    stale_validity = runtime.reduce_next()
    assert stale_validity is not None
    assert stale_validity.disposition == "ignored_stale_or_inapplicable"
    assert "stale_validity_generation" in stale_validity.effects


@pytest.mark.asyncio
async def test_disable_with_tape_effect_flushes_tape() -> None:
    """#284: explicit disable cancels building and flushes owned tape_effect."""

    flushed: list[dict[str, object]] = []

    async def tape_flush(token: dict[str, object]) -> None:
        flushed.append(dict(token))
        await asyncio.sleep(0)

    runtime = NarrativeRuntime(tape_effect=tape_flush, shutdown_flush_timeout_s=1.0)
    runtime.enable()
    runtime.admit(
        _context_with_timeline(
            "tape:open",
            _timeline_run(revision=30, stream_epoch=1, narrative_run_active=True),
            fanout=30,
            with_event=True,
        )
    )
    opened = runtime.reduce_next()
    assert opened is not None
    assert opened.lane_after == "building"

    runtime.admit(
        _context_with_timeline(
            "tape:disable",
            _timeline_run(
                revision=31,
                stream_epoch=1,
                narrative_run_active=False,
                transition_reasons=["narrative_disabled"],
            ),
            fanout=31,
        )
    )
    disabled = runtime.reduce_next()
    assert disabled is not None
    assert "narrative_run_closed" in disabled.effects
    assert "building_cancelled_on_disable" in disabled.effects
    assert "effect:cancel_realization" in disabled.effects
    assert "effect:flush_tape" in disabled.effects
    assert "effect:cancel_silence_deadline" in disabled.effects
    assert "effect:cancel_validity_deadline" in disabled.effects
    assert runtime.status().lane == "idle"
    assert runtime.status().narrative_run_active is False

    await runtime.apply_effects(disabled.effects)
    await runtime.wait_effects_idle()
    assert flushed
    assert not runtime.tape_task_active()


def test_config_then_timeline_transition_cancels_building() -> None:
    """#284: config boundary rearms deadlines; following transition cancels building."""

    runtime = _drive_to("building")
    runtime.admit(
        NarrativeCommand.config_update(
            "config:boundary", 14_000, valid=False, ledger=None, diagnostics=()
        )
    )
    config = runtime.reduce_next()
    assert config is not None
    assert config.lane_after == "building"
    assert "effect:cancel_realization" not in config.effects
    assert "effect:cancel_silence_deadline" in config.effects
    assert "effect:arm_silence_deadline" in config.effects
    assert "effect:cancel_validity_deadline" in config.effects
    assert "effect:arm_validity_deadline" in config.effects

    runtime.admit(
        _context_with_timeline(
            "config:follow-transition",
            _timeline_run(
                revision=101,
                stream_epoch=1,
                narrative_run_active=True,
                transition_reasons=["session_restarted"],
            ),
            fanout=101,
        )
    )
    follow = runtime.reduce_next()
    assert follow is not None
    assert follow.lane_after == "idle"
    assert "building_cancelled" in follow.effects
    assert "effect:cancel_realization" in follow.effects
    assert runtime.status().lane == "idle"


def test_fact_only_wait_cancels_building_without_replan() -> None:
    """Pure FactView cancels building and waits; it never opens a plan."""

    runtime = _drive_to("building")
    before_cycle = runtime.status().planning_cycle_id
    runtime.admit(_pure_fact("fact:wait", revision=50, fanout=50))
    result = runtime.reduce_next()
    assert result is not None
    assert result.lane_after == "idle"
    assert "director_skipped_pure_fact" in result.effects
    assert "fact_only_wait" in result.effects
    assert "building_invalidated" in result.effects
    assert not any(effect.startswith("plan_dispatched") for effect in result.effects)
    assert not any(effect.startswith("planning_cycle_opened:") for effect in result.effects)
    assert runtime.status().planning_cycle_id == before_cycle


def test_narrative_callback_branch_rearms_silence_and_allows_director() -> None:
    runtime = _drive_to("speaking")
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="cb:narrative:done"))
    done = runtime.reduce_next()
    assert done is not None
    assert done.lane_after == "idle"
    assert "director_reentry_eligible" in done.effects
    assert "narrative_callback_branch" in done.effects
    assert "silence_deadline_rearmed" in done.effects
    assert "manual_callback_branch" not in done.effects


def test_manual_callback_branch_rearms_silence_without_director() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "cb:manual", 13_000, text="Manual check.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="cb:manual:pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert "manual_playback_accepted" in accepted.effects
    assert "silence_deadline_paused" in accepted.effects
    assert "narrative_playback_accepted" not in accepted.effects
    assert "exposure_recorded" not in accepted.effects
    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="cb:manual:done"))
    done = runtime.reduce_next()
    assert done is not None
    assert done.lane_after == "idle"
    assert "manual_callback_branch" in done.effects
    assert "silence_deadline_rearmed" in done.effects
    assert "director_reentry_eligible" not in done.effects
    assert "narrative_callback_branch" not in done.effects


@pytest.mark.asyncio
async def test_live_authored_verify_frame_attached_and_accepted() -> None:
    """#284: authored realization_effect stashes a #270 frame; verifier accepts."""

    from irswitch.events.narrative_realization_bridge import (
        SpeechDraftCache,
        build_realization_effect,
    )
    from irswitch.events.narrative_verify_frame import _LIVE_VERIFY_FRAMES

    _LIVE_VERIFY_FRAMES.clear()
    effect = build_realization_effect(SpeechDraftCache(), prefer_authored=True)
    runtime = NarrativeRuntime(
        realization_effect=effect,
        semantic_verifier=SemanticVerifier(),
    )
    runtime.enable()
    runtime.admit(_event_impulse("live:authored-vf", revision=90, fanout=90))
    planned = runtime.reduce_next()
    assert planned is not None
    assert runtime.current_realization_token() is not None
    runtime._realization = {
        **runtime._realization,
        "beatId": "battle.side_by_side",
    }
    await runtime.apply_effects(planned.effects)
    await runtime.wait_effects_idle()
    committed = None
    for _ in range(8):
        reduced = runtime.reduce_next()
        if reduced is None:
            await asyncio.sleep(0.01)
            continue
        await runtime.apply_effects(reduced.effects)
        await runtime.wait_effects_idle()
        if "realization_committed" in reduced.effects:
            committed = reduced
            break
    assert committed is not None
    assert "verify_frame_attached_live" in committed.effects
    assert "semantic_verdict:accepted" in committed.effects
    assert "semantic_verdict:skipped_no_frame" not in committed.effects
    assert "effect:dispatch_tts" in committed.effects


@pytest.mark.asyncio
async def test_live_template_verify_frame_attached_from_draft_cache() -> None:
    """#284: template draft cache carries a verify frame into realization_effect."""

    from irswitch.events.narrative_realization_bridge import (
        SpeechDraft,
        SpeechDraftCache,
        build_realization_effect,
        template_speech,
    )
    from irswitch.events.narrative_verify_frame import _LIVE_VERIFY_FRAMES

    _LIVE_VERIFY_FRAMES.clear()
    cache = SpeechDraftCache()
    text, frame = template_speech("SECTOR_BEST", subject="Alex")
    cache._drafts.append(
        SpeechDraft(text=text, beat_id=None, source="template", verify_frame=frame)
    )
    effect = build_realization_effect(cache, prefer_authored=False)
    runtime = NarrativeRuntime(
        realization_effect=effect,
        semantic_verifier=SemanticVerifier(),
    )
    runtime.enable()
    runtime.admit(_event_impulse("live:template-vf", revision=91, fanout=91))
    planned = runtime.reduce_next()
    assert planned is not None
    await runtime.apply_effects(planned.effects)
    await runtime.wait_effects_idle()
    committed = None
    for _ in range(8):
        reduced = runtime.reduce_next()
        if reduced is None:
            await asyncio.sleep(0.01)
            continue
        await runtime.apply_effects(reduced.effects)
        await runtime.wait_effects_idle()
        if reduced is not None and "realization_committed" in reduced.effects:
            committed = reduced
            break
    assert committed is not None
    assert "verify_frame_attached_live" in committed.effects
    assert "semantic_verdict:accepted" in committed.effects


def test_narrative_runtime_same_time_external_before_callback_order() -> None:
    """#284 AC: library evidence for orderingScenario same_time_external_before_callback."""

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    assert runtime.admit(
        _context_with_timeline(
            "order:external",
            _timeline_run(
                revision=210,
                stream_epoch=1,
                narrative_run_active=True,
                transition_reasons=["session_restarted"],
            ),
            fanout=210,
        )
    ).accepted
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "order:callback",
            "REALIZATION_SUCCEEDED",
            9000,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    drained = list(runtime.drain())
    assert [item.command_id for item in drained] == ["order:external", "order:callback"]
    assert [item.reducer_sequence for item in drained] == [
        drained[0].reducer_sequence,
        drained[0].reducer_sequence + 1,
    ]
    assert drained[0].kind == "APPLY_CONTEXT_BATCH"
    assert drained[0].disposition == "handled"
    assert drained[1].kind == "REALIZATION_SUCCEEDED"
    assert drained[1].disposition == "ignored_stale_or_inapplicable"
    assert runtime.status().lane == "idle"


def test_narrative_runtime_same_time_callback_before_reset_order() -> None:
    """#284 AC: library evidence for orderingScenario same_time_callback_before_reset."""

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "order:callback-first",
            "REALIZATION_SUCCEEDED",
            9100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    assert runtime.admit(
        _context_with_timeline(
            "order:reset",
            _timeline_run(
                revision=211,
                stream_epoch=1,
                narrative_run_active=True,
                transition_reasons=["session_restarted"],
            ),
            fanout=211,
        )
    ).accepted
    drained = list(runtime.drain())
    assert [item.command_id for item in drained] == ["order:callback-first", "order:reset"]
    assert drained[0].kind == "REALIZATION_SUCCEEDED"
    assert drained[0].disposition == "handled"
    assert drained[0].lane_after == "committed"
    assert drained[1].kind == "APPLY_CONTEXT_BATCH"
    assert drained[1].disposition == "handled"
    assert runtime.status().lane in {"stopping", "idle", "building"}


def test_narrative_runtime_deadline_before_result_race() -> None:
    """#284 AC: library evidence for raceTrace deadline_before_result."""

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    assert runtime.admit(
        NarrativeCommand.realization_deadline(
            "race:deadline-first",
            3200,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            deadline_mono_ms=3200,
        )
    ).accepted
    timed_out = runtime.reduce_next()
    assert timed_out is not None
    assert timed_out.disposition == "handled"
    assert "realization_deadline" in timed_out.effects
    assert timed_out.lane_after == "idle"
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "race:late-result",
            "REALIZATION_SUCCEEDED",
            3300,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    late = runtime.reduce_next()
    assert late is not None
    assert late.disposition == "ignored_stale_or_inapplicable"
    assert "stale_realization_token" in late.effects
    assert late.lane_after == "idle"
    assert runtime.status().lane == "idle"


def test_narrative_runtime_reset_before_result_race() -> None:
    """#284 AC: library evidence for raceTrace reset_before_result."""

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    assert runtime.admit(
        _context_with_timeline(
            "race:reset",
            _timeline_run(
                revision=220,
                stream_epoch=1,
                narrative_run_active=True,
                transition_reasons=["session_restarted"],
            ),
            fanout=220,
        )
    ).accepted
    reset = runtime.reduce_next()
    assert reset is not None
    assert reset.disposition == "handled"
    assert "building_cancelled" in reset.effects
    assert reset.lane_after == "idle"
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "race:old-occurrence-result",
            "REALIZATION_SUCCEEDED",
            3400,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    late = runtime.reduce_next()
    assert late is not None
    assert late.disposition == "ignored_stale_or_inapplicable"
    assert "stale_realization_token" in late.effects
    assert runtime.status().lane == "idle"


def test_narrative_runtime_config_generation_then_completion_race() -> None:
    """#284 AC: completion races config generation — config rearms only; result may still commit."""

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    stale_silence = runtime._silence_generation  # noqa: SLF001
    assert runtime.admit(
        NarrativeCommand.config_update(
            "race:config-gen", 3500, valid=False, ledger=None, diagnostics=()
        )
    ).accepted
    config = runtime.reduce_next()
    assert config is not None
    assert config.lane_after == "building"
    assert "effect:cancel_realization" not in config.effects
    assert runtime._silence_generation == stale_silence + 1  # noqa: SLF001
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "race:config-then-result",
            "REALIZATION_SUCCEEDED",
            3600,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.disposition == "handled"
    assert committed.lane_after == "committed"
    assert "effect:dispatch_tts" in committed.effects


def test_narrative_runtime_validity_expiry_before_completion_race() -> None:
    """#284 AC: validity expiry cancels building; late completion stays stale."""

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    generation = runtime._validity_generation  # noqa: SLF001
    assert runtime.admit(
        NarrativeCommand.deadline(
            "race:validity-expiry",
            "VALIDITY_DEADLINE_ELAPSED",
            3700,
            generation=generation,
            deadline_mono_ms=3700,
        )
    ).accepted
    expired = runtime.reduce_next()
    assert expired is not None
    assert expired.disposition == "handled"
    assert "building_cancelled" in expired.effects or expired.lane_after == "idle"
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "race:after-validity",
            "REALIZATION_SUCCEEDED",
            3800,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    late = runtime.reduce_next()
    assert late is not None
    assert late.disposition == "ignored_stale_or_inapplicable"
    assert "stale_realization_token" in late.effects
    assert runtime.status().lane == "idle"


def test_runtime_does_not_back_mutate_upstream_timeline_or_fact_snapshots() -> None:
    """#284 AC: StreamTimeline/FactView projections stay immutable upstream truth."""

    import copy

    timeline = _timeline(revision=7)
    fact_view = _fact_view(1, revision=13)
    pristine_timeline = copy.deepcopy(timeline)
    pristine_facts = copy.deepcopy(fact_view)
    part = partition_context_batches(
        timeline=timeline,
        fact_view=fact_view,
        events=(),
        fanout_stream_sequence=71,
    )[0]

    # Caller mutates the dicts it still holds — frozen batch must be unaffected.
    timeline["timelineRevision"] = 999
    fact_view["facts"].clear()
    assert part.batch.timeline == pristine_timeline
    assert part.batch.fact_view == pristine_facts

    runtime = NarrativeRuntime()
    runtime.enable()
    assert runtime.admit(NarrativeCommand.context_batch("immut:context", 1000, part)).accepted
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert runtime.status().timeline_revision == 7
    assert runtime.status().fact_view_revision == 13

    # Property accessors return fresh dicts; mutating them cannot rewrite actor pointers.
    leaked = part.batch.timeline
    leaked["timelineRevision"] = 0
    assert runtime.status().timeline_revision == 7
    assert part.batch.timeline["timelineRevision"] == 7

    # Actor caches scalar revisions only — not live upstream owner objects.
    assert not hasattr(runtime, "_stream_timeline")
    assert not hasattr(runtime, "_feature_engine")
    assert getattr(runtime, "_timeline", None) is None
    assert getattr(runtime, "_fact_view", None) is None


def test_runtime_reads_detector_bank_status_without_stepping_or_owning_engines() -> None:
    """#284 AC: DetectorBank remains upstream-owned; FeatureEngine frames stay frozen."""

    import inspect
    from dataclasses import FrozenInstanceError

    from test_feature_engine import _sample

    from irswitch.events.detector_bank import DetectorBank
    from irswitch.events.feature_engine import FeatureEngine
    from irswitch.logic.stream_timeline import StreamTimeline

    bank = DetectorBank()
    step_calls: list[object] = []
    original_step = bank.step

    def tracked_step(*args: object, **kwargs: object) -> object:
        step_calls.append((args, kwargs))
        return original_step(*args, **kwargs)

    bank.step = tracked_step  # type: ignore[method-assign]

    runtime = NarrativeRuntime(detector_bank=bank)
    runtime.enable()
    assert runtime.admit(_pure_fact("immut:detectors", revision=8, fanout=81)).accepted
    assert runtime.reduce_next() is not None
    assert step_calls == []
    assert runtime.status().detector_disabled == ()

    bank.disable_for_run(("battle_ahead_v1",), reason="required_capture_lost")
    assert runtime.status().detector_disabled == (
        {"id": "battle_ahead_v1", "reason": "required_capture_lost"},
    )
    assert step_calls == []

    # Upstream owners remain independently mutable; actor does not absorb them.
    _timeline_owner = StreamTimeline()
    feature_owner = FeatureEngine()
    assert runtime.__dict__.get("_detector_bank") is bank
    assert "stream_timeline" not in inspect.signature(NarrativeRuntime.__init__).parameters
    assert "feature_engine" not in inspect.signature(NarrativeRuntime.__init__).parameters

    feature_step = feature_owner.observe(_sample())
    assert feature_step.frame is not None
    with pytest.raises(FrozenInstanceError):
        feature_step.frame.frame_sequence = 99  # type: ignore[misc]
    assert step_calls == []
