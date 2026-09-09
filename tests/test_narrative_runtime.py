"""#284 NarrativeRuntime — thin library slice."""

from __future__ import annotations

import asyncio
import dataclasses
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
