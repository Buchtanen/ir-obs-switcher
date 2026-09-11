"""#284 NarrativeIngress — shadow fanout→mailbox adapter (not live-wired)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_ingress import NarrativeIngress, project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_ingress.py"
)


def test_ingress_source_documents_shadow_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "Not exported from ``events/__init__.py``" in text
    assert "race.runtime" in text
    assert "commentary.consumer" in text
    assert "NarrativeIngress" not in events_exports
    assert "project_runtime_status" not in events_exports


def test_admit_context_publication_preserves_order_and_sequences() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    events = tuple(_event(index) for index in range(3))
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(3),
        events=events,
        fanout_stream_sequence=11,
        command_id_prefix="pub:1",
        enqueued_mono_ms=2_000,
    )
    assert result.accepted
    assert result.reason == "accepted"
    assert result.command_ids == ("pub:1:0",)
    assert result.mailbox_sequences == (1,)
    assert "ingress_publication_complete" in result.effects
    assert len(mailbox) == 1
    command = mailbox.dequeue()
    assert command is not None
    assert command.kind == "APPLY_CONTEXT_BATCH"
    assert command.external_order is not None
    assert command.external_order.fanout_stream_sequence == 11
    assert command.external_order.first_source_ordinal == 0
    assert command.external_order.last_source_ordinal == 2


def test_admit_splits_at_64_events_preserving_total_order() -> None:
    ingress = NarrativeIngress()
    events = tuple(_event(index) for index in range(65))
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(65),
        events=events,
        fanout_stream_sequence=11,
        command_id_prefix="pub:split",
        enqueued_mono_ms=2_100,
    )
    assert result.accepted
    assert result.command_ids == ("pub:split:0", "pub:split:1")
    assert result.mailbox_sequences == (1, 2)
    first = ingress.mailbox.dequeue()
    second = ingress.mailbox.dequeue()
    assert first is not None and second is not None
    assert first.mailbox_sequence < second.mailbox_sequence
    assert first.external_order is not None and second.external_order is not None
    assert first.external_order.first_source_ordinal == 0
    assert first.external_order.last_source_ordinal == 63
    assert second.external_order.first_source_ordinal == 64
    assert second.external_order.last_source_ordinal == 64


def test_ingress_mailbox_can_feed_narrative_runtime_without_live_wiring() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:rt",
        enqueued_mono_ms=2_200,
    )
    assert result.accepted
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert reduced.kind == "APPLY_CONTEXT_BATCH"
    assert reduced.disposition == "handled"
    assert "plan_dispatched" in reduced.effects


def test_project_runtime_status_emits_commentary_runtime_subset() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    status = runtime.status()
    assert isinstance(status, RuntimeStatus)
    projection = project_runtime_status(status)
    assert projection["schemaVersion"] == "commentary-runtime/2"
    assert projection["status"] == "ready"
    assert projection["language"] == "en"
    assert projection["speech"] == {
        "state": "idle",
        "sourceKind": None,
        "utteranceId": None,
        "beatId": None,
        "opportunityId": None,
        "backend": None,
        "backendGeneration": None,
        "dispatchedAtMonoMs": None,
        "acceptedAtMonoMs": None,
        "lastTerminal": None,
    }
    assert projection["queues"]["mailbox"]["capacity"] == 64
    assert projection["queues"]["mailbox"]["depth"] == 0
    assert projection["loop"]["active"] is False
    assert projection["timeline"] == {
        "broadcastEpoch": 0,
        "streamEpoch": 0,
        "narrativeRunActive": False,
        "streamActive": None,
        "streamState": "unknown",
        "sessionPlan": None,
        "sessionRef": None,
        "occurrenceId": None,
        "lineageId": None,
        "stage": None,
        "historyComplete": True,
    }
    assert projection["components"]["llm"] == {
        "status": "ready",
        "reason": None,
        "generation": 0,
        "configGeneration": 0,
        "model": "unconfigured",
        "residencyEvidence": "not_requested",
        "lastAttempt": None,
    }
    assert projection["components"]["tts"] == {
        "status": "ready",
        "reason": None,
        "backend": None,
        "backendGeneration": 0,
        "configGeneration": 0,
        "quarantinedGeneration": None,
        "voice": None,
    }
    assert projection["components"]["tape"]["status"] == "disabled"
    assert projection["components"]["detectors"] == {
        "status": "ready",
        "reason": None,
        "disabled": [],
    }
    assert projection["components"]["facts"]["status"] == "ready"
    assert projection["components"]["facts"]["active"] == 0
    assert projection["components"]["facts"]["historicalSummaries"] == 0
    assert projection["components"]["facts"]["historyComplete"] is True
    assert projection["components"]["facts"]["viewRevision"] == 0
    assert projection["queues"]["opportunities"] == {
        "depth": 0,
        "capacity": 128,
        "expired": 0,
        "evicted": 0,
    }
    assert projection["catalog"]["schemaVersion"] == "narrative-catalog/2"
    assert projection["catalog"]["eventIdentifierCount"] == 60
    assert projection["catalog"]["beatCount"] == 64
    assert projection["catalog"]["hash"].startswith("sha256:")
    assert len(projection["catalog"]["hash"]) == len("sha256:") + 64
    assert projection["config"] == {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 0,
        "desiredHash": "sha256:" + ("0" * 64),
        "effectiveHash": "sha256:" + ("0" * 64),
        "applySequence": 0,
        "pendingChanges": [],
    }
    assert projection["episodes"] == {
        "active": 0,
        "candidate": 0,
        "suspended": 0,
        "retainedCurrentCapacity": 64,
        "resolved": 0,
        "resolvedCapacity": 256,
    }
    assert projection["byTapeChannel"] == {}
    assert projection["recovery"]["count"] == 0
    assert "admissionDiagnostics" in projection["diagnostics"]


def test_project_runtime_status_ready_library_golden() -> None:
    """#273 thin status_ready: catalog/config/episodes/byTapeChannel stubs."""
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_ready_library.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == expected["status"]
    assert projection["catalog"] == expected["catalog"]
    assert projection["config"] == expected["config"]
    assert projection["episodes"] == expected["episodes"]
    assert projection["byTapeChannel"] == expected["byTapeChannel"]
    assert projection["queues"]["opportunities"] == expected["queues"]["opportunities"]
    assert projection["components"]["detectors"] == expected["components"]["detectors"]
    assert projection["components"]["facts"] == expected["components"]["facts"]


def test_project_runtime_status_loop_inactive_without_actor() -> None:
    """#284 loop liveness: library status reports loop.active=false until run()."""
    runtime = NarrativeRuntime()
    runtime.enable()
    assert runtime.status().loop_active is False
    projection = project_runtime_status(runtime.status())
    assert projection["loop"]["active"] is False


@pytest.mark.asyncio
async def test_project_runtime_status_loop_active_while_run_loop_owns_actor() -> None:
    """#284 loop liveness: loop.active tracks NarrativeRuntime.run() ownership."""
    import asyncio

    runtime = NarrativeRuntime()
    runtime.enable()
    task = asyncio.create_task(runtime.run())
    try:
        for _ in range(50):
            if runtime.status().loop_active:
                break
            await asyncio.sleep(0)
        assert runtime.status().loop_active is True
        assert project_runtime_status(runtime.status())["loop"]["active"] is True
        runtime.admit(NarrativeCommand.shutdown("loop:stop", 1, "test_stop"))
        await asyncio.wait_for(task, timeout=1.0)
        assert runtime.status().loop_active is False
        assert project_runtime_status(runtime.status())["loop"]["active"] is False
    finally:
        if not task.done():
            runtime.admit(NarrativeCommand.shutdown("loop:stop:force", 2, "test_stop"))
            await asyncio.wait_for(task, timeout=1.0)


