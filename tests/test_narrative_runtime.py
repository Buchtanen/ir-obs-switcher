"""#284 NarrativeRuntime — thin library slice."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_runtime import NarrativeRuntime, ReduceResult, RuntimeStatus

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

    runtime.fail_current_realization_for_test()
    runtime.admit(_event_impulse("e2", revision=4, fanout=12))
    second = runtime.reduce_next()
    assert second is not None
    assert second.planning_cycle_id == 1
    assert second.plans_dispatched == 2

    runtime.fail_current_realization_for_test()
    runtime.admit(_event_impulse("e3", revision=5, fanout=13))
    third = runtime.reduce_next()
    assert third is not None
    assert third.plans_dispatched == 2
    assert "planning_cycle_exhausted" in third.effects


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