def test_project_runtime_status_speech_retains_last_terminal_after_completion() -> None:
    """#273 speech projection keeps lastTerminal after the lane returns to idle."""
    from irswitch.contracts.command import NarrativeCommand

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "speech:proj:manual", 12_000, text="Gap is closing.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.disposition == "handled"
    projection = project_runtime_status(runtime.status())
    assert projection["speech"]["state"] == "committed"
    assert projection["speech"]["sourceKind"] == "manual"
    assert projection["speech"]["utteranceId"] is not None
    assert projection["speech"]["beatId"] is None
    utterance = runtime.current_utterance_token()
    assert utterance is not None

    def _tts(kind: str, command_id: str, *, at_mono_ms: int) -> NarrativeCommand:
        return NarrativeCommand.tts_callback(
            command_id,
            kind,  # type: ignore[arg-type]
            at_mono_ms,
            utterance_id=str(utterance["utteranceId"]),
            utterance_ordinal=int(utterance["utteranceOrdinal"]),
            backend_generation=int(utterance["backendGeneration"]),
            dispatch_generation=int(utterance["dispatchGeneration"]),
            callback={
                "schemaVersion": "tts-callback/2",
                "callbackId": f"cb:{command_id}",
                "kind": {
                    "PLAYBACK_ACCEPTED": "playback_accepted",
                    "SPEECH_COMPLETED": "completed",
                }[kind],
                "utteranceId": utterance["utteranceId"],
                "utteranceOrdinal": utterance["utteranceOrdinal"],
                "backend": "sapi",
                "backendGeneration": utterance["backendGeneration"],
                "dispatchGeneration": utterance["dispatchGeneration"],
                "workerSequence": 1,
                "observedMonoMs": at_mono_ms,
                "detailCode": None,
            },
        )

    runtime.admit(_tts("PLAYBACK_ACCEPTED", "speech:proj:pb", at_mono_ms=12_200))
    accepted = runtime.reduce_next()
    assert accepted is not None
    assert accepted.lane_after == "speaking"
    speaking = project_runtime_status(runtime.status())
    assert speaking["speech"]["state"] == "speaking"
    assert speaking["speech"]["acceptedAtMonoMs"] == 12_200

    runtime.admit(_tts("SPEECH_COMPLETED", "speech:proj:done", at_mono_ms=12_500))
    done = runtime.reduce_next()
    assert done is not None
    projection = project_runtime_status(runtime.status())
    assert projection["speech"]["state"] == "idle"
    assert projection["speech"]["utteranceId"] is None
    assert projection["speech"]["lastTerminal"] == {
        "utteranceId": utterance["utteranceId"],
        "sourceKind": "manual",
        "reason": "completed",
        "atMonoMs": 12_500,
    }


def test_project_runtime_status_speech_idle_golden() -> None:
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_speech_idle.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["language"] == expected["language"]
    assert projection["speech"] == expected["speech"]
    assert projection["components"]["llm"] == expected["components"]["llm"]
    assert projection["components"]["tts"] == expected["components"]["tts"]
    assert projection["components"]["tape"]["status"] == expected["components"]["tape"]["status"]


def test_project_runtime_status_components_llm_tts_golden() -> None:
    """#273 llm/tts schema-complete defaults without an attached LlmComponent."""
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_components_llm_tts.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == expected["status"]
    assert projection["components"]["llm"] == expected["components"]["llm"]
    assert projection["components"]["tts"] == expected["components"]["tts"]


def test_project_runtime_status_llm_live_after_warmup() -> None:
    """#273/#284 live llm projection follows LlmComponent warmup residency/generation."""
    from irswitch.events.narrative_realization_bridge import warmup_qwen_component
    from irswitch.events.qwen_transport import FakeTransport, LlmComponent

    component = LlmComponent()
    assert warmup_qwen_component(component, FakeTransport(), generation=4) is True
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    projection = project_runtime_status(runtime.status())
    assert projection["components"]["llm"] == {
        "status": "ready",
        "reason": None,
        "generation": 4,
        "configGeneration": 0,
        "model": "qwen3:4b-instruct-2507-q4_K_M",
        "residencyEvidence": "warmup_succeeded",
        "lastAttempt": None,
    }


def test_project_runtime_status_llm_live_warmup_failed_maps_unavailable() -> None:
    """Failed warmup stays schema-safe: unavailable + not_requested residency evidence."""
    from irswitch.events.narrative_realization_bridge import warmup_qwen_component
    from irswitch.events.qwen_transport import FakeTransport, LlmComponent

    component = LlmComponent()
    assert warmup_qwen_component(component, FakeTransport(fail=True), generation=2) is False
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    llm = project_runtime_status(runtime.status())["components"]["llm"]
    assert llm["status"] == "unavailable"
    assert llm["reason"] == "component_unavailable"
    assert llm["generation"] == 2
    assert llm["model"] == "qwen3:4b-instruct-2507-q4_K_M"
    assert llm["residencyEvidence"] == "not_requested"
    assert llm["lastAttempt"] is None


def test_project_runtime_status_llm_tts_config_generation_from_ledger() -> None:
    """Live llm/tts configGeneration tracks CONFIG_UPDATE desiredGeneration when present."""
    from irswitch.events.narrative_realization_bridge import warmup_qwen_component
    from irswitch.events.qwen_transport import FakeTransport, LlmComponent

    component = LlmComponent()
    assert warmup_qwen_component(component, FakeTransport(), generation=1) is True
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    # Reuse helper if present; otherwise inline a minimal ledger.
    ledger = _config_ledger(desired_generation=7)
    runtime._config_ledger = ledger  # library test seam for status projection
    projection = project_runtime_status(runtime.status())
    assert projection["components"]["llm"]["configGeneration"] == 7
    assert projection["components"]["tts"]["configGeneration"] == 7


def test_project_runtime_status_tts_voice_from_config_ledger_desired() -> None:
    """#273/#284 tts.voice projects from CONFIG_UPDATE desiredValues when effective empty."""
    runtime = NarrativeRuntime()
    runtime.enable()
    assert project_runtime_status(runtime.status())["components"]["tts"]["voice"] is None
    runtime._config_ledger = _config_ledger(desired_generation=3)
    projection = project_runtime_status(runtime.status())
    assert projection["components"]["tts"]["voice"] == "en-US"


def test_project_runtime_status_tts_voice_prefers_effective_over_desired() -> None:
    """Effective TTS voice wins over desired when both bags are present."""
    runtime = NarrativeRuntime()
    runtime.enable()
    ledger = _config_ledger(desired_generation=4)
    ledger["desiredValues"] = {"voice": "desired-voice"}
    ledger["effectiveValues"] = {"voice": "M1"}
    runtime._config_ledger = ledger
    projection = project_runtime_status(runtime.status())
    assert projection["components"]["tts"]["voice"] == "M1"


def test_project_runtime_status_tts_quarantined_generation_from_status() -> None:
    """quarantinedGeneration + timeout reason after stop/start-timeout quarantine."""
    import json
    from dataclasses import replace
    from pathlib import Path

    runtime = NarrativeRuntime()
    runtime.enable()
    assert (
        project_runtime_status(runtime.status())["components"]["tts"]["quarantinedGeneration"]
        is None
    )
    status = replace(
        runtime.status(),
        speech_backend="supertonic",
        speech_backend_generation=3,
        speech_quarantined_generation=3,
        speech_quarantine_reason="tts_start_timeout",
        component_health={**runtime.status().component_health, "tts": "unavailable"},
    )
    projection = project_runtime_status(status)
    tts = projection["components"]["tts"]
    assert tts["quarantinedGeneration"] == 3
    assert tts["status"] == "unavailable"
    assert tts["reason"] == "tts_start_timeout"
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_component_tts_quarantine_timeout.json"
        ).read_text(encoding="utf-8")
    )
    assert tts == golden


def test_project_runtime_status_tts_quarantine_defaults_stop_timeout_reason() -> None:
    """Missing quarantine reason still projects the bounded tts_stop_timeout id."""
    from dataclasses import replace

    runtime = NarrativeRuntime()
    runtime.enable()
    status = replace(
        runtime.status(),
        speech_quarantined_generation=2,
        speech_quarantine_reason=None,
        component_health={**runtime.status().component_health, "tts": "unavailable"},
    )
    tts = project_runtime_status(status)["components"]["tts"]
    assert tts["reason"] == "tts_stop_timeout"
    assert tts["status"] == "unavailable"


def test_project_runtime_status_llm_last_attempt_after_qwen_success() -> None:
    """#273/#284 lastAttempt fills after first admitted Qwen realization."""
    import binascii

    from irswitch.events.narrative_realization_bridge import (
        realize_qwen_text,
        warmup_qwen_component,
    )
    from irswitch.events.qwen_transport import (
        FakeTransport,
        LlmComponent,
        RealizerService,
        load_transport_goldens,
    )

    goldens = load_transport_goldens()
    chunks = None
    for row in goldens["sse"]["valid"]:
        if row["id"] == "role_content_usage_done":
            chunks = [binascii.unhexlify(item) for item in row["chunksHex"]]
            break
    assert chunks is not None

    component = LlmComponent()
    assert warmup_qwen_component(component, FakeTransport(chunks=chunks), generation=1) is True
    # Warmup must not invent a status lastAttempt.
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    assert project_runtime_status(runtime.status())["components"]["llm"]["lastAttempt"] is None

    service = RealizerService(transport=FakeTransport(chunks=chunks))
    text = realize_qwen_text(
        beat_id="battle.approach",
        request_ordinal=2,
        dispatch_generation=7,
        service=service,
        component=component,
        now_ms=91_000,
    )
    assert text is not None
    attempt = project_runtime_status(runtime.status())["components"]["llm"]["lastAttempt"]
    assert attempt is not None
    assert attempt["outcome"] == "succeeded"
    assert attempt["terminalReason"] is None
    assert isinstance(attempt["requestId"], str) and attempt["requestId"]
    assert attempt["ttfbMs"] is None or attempt["ttfbMs"] >= 0
    assert attempt["ttftMs"] is None or attempt["ttftMs"] >= 0
    assert attempt["totalMs"] is None or attempt["totalMs"] >= 0
    assert attempt["reducerLagMs"] is None or attempt["reducerLagMs"] >= 0


def test_project_runtime_status_llm_last_attempt_after_qwen_failure() -> None:
    """Failed admitted Qwen request projects lastAttempt.outcome=failed."""
    from irswitch.events.narrative_realization_bridge import (
        realize_qwen_text,
        warmup_qwen_component,
    )
    from irswitch.events.qwen_transport import FakeTransport, LlmComponent, RealizerService

    component = LlmComponent()
    assert warmup_qwen_component(component, FakeTransport(), generation=2) is True
    service = RealizerService(transport=FakeTransport(fail=True))
    assert (
        realize_qwen_text(
            beat_id="battle.approach",
            request_ordinal=3,
            dispatch_generation=8,
            service=service,
            component=component,
            now_ms=50_000,
        )
        is None
    )
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    attempt = project_runtime_status(runtime.status())["components"]["llm"]["lastAttempt"]
    assert attempt is not None
    assert attempt["outcome"] == "failed"
    assert attempt["terminalReason"] == "realization_transport"
    assert attempt["requestId"]


def test_project_runtime_status_llm_last_attempt_timeout_maps_timed_out() -> None:
    """Deadline-expired Qwen admission maps outcome to timed_out."""
    from irswitch.events.qwen_transport import (
        FakeTransport,
        LlmComponent,
        RealizationIntent,
        RealizerService,
        load_transport_goldens,
    )

    component = LlmComponent()
    component.start_preflight(desired_generation=1, warmup=True)
    component.complete_preflight(generation=1, residency="warmup_succeeded")
    component.model = "qwen3:4b-instruct-2507-q4_K_M"
    prompt = dict(load_transport_goldens()["compiledPrompt"])
    intent = RealizationIntent(
        process_instance_id="narrative-runtime",
        request_ordinal=9,
        dispatch_generation=1,
        backend="qwen_compiled",
        plan_id="plan:timeout",
        planning_cycle_id="cycle:1",
        cycle_attempt_ordinal=1,
        bundle_id="bundle:timeout",
        bundle_hash="sha256:" + ("88" * 32),
        compiled_prompt=prompt,
        component_generation=1,
        config_generation=1,
        effective_config_hash="sha256:" + ("55" * 32),
        config_apply_sequence=1,
        capture_prompt="hash",
        capture_completion=True,
        dispatched_mono_ms=10_000,
        deadline_mono_ms=10_000,
        beat_id="battle.approach",
        episode_revision=1,
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.2,
        top_p=0.8,
        max_tokens=96,
        seed=17,
        pattern_id="battle.approach:tight:1",
        render_contract_version=2,
        now_ms=10_000,
    )
    step = RealizerService(transport=FakeTransport()).try_start(intent, component=component)
    assert step.outcome == "failed"
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    attempt = project_runtime_status(runtime.status())["components"]["llm"]["lastAttempt"]
    assert attempt is not None
    assert attempt["outcome"] == "timed_out"
    assert attempt["terminalReason"] == "realization_timeout"


def test_project_runtime_status_facts_live_after_context() -> None:
    """#273/#284 facts block tracks live viewRevision/active/historicalSummaries."""
    from test_narrative_context_batch import _event, _fact_view, _timeline

    from irswitch.commentary.mailbox import NarrativeMailbox
    from irswitch.events.narrative_ingress import NarrativeIngress

    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    fact_view = _fact_view(3, revision=11)
    fact_view["compactedSummaryRefs"] = ["summary:a", "summary:b"]
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=fact_view,
        events=(_event(0, fanout=21, fact_revision=11),),
        fanout_stream_sequence=21,
        command_id_prefix="facts:live",
        enqueued_mono_ms=5_000,
    )
    assert result.accepted
    reduced = runtime.reduce_next()
    assert reduced is not None
    facts = project_runtime_status(runtime.status())["components"]["facts"]
    assert facts == {
        "status": "ready",
        "reason": None,
        "viewRevision": 11,
        "active": 3,
        "historicalSummaries": 2,
        "historyComplete": True,
    }


def _admit_and_reduce(
    *,
    runtime: NarrativeRuntime,
    timeline: dict,
    fact_view: dict,
    prefix: str,
    fanout: int,
    enqueued_mono_ms: int,
) -> None:
    from test_narrative_context_batch import _event

    from irswitch.events.narrative_ingress import NarrativeIngress

    mailbox = runtime._mailbox  # noqa: SLF001 — shared mailbox identity for admit/reduce
    ingress = NarrativeIngress(mailbox)
    result = ingress.admit_context_publication(
        timeline=timeline,
        fact_view=fact_view,
        events=(_event(0, fanout=fanout, fact_revision=int(fact_view["viewRevision"])),),
        fanout_stream_sequence=fanout,
        command_id_prefix=prefix,
        enqueued_mono_ms=enqueued_mono_ms,
    )
    assert result.accepted
    reduced = runtime.reduce_next()
    assert reduced is not None


def test_project_runtime_status_facts_degraded_after_capacity_eviction() -> None:
    """#273 facts become degraded+fact_capacity_evicted after lossy compaction."""
    from test_narrative_context_batch import _fact_view, _timeline

    from irswitch.commentary.mailbox import NarrativeMailbox

    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    fact_view = _fact_view(2, revision=12)
    fact_view["historyComplete"] = False
    _admit_and_reduce(
        runtime=runtime,
        timeline=_timeline(),
        fact_view=fact_view,
        prefix="facts:evicted",
        fanout=31,
        enqueued_mono_ms=6_000,
    )
    facts = project_runtime_status(runtime.status())["components"]["facts"]
    expected = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_component_facts_evicted.json"
        ).read_text(encoding="utf-8")
    )
    assert facts == expected


def test_project_runtime_status_facts_unavailable_while_capacity_exhausted() -> None:
    """#273 facts are unavailable+fact_capacity_exhausted until a coherent view fits."""
    from test_narrative_context_batch import _fact_view, _timeline

    from irswitch.commentary.mailbox import NarrativeMailbox

    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    # FactView contract has no diagnostics; FactLedger exhaustion is latched via
    # note_fact_capacity (library hook for upstream wiring).
    runtime.note_fact_capacity("fact_capacity_exhausted")
    facts = project_runtime_status(runtime.status())["components"]["facts"]
    assert facts["status"] == "unavailable"
    assert facts["reason"] == "fact_capacity_exhausted"
    assert facts["historyComplete"] is False

    recovered = _fact_view(1, revision=14)
    recovered["historyComplete"] = False
    _admit_and_reduce(
        runtime=runtime,
        timeline=_timeline(revision=4),
        fact_view=recovered,
        prefix="facts:exhausted-clear",
        fanout=33,
        enqueued_mono_ms=7_100,
    )
    facts = project_runtime_status(runtime.status())["components"]["facts"]
    assert facts == {
        "status": "degraded",
        "reason": "fact_capacity_evicted",
        "viewRevision": 14,
        "active": 1,
        "historicalSummaries": 0,
        "historyComplete": False,
    }


def test_project_runtime_status_facts_ready_only_on_new_lossless_run() -> None:
    """#273 only a new narrative run without capacity loss restores facts ready."""
    from test_narrative_context_batch import _fact_view, _timeline

    from irswitch.commentary.mailbox import NarrativeMailbox

    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    evicted = _fact_view(1, revision=15)
    evicted["historyComplete"] = False
    _admit_and_reduce(
        runtime=runtime,
        timeline=_timeline(),
        fact_view=evicted,
        prefix="facts:run-evict",
        fanout=41,
        enqueued_mono_ms=8_000,
    )
    assert project_runtime_status(runtime.status())["components"]["facts"]["status"] == "degraded"

    closed = _timeline(revision=5)
    closed["narrativeRunActive"] = False
    _admit_and_reduce(
        runtime=runtime,
        timeline=closed,
        fact_view=_fact_view(1, revision=16),
        prefix="facts:run-close",
        fanout=42,
        enqueued_mono_ms=8_100,
    )
    # Latch survives run close; still degraded until a new lossless open.
    assert (
        project_runtime_status(runtime.status())["components"]["facts"]["reason"]
        == "fact_capacity_evicted"
    )

    reopened = _timeline(revision=6)
    reopened["narrativeRunActive"] = True
    reopened["streamEpoch"] = 2
    lossless = _fact_view(1, revision=17)
    lossless["streamEpoch"] = 2
    _admit_and_reduce(
        runtime=runtime,
        timeline=reopened,
        fact_view=lossless,
        prefix="facts:run-open",
        fanout=43,
        enqueued_mono_ms=8_200,
    )
    facts = project_runtime_status(runtime.status())["components"]["facts"]
    assert facts == {
        "status": "ready",
        "reason": None,
        "viewRevision": 17,
        "active": 1,
        "historicalSummaries": 0,
        "historyComplete": True,
    }


def test_project_runtime_status_detectors_disabled_from_bank() -> None:
    """#273/#284 detectors.disabled mirrors DetectorBank disable_for_run reasons."""
    from irswitch.events.detector_bank import DetectorBank

    bank = DetectorBank()
    bank.disable_for_run(("battle_ahead_v1",), reason="required_capture_lost")
    runtime = NarrativeRuntime(detector_bank=bank)
    runtime.enable()
    detectors = project_runtime_status(runtime.status())["components"]["detectors"]
    assert detectors["status"] == "ready"
    assert detectors["reason"] is None
    assert detectors["disabled"] == [{"id": "battle_ahead_v1", "reason": "required_capture_lost"}]


def test_project_runtime_status_detectors_empty_without_bank() -> None:
    """Without a DetectorBank, detectors stay the ready/empty stub."""
    runtime = NarrativeRuntime()
    runtime.enable()
    assert project_runtime_status(runtime.status())["components"]["detectors"] == {
        "status": "ready",
        "reason": None,
        "disabled": [],
    }


def test_project_runtime_status_loop_heartbeats_after_reduce() -> None:
    """#284 loop heartbeats: reduceCount/lastReduceMonoMs advance on reduce_next."""
    runtime = NarrativeRuntime()
    runtime.enable()
    before = project_runtime_status(runtime.status())["loop"]
    assert before == {
        "active": False,
        "lastReduceMonoMs": None,
        "reduceCount": 0,
        "supervisors": {},
    }
    from irswitch.contracts.command import NarrativeCommand

    cmd = NarrativeCommand.shutdown("hb:1", 1, "test_stop")
    assert runtime.admit(cmd).accepted
    reduced = runtime.reduce_next()
    assert reduced is not None
    after = project_runtime_status(runtime.status())["loop"]
    assert after["active"] is False
    assert after["reduceCount"] == 1
    assert isinstance(after["lastReduceMonoMs"], int) and after["lastReduceMonoMs"] >= 0
    assert after["supervisors"] == {}


def test_project_runtime_status_loop_supervisors_from_attached_providers() -> None:
    """#284 loop.supervisors mirrors attached WorkerSupervisor-style snapshots."""
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.attach_supervisor_heartbeat(
        "narrativeRuntime",
        lambda: {"running": True, "restarts": 2, "lastError": None},
    )
    runtime.attach_supervisor_heartbeat(
        "narrativeShadow",
        lambda: {"running": False, "restarts": 0, "lastError": "boom"},
    )
    loop = project_runtime_status(runtime.status())["loop"]
    assert loop["supervisors"] == {
        "narrativeRuntime": {"running": True, "restarts": 2, "lastError": None},
        "narrativeShadow": {"running": False, "restarts": 0, "lastError": "boom"},
    }


def test_race_attaches_narrative_supervisor_heartbeats() -> None:
    """Race cutover attaches narrative runtime/shadow supervisor heartbeats."""
    race_src = (
        Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
    ).read_text(encoding="utf-8")
    assert "attach_supervisor_heartbeat" in race_src
    assert '"narrativeRuntime"' in race_src or "'narrativeRuntime'" in race_src
    assert '"narrativeShadow"' in race_src or "'narrativeShadow'" in race_src


def test_race_wires_llm_component_into_narrative_runtime() -> None:
    """Race cutover passes the warmed LlmComponent into NarrativeRuntime for status."""
    race_src = (
        Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
    ).read_text(encoding="utf-8")
    assert "NarrativeRuntime(" in race_src
    # Must appear as NarrativeRuntime kwarg, not only realization_effect.
    block_start = race_src.index("runtime = NarrativeRuntime(")
    depth = 0
    block_end = None
    for index, char in enumerate(race_src[block_start:], start=block_start):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                block_end = index + 1
                break
    assert block_end is not None
    block = race_src[block_start:block_end]
    assert "llm_component=llm_component" in block


def test_project_runtime_status_identity_follows_context_timeline() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:identity",
        enqueued_mono_ms=3_000,
    )
    assert result.accepted
    reduced = runtime.reduce_next()
    assert reduced is not None
    projection = project_runtime_status(runtime.status())
    timeline = projection["timeline"]
    assert timeline["broadcastEpoch"] == 4
    assert timeline["streamEpoch"] == 1
    assert timeline["narrativeRunActive"] is True
    assert timeline["streamActive"] is True
    assert timeline["streamState"] == "active"
    assert timeline["historyComplete"] is True
    assert timeline["sessionPlan"] == {
        "revision": 1,
        "valid": True,
        "reason": None,
        "stages": ["practice", "qualifying", "race"],
    }
    assert timeline["sessionRef"] == {"subSessionId": "42", "sessionNum": 2}
    assert timeline["occurrenceId"] == "1:race:0"
    assert timeline["lineageId"] == "1:race:0"
    assert timeline["stage"] == "race"


def test_project_tape_unavailable_exposes_capture_loss_reason() -> None:
    """#273: recorder/tape unavailable projects capture_unavailable on components.tape."""
    import json
    from dataclasses import replace
    from pathlib import Path

    from irswitch.events.narrative_ingress import project_runtime_status
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    status = replace(runtime.status(), tape_status="unavailable")
    projected = project_runtime_status(status)
    tape = projected["components"]["tape"]
    assert tape["status"] == "unavailable"
    assert tape["reason"] == "capture_unavailable"
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_component_tape_capture_unavailable.json"
        ).read_text(encoding="utf-8")
    )
    assert tape == golden


def test_project_tape_counters_from_runtime_status() -> None:
    """#273: tape drop/size/purpose-channel counters project on components.tape."""
    import json
    from dataclasses import replace
    from pathlib import Path

    from irswitch.events.narrative_ingress import project_runtime_status
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    status = replace(
        runtime.status(),
        tape_status="ready",
        tape_path="narrative-process_race-s1-f0000.ndjson",
        tape_size=1280,
        tape_drops=3,
        tape_drops_by_priority={"sample": 1, "normal": 1, "critical": 1},
        tape_purpose_counts=(
            {"purposeChannel": "flow", "count": 5},
            {"purposeChannel": "detector_tuning", "count": 2},
        ),
    )
    projected = project_runtime_status(status)
    tape = projected["components"]["tape"]
    assert tape["drops"] == sum(tape["dropsByPriority"].values())
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_component_tape_counters.json"
        ).read_text(encoding="utf-8")
    )
    assert tape == golden


def test_project_tape_counters_live_from_attached_writer() -> None:
    """#273: attached NarrativeTapeWriter feeds live tape counters into status."""
    import copy
    from pathlib import Path

    from test_narrative_tape_writer import _golden

    from irswitch.commentary.tape_writer import NarrativeTapeWriter
    from irswitch.events.narrative_ingress import project_runtime_status
    from irswitch.events.narrative_runtime import NarrativeRuntime

    manifest = copy.deepcopy(_golden("tape-manifest-framing"))
    manifest["enabledPurposeChannels"] = ["flow", "detector_tuning"]
    records: list[bytes] = []

    def sink(data: bytes) -> None:
        records.append(data)

    writer = NarrativeTapeWriter(
        Path("/tmp/unused"),
        manifest,
        capacity=1,
        sink=sink,
    )
    record = _golden("tape-health-record")
    writer.submit(record)
    writer.submit({**record, "recordId": "record:sample:1", "recordPriority": "sample"})
    writer.submit(
        {
            **record,
            "recordId": "record:critical:1",
            "recordPriority": "critical",
            "purposeChannel": "detector_tuning",
        }
    )
    # Saturate queue: evict/drop the sample row.
    writer.submit(
        {
            **record,
            "recordId": "record:normal:2",
            "recordPriority": "normal",
            "purposeChannel": "flow",
        }
    )

    runtime = NarrativeRuntime(tape_writer=writer)
    runtime.enable()
    projected = project_runtime_status(runtime.status())
    tape = projected["components"]["tape"]
    assert tape["drops"] >= 1
    assert tape["drops"] == sum(tape["dropsByPriority"].values())
    assert tape["status"] == "degraded"
    assert tape["reason"] == "tape_queue_drop"
    assert isinstance(tape["size"], int)
    assert tape["size"] >= 0
    assert isinstance(tape["purposeCounts"], list)


def test_project_detectors_disabled_required_rows() -> None:
    """#273: disabled-required detectors appear as bounded {id, reason} rows."""
    import json
    from dataclasses import replace
    from pathlib import Path

    from irswitch.events.narrative_ingress import project_runtime_status
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    status = replace(
        runtime.status(),
        detector_disabled=(
            {"id": "gap_closing", "reason": "disabled_by_config"},
            {"id": "battle_ahead", "reason": "capture_unavailable"},
        ),
    )
    projected = project_runtime_status(status)
    detectors = projected["components"]["detectors"]
    assert detectors["status"] == "ready"
    assert detectors["disabled"] == [
        {"id": "battle_ahead", "reason": "capture_unavailable"},
        {"id": "gap_closing", "reason": "disabled_by_config"},
    ]
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_component_detectors_disabled.json"
        ).read_text(encoding="utf-8")
    )
    # Freeze exact projected shape including sort order (id ascending).
    assert detectors == golden


def test_project_immutable_recorder_model_timeline_detector_shapes() -> None:
    """#273: freeze recorder/model/timeline/detector health projection shapes."""
    import json
    from pathlib import Path

    from irswitch.events.narrative_ingress import project_runtime_status
    from irswitch.events.narrative_runtime import NarrativeRuntime

    projected = project_runtime_status(NarrativeRuntime().status())
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_health_projections_library.json"
        ).read_text(encoding="utf-8")
    )
    assert {
        "timeline": projected["timeline"],
        "components": {
            "llm": projected["components"]["llm"],
            "tape": projected["components"]["tape"],
            "detectors": projected["components"]["detectors"],
        },
    } == golden


def test_project_commentary_health_component_disabled_default() -> None:
    from irswitch.events.narrative_ingress import project_commentary_health_component

    assert project_commentary_health_component() == {"status": "disabled", "reason": None}
    runtime = NarrativeRuntime()
    runtime.enable()
    assert project_commentary_health_component(runtime.status()) == {
        "status": "ready",
        "reason": None,
    }


def test_project_commentary_health_reason_uses_actor_recovery_code() -> None:
    """``/health`` commentary.reason may carry mailbox/tape recovery codes (#284)."""

    import json
    from pathlib import Path

    from test_narrative_runtime import _pure_fact

    from irswitch.contracts.command import NarrativeCommand
    from irswitch.events.narrative_ingress import project_commentary_health_component

    runtime = NarrativeRuntime()
    runtime.enable()
    latest = _pure_fact("health:latest", revision=70, fanout=70)
    runtime.admit(
        NarrativeCommand.recovery(
            "health:recovery",
            9100,
            latest_context=latest.context_part,
            loss_first_sequence=1,
            loss_last_sequence=2,
            safety_effects=(latest.safety_effect(),),
        )
    )
    assert runtime.reduce_next() is not None
    projected = project_commentary_health_component(runtime.status())
    assert projected["status"] in {"ready", "degraded"}
    assert projected["reason"] in {
        "history_incomplete",
        "mailbox_history_incomplete",
        "mailbox_recovery",
    }

    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "v2.0.0"
            / "machine"
            / "api-contracts.schema.json"
        ).read_text(encoding="utf-8")
    )
    health = schema["$defs"]["HealthCommentarySummary"]
    reason_enum = health["properties"]["reason"]["oneOf"][0]["enum"]
    for code in (
        "mailbox_recovery",
        "mailbox_overloaded",
        "mailbox_evicted_update",
        "deadline_admission_skipped",
        "capture_unavailable",
        "history_incomplete",
    ):
        assert code in reason_enum
    assert projected["reason"] in reason_enum


def test_project_runtime_status_identity_golden_disabled() -> None:
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_identity_disabled.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["timeline"] == expected["timeline"]
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == expected["status"]


def test_project_runtime_status_stopped_golden() -> None:
    """#273 public enum: stopped status + null session-plan identity."""
    import json
    from pathlib import Path

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime._runtime = "stopped"
    projection = project_runtime_status(runtime.status())
    expected = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_stopped.json"
        ).read_text(encoding="utf-8")
    )
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == "stopped"
    assert projection["language"] == "en"
    assert projection["timeline"] == expected["timeline"]
    assert projection["timeline"]["sessionPlan"] is None


def test_project_runtime_status_timeline_session_null_golden() -> None:
    """#273 thin timeline session identity — all-or-none null stubs when idle."""
    import json
    from pathlib import Path

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_timeline_session_null.json"
    )
    projection = project_runtime_status(NarrativeRuntime().status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == expected["status"]
    assert projection["timeline"] == expected["timeline"]
    assert projection["timeline"]["sessionPlan"] is None
    assert projection["timeline"]["sessionRef"] is None
    assert projection["timeline"]["occurrenceId"] is None
    assert projection["timeline"]["lineageId"] is None
    assert projection["timeline"]["stage"] is None


def test_project_runtime_status_timeline_session_from_context_golden() -> None:
    """#273 live session identity projected from APPLY_CONTEXT timeline."""
    import json
    from pathlib import Path

    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:session",
        enqueued_mono_ms=3_000,
    )
    assert result.accepted
    assert runtime.reduce_next() is not None
    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "status_identity_after_context.json"
    )
    projection = project_runtime_status(runtime.status())
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert projection["schemaVersion"] == expected["schemaVersion"]
    assert projection["status"] == expected["status"]
    assert projection["timeline"] == expected["timeline"]


def _config_ledger(
    *,
    desired_generation: int = 3,
    apply_sequence: int = 7,
) -> dict:
    digest_a = "sha256:" + ("a" * 64)
    digest_b = "sha256:" + ("b" * 64)
    return {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": desired_generation,
        "desiredHash": digest_a,
        "effectiveHash": digest_b,
        "applySequence": apply_sequence,
        "desiredValues": {"voice": "en-US"},
        "effectiveValues": {},
        "pendingChanges": [
            {
                "boundary": "next_plan_or_manual",
                "key": "voice",
                "desiredGeneration": desired_generation,
            }
        ],
        "acceptedMonoMs": 4_000,
    }


def test_project_runtime_status_config_follows_config_update_ledger() -> None:
    """#273 live config block from CONFIG_UPDATE ledger (all-or-none unload)."""
    from irswitch.contracts.command import NarrativeCommand

    runtime = NarrativeRuntime()
    runtime.enable()
    assert project_runtime_status(runtime.status())["config"]["desiredGeneration"] == 0

    ledger = _config_ledger()
    assert runtime.admit(
        NarrativeCommand.config_update(
            "cfg:live",
            4_000,
            valid=True,
            ledger=ledger,
            diagnostics=(),
        )
    ).accepted
    assert runtime.reduce_next() is not None
    config = project_runtime_status(runtime.status())["config"]
    assert config == {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 3,
        "desiredHash": ledger["desiredHash"],
        "effectiveHash": ledger["effectiveHash"],
        "applySequence": 7,
        "pendingChanges": [
            {
                "key": "voice",
                "boundary": "next_plan_or_manual",
                "desiredGeneration": 3,
            }
        ],
    }

    assert runtime.admit(
        NarrativeCommand.config_update(
            "cfg:clear",
            4_100,
            valid=False,
            ledger=None,
            diagnostics=(),
        )
    ).accepted
    assert runtime.reduce_next() is not None
    cleared = project_runtime_status(runtime.status())["config"]
    assert cleared["desiredGeneration"] == 0
    assert cleared["applySequence"] == 0
    assert cleared["pendingChanges"] == []


def test_project_runtime_status_fixed_en_catalog_and_pending_boundaries_golden() -> None:
    """#273 fixed language=en, packaged catalog hash, value-free pending boundaries."""
    import json
    from pathlib import Path

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime._config_ledger = {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 7,
        "desiredHash": "sha256:" + ("1" * 64),
        "effectiveHash": "sha256:" + ("2" * 64),
        "applySequence": 12,
        "desiredValues": {"commentary.tts.voice": "secret-voice"},
        "pendingChanges": [
            {
                "key": "commentary.tts.voice",
                "boundary": "next_utterance",
                "desiredGeneration": 7,
                "value": "secret-voice",
            },
            {
                "key": "commentary.detector.battle_ahead_v1.max_closing_slope",
                "boundary": "next_stream",
                "desiredGeneration": 7,
                "value": 0.4,
            },
        ],
    }
    projection = project_runtime_status(runtime.status())
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_config_pending_boundaries.json"
        ).read_text(encoding="utf-8")
    )
    assert projection["language"] == "en"
    assert projection["language"] == golden["language"]
    assert projection["catalog"] == golden["catalog"]
    assert projection["config"] == golden["config"]
    for row in projection["config"]["pendingChanges"]:
        assert set(row) == {"key", "boundary", "desiredGeneration"}


def test_project_runtime_status_pending_changes_sorted_capped_and_fail_closed() -> None:
    """#273 pendingChanges sort by key, cap 128, malformed rows unload config."""
    runtime = NarrativeRuntime()
    runtime.enable()

    many = [
        {
            "key": f"commentary.detector.slot_{index:03d}.threshold",
            "boundary": "next_stream",
            "desiredGeneration": 4,
        }
        for index in range(140, 0, -1)
    ]
    runtime._config_ledger = {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 4,
        "desiredHash": "sha256:" + ("a" * 64),
        "effectiveHash": "sha256:" + ("b" * 64),
        "applySequence": 9,
        "pendingChanges": many,
    }
    pending = project_runtime_status(runtime.status())["config"]["pendingChanges"]
    assert len(pending) == 128
    keys = [row["key"] for row in pending]
    assert keys == sorted(keys)
    assert keys[0] == "commentary.detector.slot_001.threshold"
    assert keys[-1] == "commentary.detector.slot_128.threshold"

    runtime._config_ledger = {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 4,
        "desiredHash": "sha256:" + ("a" * 64),
        "effectiveHash": "sha256:" + ("b" * 64),
        "applySequence": 9,
        "pendingChanges": [
            {"key": "commentary.tts.voice", "boundary": "next_utterance", "desiredGeneration": 4},
            {"key": "broken", "boundary": "next_stream"},  # missing desiredGeneration
        ],
    }
    unloaded = project_runtime_status(runtime.status())["config"]
    assert unloaded["desiredGeneration"] == 0
    assert unloaded["applySequence"] == 0
    assert unloaded["pendingChanges"] == []


def test_project_runtime_status_episodes_follow_registry_counts() -> None:
    """#273 live episode counters from EpisodeRegistry snapshot."""
    from test_episode_registry import _intent

    from irswitch.events.episode_registry import ACTIVE_CAP, RESOLVED_CAP, EpisodeRegistry

    registry = EpisodeRegistry()
    opened = registry.open(_intent())
    assert opened.episode is not None
    activated = registry.activate(
        opened.episode.episode_id,
        now_ms=2_000,
        source_refs=("test:activate",),
    )
    assert activated.episode is not None
    assert activated.episode.state == "active"
    cand = registry.open(_intent(semantic=("rival", "car.7"), correlation=("corr:2",)))
    assert cand.episode is not None
    assert cand.episode.state == "candidate"

    runtime = NarrativeRuntime(episode_registry=registry)
    runtime.enable()
    episodes = project_runtime_status(runtime.status())["episodes"]
    assert episodes == {
        "active": 1,
        "candidate": 1,
        "suspended": 0,
        "retainedCurrentCapacity": int(ACTIVE_CAP),
        "resolved": 0,
        "resolvedCapacity": int(RESOLVED_CAP),
    }

    resolved = registry.resolve(
        activated.episode.episode_id,
        now_ms=5_000,
        reason="outcome_observed",
    )
    assert resolved.episode is not None
    episodes_after = project_runtime_status(runtime.status())["episodes"]
    assert episodes_after["active"] == 0
    assert episodes_after["candidate"] == 1
    assert episodes_after["resolved"] == 1


def test_project_runtime_status_by_tape_channel_follows_opportunity_counters() -> None:
    """#273 live byTapeChannel from OpportunityQueue channel counters."""
    import json
    from pathlib import Path

    from irswitch.events.opportunity_queue import ChannelCounters, OpportunityQueue

    queue = OpportunityQueue()
    queue._counters["race.battle.closing"] = ChannelCounters(
        tape_channel="race.battle.closing",
        kick=3,
        queued=2,
        selected=1,
        consumed=1,
        expired=1,
        spoken=2,
    )
    # Zero-only channels must not appear in the status projection.
    queue._counters["race.timing.lap"] = ChannelCounters(tape_channel="race.timing.lap")
    runtime = NarrativeRuntime(opportunity_queue=queue)
    runtime.enable()
    by_channel = project_runtime_status(runtime.status())["byTapeChannel"]
    golden = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_by_tape_channel.json"
        ).read_text(encoding="utf-8")
    )
    assert by_channel == golden
    assert "race.timing.lap" not in by_channel


def test_by_tape_channel_projection_filters_zeros_sorts_and_caps() -> None:
    """#273 byTapeChannel: drop all-zero rows, sort by id, cap at 128."""
    from dataclasses import replace

    from irswitch.events.narrative_ingress import _by_tape_channel_projection
    from irswitch.events.opportunity_queue import BY_TAPE_CHANNEL_STATUS_CAP

    raw: dict[str, dict[str, int]] = {
        "z.zero": {
            "kick": 0,
            "accepted": 0,
            "queued": 0,
            "selected": 0,
            "started": 0,
            "expired": 0,
        }
    }
    for index in range(BY_TAPE_CHANNEL_STATUS_CAP + 2):
        raw[f"ch.{index:03d}"] = {
            "kick": 1 if index % 2 == 0 else 0,
            "accepted": 0,
            "queued": 0,
            "selected": 0,
            "started": 0,
            "expired": 0 if index % 2 == 0 else 1,
        }
    projected = _by_tape_channel_projection(
        replace(NarrativeRuntime().status(), by_tape_channel=raw)
    )

    assert "z.zero" not in projected
    assert list(projected) == sorted(projected)
    assert len(projected) == BY_TAPE_CHANNEL_STATUS_CAP
    assert "ch.000" in projected
    assert f"ch.{BY_TAPE_CHANNEL_STATUS_CAP - 1:03d}" in projected
    assert f"ch.{BY_TAPE_CHANNEL_STATUS_CAP:03d}" not in projected
    assert f"ch.{BY_TAPE_CHANNEL_STATUS_CAP + 1:03d}" not in projected
    assert projected["ch.000"]["kick"] == 1
    assert projected["ch.001"]["expired"] == 1


def test_cohort_funnel_rates_omit_non_applicable_stages() -> None:
    """#273 cohort-valid rates: N/A stages are None, not zero failures."""
    from irswitch.events.opportunity_queue import cohort_funnel_rates

    candidate = cohort_funnel_rates(
        {
            "kick": 3,
            "accepted": 2,
            "queued": 2,
            "selected": 1,
            "started": 1,
            "expired": 1,
        }
    )
    assert candidate == {
        "kickToAccepted": 2 / 3,
        "acceptedToQueued": 1.0,
        "selectedToStarted": 1.0,
    }

    # Visual-only ends after accepted — queued stage is N/A, not a 0.0 failure.
    visual_only = cohort_funnel_rates(
        {
            "kick": 2,
            "accepted": 1,
            "queued": 0,
            "selected": 0,
            "started": 0,
            "expired": 0,
        }
    )
    assert visual_only["kickToAccepted"] == 0.5
    assert visual_only["acceptedToQueued"] is None
    assert visual_only["selectedToStarted"] is None

    # Silence / successor: no kick cohort → kick→accepted is N/A.
    silence = cohort_funnel_rates(
        {
            "kick": 0,
            "accepted": 0,
            "queued": 1,
            "selected": 1,
            "started": 1,
            "expired": 0,
        }
    )
    assert silence["kickToAccepted"] is None
    assert silence["acceptedToQueued"] is None
    assert silence["selectedToStarted"] == 1.0


def test_session_identity_all_or_none_clears_on_incomplete_timeline() -> None:
    """Incomplete APPLY_CONTEXT timeline clears the whole session-identity set."""
    from irswitch.events.narrative_runtime import _session_identity_from_timeline

    complete = _timeline()
    plan, ref, occ, lin, stage = _session_identity_from_timeline(complete)
    assert plan is not None and ref is not None
    assert occ == "1:race:0" and lin == "1:race:0" and stage == "race"

    incomplete = dict(complete)
    incomplete.pop("sessionRef")
    assert _session_identity_from_timeline(incomplete) == (None, None, None, None, None)

    bad_stage = dict(complete)
    bad_stage["stage"] = "warmup"
    assert _session_identity_from_timeline(bad_stage) == (None, None, None, None, None)


def test_project_runtime_status_incomplete_context_clears_live_session() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    assert ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:session-ok",
        enqueued_mono_ms=3_000,
    ).accepted
    assert runtime.reduce_next() is not None
    assert project_runtime_status(runtime.status())["timeline"]["sessionPlan"] is not None

    broken = dict(_timeline(revision=4))
    broken["sessionRef"] = None
    assert ingress.admit_context_publication(
        timeline=broken,
        fact_view=_fact_view(2, revision=10),
        events=(_event(1, fanout=12, fact_revision=10),),
        fanout_stream_sequence=12,
        command_id_prefix="pub:session-bad",
        enqueued_mono_ms=4_000,
    ).accepted
    assert runtime.reduce_next() is not None
    timeline = project_runtime_status(runtime.status())["timeline"]
    assert timeline["sessionPlan"] is None
    assert timeline["sessionRef"] is None
    assert timeline["occurrenceId"] is None
    assert timeline["lineageId"] is None
    assert timeline["stage"] is None
    assert timeline["broadcastEpoch"] == 4


def test_project_runtime_decisions_selected_golden() -> None:
    import json
    from pathlib import Path

    from irswitch.events.narrative_decision_projection import project_runtime_decisions

    golden_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "commentary_runtime"
        / "decisions_selected.json"
    )
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    projection = project_runtime_decisions(expected["decisions"], runtime=True)
    assert projection == expected


def test_project_runtime_decisions_story_successor_golden() -> None:
    """#273: story_successor decisions are first-class beside event_opportunity."""
    import json
    from pathlib import Path

    from test_story_director import _cand as _director_cand
    from test_story_director import _world as _director_world

    from irswitch.events.beat_plan import CandidateOrder
    from irswitch.events.narrative_decision_projection import (
        build_runtime_decision_entry,
        project_runtime_decisions,
    )
    from irswitch.events.story_director import StoryDirector

    expected = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "decisions_story_successor.json"
        ).read_text(encoding="utf-8")
    )
    primary = _director_cand(
        beat_id="battle.pursuit",
        episode_id="battle-ahead:3:17:22:4",
        source="story_successor",
        relation="continues_focused_episode",
        opportunity_id=None,
        tape_channel="race.battle.closing",
        candidate_order=CandidateOrder(421, 0),
        continuation_base=70.0,
        base_priority=70.0,
    )
    decision = StoryDirector().evaluate(
        _director_world(
            focused_episode_id="battle-ahead:3:17:22:4",
            now_ms=15_000,
            impulse="post_beat",
        ),
        (primary,),
    )
    entry = build_runtime_decision_entry(
        decision,
        (primary,),
        reducer_sequence=422,
        at_mono_ms=90_410,
    )
    assert project_runtime_decisions([entry], runtime=True) == expected


def test_build_terminal_decision_entry_expired_ttl_golden() -> None:
    """#273: expired opportunities project decision=expired + terminalReason."""
    import json
    from pathlib import Path

    from irswitch.events.beat_plan import CandidateOrder
    from irswitch.events.narrative_decision_projection import (
        build_terminal_decision_entry,
        project_runtime_decisions,
    )

    expected = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "decisions_expired_ttl.json"
        ).read_text(encoding="utf-8")
    )
    entry = build_terminal_decision_entry(
        decision="expired",
        reason="expired_ttl",
        terminal_reason="expired_ttl",
        reducer_sequence=430,
        at_mono_ms=95_000,
        beat_id="battle.approach",
        episode_id="battle-ahead:3:17:22:4",
        opportunity_id="opp:401",
        tape_channel="race.battle.closing",
        candidate_source="event_opportunity",
        candidate_order=CandidateOrder(417, 0).to_dict(),
        relation="updates_active_episode",
        urgency="story",
        score=0.0,
    )
    assert project_runtime_decisions([entry], runtime=True) == expected


def test_project_runtime_status_opportunities_queue_follows_live_counts() -> None:
    """#273: queues.opportunities exposes live depth/expired/evicted."""
    import json
    from pathlib import Path

    from irswitch.events.opportunity_queue import ChannelCounters, OpportunityQueue

    queue = OpportunityQueue()
    queue._counters["race.battle.closing"] = ChannelCounters(
        tape_channel="race.battle.closing",
        expired=3,
        evicted=1,
    )
    queue._counters["race.timing.lap"] = ChannelCounters(
        tape_channel="race.timing.lap",
        expired=1,
        queued=2,
    )
    queue._live = [object(), object()]  # type: ignore[list-item]
    runtime = NarrativeRuntime(opportunity_queue=queue)
    runtime.enable()
    opportunities = project_runtime_status(runtime.status())["queues"]["opportunities"]
    expected = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "commentary_runtime"
            / "status_opportunities_queue.json"
        ).read_text(encoding="utf-8")
    )
    assert opportunities == expected


def test_project_runtime_decisions_clamps_limit_newest_first() -> None:
    from irswitch.events.narrative_decision_projection import project_runtime_decisions

    entries = [
        {
            "reducerSequence": seq,
            "atMonoMs": seq,
            "decision": "silence",
            "reason": "no_candidate",
            "beatId": None,
            "episodeId": None,
            "opportunityId": None,
            "tapeChannel": None,
            "candidateSource": None,
            "candidateOrder": None,
            "relation": None,
            "urgency": None,
            "score": None,
            "threshold": 35.0,
            "runnerUp": None,
            "terminalReason": None,
        }
        for seq in (3, 2, 1)
    ]
    projection = project_runtime_decisions(entries, runtime=True, limit=2)
    assert [item["reducerSequence"] for item in projection["decisions"]] == [3, 2]
    assert (
        project_runtime_decisions(entries, runtime=True, limit=0)["decisions"][0]["reducerSequence"]
        == 3
    )
    assert len(project_runtime_decisions(entries, runtime=True, limit=999)["decisions"]) == 3
    assert project_runtime_decisions([], runtime=False) == {
        "schemaVersion": "commentary-runtime/2",
        "runtime": False,
        "decisions": [],
    }


def test_build_runtime_decision_entry_selected_and_silence() -> None:
    from test_story_director import _cand as _director_cand
    from test_story_director import _world as _director_world

    from irswitch.events.beat_plan import CandidateOrder
    from irswitch.events.narrative_decision_projection import build_runtime_decision_entry
    from irswitch.events.story_director import StoryDirector

    director = StoryDirector()
    primary = _director_cand(
        source="event_opportunity",
        opportunity_id="opp:401",
        from_accepted_event=True,
        relation="updates_active_episode",
        tape_channel="race.battle.closing",
        candidate_order=CandidateOrder(417, 0),
    )
    runner = _director_cand(
        beat_id="battle.pursuit",
        source="event_opportunity",
        opportunity_id="opp:402",
        from_accepted_event=True,
        base_priority=50.0,
        candidate_order=CandidateOrder(417, 1),
    )
    selected = director.evaluate(_director_world(now_ms=15_000), (primary, runner))
    entry = build_runtime_decision_entry(
        selected,
        (primary, runner),
        reducer_sequence=418,
        at_mono_ms=90_231,
    )
    assert entry["decision"] == "selected"
    assert entry["beatId"] == "battle.approach"
    assert entry["opportunityId"] == "opp:401"
    assert entry["candidateOrder"] == {"reducerSequence": 417, "sourceOrdinal": 0}
    assert entry["runnerUp"] is not None
    assert entry["runnerUp"]["beatId"] == "battle.pursuit"
    assert entry["threshold"] == 35.0
    assert entry["terminalReason"] is None
    assert entry["atMonoMs"] == 90_231

    silenced = director.evaluate(
        _director_world(lane="building", impulse="timer", now_ms=15_000),
        (primary,),
    )
    quiet = build_runtime_decision_entry(
        silenced,
        (primary,),
        reducer_sequence=419,
        at_mono_ms=90_231,
    )
    assert quiet["decision"] == "silence"
    assert quiet["beatId"] is None
    assert quiet["episodeId"] is None
    assert quiet["opportunityId"] is None
    assert quiet["tapeChannel"] is None
    assert quiet["candidateSource"] is None
    assert quiet["candidateOrder"] is None
    assert quiet["relation"] is None
    assert quiet["urgency"] is None
    assert quiet["score"] is None
    assert quiet["runnerUp"] is None


def test_build_runtime_decision_entry_replaced_precommit() -> None:
    from test_story_director import _cand as _director_cand

    from irswitch.events.beat_plan import CandidateOrder
    from irswitch.events.narrative_decision_projection import build_runtime_decision_entry
    from irswitch.events.story_director import CandidateRecord, DirectorDecision

    primary = _director_cand(
        source="event_opportunity",
        opportunity_id="opp:401",
        from_accepted_event=True,
        candidate_order=CandidateOrder(417, 0),
    )
    selected = CandidateRecord(
        beat_id=primary.beat_id,
        episode_id=primary.episode_id,
        episode_revision=primary.episode_revision,
        source=primary.source,
        eligible=True,
        reject_reason=None,
        score=70.0,
        candidate_order=primary.candidate_order,
    )
    decision = DirectorDecision(
        reason="replaced_precommit",
        selected=selected,
        records=(selected,),
        speech="speak",
        schema_version="director-decision/2",
        planning_cycle_id=1,
        cycle_attempt_ordinal=1,
    )
    entry = build_runtime_decision_entry(
        decision,
        (primary,),
        reducer_sequence=420,
        at_mono_ms=90_231,
    )
    assert entry["decision"] == "replaced"
    assert entry["reason"] == "replaced_precommit"
    assert entry["beatId"] == primary.beat_id
    assert entry["opportunityId"] == "opp:401"


def test_project_validate_response_supported_golden() -> None:
    import json
    from pathlib import Path

    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    expected = json.loads((fixtures / "validate_supported.json").read_text(encoding="utf-8"))
    assert project_validate_response(request) == expected


def test_project_validate_response_actor_reversed_golden() -> None:
    import json
    from pathlib import Path

    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    request = {
        **request,
        "text": "Morgan is closing on the driver, the gap at one point four seconds.",
    }
    expected = json.loads((fixtures / "validate_rejected.json").read_text(encoding="utf-8"))
    assert project_validate_response(request) == expected


def test_project_validate_response_rejects_malformed_request() -> None:
    from irswitch.contracts.primitives import ContractViolation
    from irswitch.events.narrative_validate_projection import project_validate_response

    try:
        project_validate_response({"schemaVersion": "commentary-runtime/2"})
    except ContractViolation:
        return
    raise AssertionError("expected ContractViolation")


def test_project_validate_response_rejects_incomplete_atomic_fact() -> None:
    """Offline validate reuses AtomicFact.from_dict — subset facts are 400 (#273)."""

    import copy
    import json
    from pathlib import Path

    from irswitch.contracts.primitives import ContractViolation
    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    request = copy.deepcopy(request)
    request["factBindings"][0].pop("attributes")
    try:
        project_validate_response(request)
    except ContractViolation as exc:
        assert "AtomicFact" in str(exc) or "factBindings" in str(exc)
        return
    raise AssertionError("expected ContractViolation for incomplete AtomicFact")


def test_project_validate_response_rejects_unknown_fact_field() -> None:
    import copy
    import json
    from pathlib import Path

    from irswitch.contracts.primitives import ContractViolation
    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    request = copy.deepcopy(request)
    request["factBindings"][0]["extraField"] = "nope"
    try:
        project_validate_response(request)
    except ContractViolation as exc:
        assert "unknown" in str(exc).lower() or "AtomicFact" in str(exc)
        return
    raise AssertionError("expected ContractViolation for unknown AtomicFact field")


def test_project_validate_response_rejects_unregistered_predicate() -> None:
    import copy
    import json
    from pathlib import Path

    from irswitch.contracts.primitives import ContractViolation
    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    request = copy.deepcopy(request)
    request["factBindings"][0]["predicate"] = "not.a.registered.predicate"
    try:
        project_validate_response(request)
    except ContractViolation as exc:
        assert "unregistered" in str(exc).lower() or "predicate" in str(exc).lower()
        return
    raise AssertionError("expected ContractViolation for unregistered predicate")


def test_project_validate_response_rejects_unknown_request_field() -> None:
    import json
    from pathlib import Path

    from irswitch.contracts.primitives import ContractViolation
    from irswitch.events.narrative_validate_projection import project_validate_response

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    request = {**request, "force": True}
    try:
        project_validate_response(request)
    except ContractViolation:
        return
    raise AssertionError("expected ContractViolation for unknown ValidateRequest field")
