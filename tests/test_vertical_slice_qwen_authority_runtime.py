"""#278 Slice 21 — offline F40 Qwen request/stream/deadline authority drivers.

Consumes frozen machine rows and proves one Qwen authority for exact prompt
projection, one terminal result, fail-closed SSE, deadline authority, protected
deadline admission under mailbox pressure, no request queue, duplicate result
protocol, warmup without retry, and exact latency metrics. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import binascii
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_context_batch import _context_command
from test_narrative_runtime import _result_for
from test_qwen_transport import _chunks, _goldens, _intent, _ready_component

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.primitives import ContractViolation, canonical_json
from irswitch.events.qwen_transport import (
    SCHEMA_REQUEST,
    WARMUP_TIMEOUT_MS,
    AttemptReducer,
    FakeTransport,
    LlmComponent,
    RealizerService,
    build_qwen_backend_request,
    build_realization_request,
    latency_metrics,
    parse_sse,
    warmup_request_body,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE21_IDS = ("F40",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_qwen_authority_builder_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    machine_path = str(MACHINE)
    if machine_path not in sys.path:
        sys.path.insert(0, machine_path)
    spec = importlib.util.spec_from_file_location(module_name, BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE21_IDS)
def test_slice21_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f40_qwen_request_stream_and_deadline_have_one_authority(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F40: one authority for prompt, SSE, deadline, mailbox, warmup, metrics."""

    expected = set(fixtures_by_id["F40"]["expectations"])
    observed: set[str] = set()
    goldens = _goldens()

    authored = goldens["commonRequests"][0]
    qwen = goldens["commonRequests"][1]
    built_authored = build_realization_request(
        _intent(backend="authored", request_ordinal=1, deadline_mono_ms=94_000)
    )
    built_qwen = build_realization_request(_intent())
    assert built_authored.schema_version == SCHEMA_REQUEST
    assert built_authored.to_dict() == authored
    assert built_qwen.to_dict() == qwen
    backend = build_qwen_backend_request(_intent())
    assert backend == goldens["canonicalBackendRequest"]
    assert bytes.fromhex(goldens["http"]["requestBytesHex"]) == canonical_json(backend).encode(
        "utf-8"
    )
    assert goldens["http"]["environmentProxy"] is False
    assert goldens["http"]["redirects"] is False
    observed.add("exact_prompt_projection")

    for row in goldens["deadlineRaces"]:
        reducer = AttemptReducer()
        dispositions = [reducer.reduce(kind) for kind in row["reducerOrder"]]
        assert dispositions[0] == "terminal"
        assert dispositions[1] == row["lateDisposition"]
        assert reducer.terminal_attempts == row["terminalAttempts"]
    observed.add("one_terminal_result")
    observed.add("deadline_authority")

    for row in goldens["sse"]["invalid"]:
        parsed = parse_sse([binascii.unhexlify(item) for item in row["chunksHex"]])
        assert parsed.reason == row["reason"]
        assert parsed.text is None
    for row in goldens["sse"]["valid"]:
        parsed = parse_sse([binascii.unhexlify(item) for item in row["chunksHex"]])
        assert parsed.reason is None
        assert parsed.text == row["text"]
    observed.add("fail_closed_sse")

    service = RealizerService(
        transport=FakeTransport(chunks=_chunks("role_content_usage_done"), hold=True)
    )
    admitted = service.try_start(_intent(), component=_ready_component())
    busy = service.try_start(
        _intent(request_ordinal=3, now_ms=91_010), component=_ready_component()
    )
    finished = service.finish(now_ms=91_200)
    assert admitted.outcome == "admitted"
    assert busy.reason == "realization_transport"
    assert busy.result is None
    assert finished.outcome == "succeeded"
    assert finished.result is not None
    assert finished.result.text == "Alex is closing on Morgan."
    assert service.active_count == 0
    late = RealizerService(
        transport=FakeTransport(chunks=_chunks("role_content_usage_done"))
    ).try_start(_intent(now_ms=92_500), component=_ready_component())
    assert late.outcome == "failed"
    assert late.reason == "realization_timeout"
    cancelled = RealizerService(
        transport=FakeTransport(chunks=_chunks("role_content_usage_done"))
    ).try_start(_intent(cancelled=True, now_ms=91_000), component=_ready_component())
    assert cancelled.outcome == "cancelled"
    observed.add("no_request_queue")

    mailbox = NarrativeMailbox()
    assert mailbox.admit(_context_command("ctx:f40")).reason == "accepted"
    for index in range(NarrativeMailbox.PROTECTED_CELLS):
        deadline = NarrativeCommand.realization_deadline(
            f"deadline:f40:{index}",
            10_000 + index,
            request_id=f"request:f40:{index + 1}",
            request_ordinal=index + 1,
            dispatch_generation=1,
            deadline_mono_ms=11_000 + index,
        )
        assert deadline.protected is True
        assert mailbox.admit(deadline).reason == "accepted"
    overflow = NarrativeCommand.realization_deadline(
        "deadline:f40:overflow",
        20_000,
        request_id="request:f40:overflow",
        request_ordinal=99,
        dispatch_generation=1,
        deadline_mono_ms=21_000,
    )
    recovered = mailbox.admit(overflow)
    assert recovered.reason == "mailbox_recovery"
    assert recovered.command.kind == "MAILBOX_RECOVERY"
    effects = recovered.command.payload["safetyEffects"]
    assert any(effect["kind"] == "REALIZATION_DEADLINE_ELAPSED" for effect in effects)
    observed.add("protected_deadline")

    duplicate_mailbox = NarrativeMailbox()
    result = _result_for(
        {
            "requestId": "request:f40:dup",
            "requestOrdinal": 1,
            "dispatchGeneration": 1,
        }
    )
    first = NarrativeCommand.realization_result(
        "result:f40:dup",
        "REALIZATION_SUCCEEDED",
        30_000,
        request_id="request:f40:dup",
        request_ordinal=1,
        dispatch_generation=1,
        result=result,
    )
    assert duplicate_mailbox.admit(first).reason == "accepted"
    assert duplicate_mailbox.admit(first).reason == "duplicate"
    changed = _result_for(
        {
            "requestId": "request:f40:dup",
            "requestOrdinal": 1,
            "dispatchGeneration": 1,
        },
        text="Different realization text.",
    )
    conflict = NarrativeCommand.realization_result(
        "result:f40:dup",
        "REALIZATION_SUCCEEDED",
        30_000,
        request_id="request:f40:dup",
        request_ordinal=1,
        dispatch_generation=1,
        result=changed,
    )
    with pytest.raises(ContractViolation, match="conflicting"):
        duplicate_mailbox.admit(conflict)
    observed.add("duplicate_protocol")

    body = warmup_request_body("qwen3:4b-instruct-2507-q4_K_M")
    expected_body = dict(goldens["warmup"]["body"])
    expected_body["model"] = "qwen3:4b-instruct-2507-q4_K_M"
    assert body == expected_body
    assert WARMUP_TIMEOUT_MS == goldens["warmup"]["timeoutMs"] == 10_000
    ready = LlmComponent()
    ready.start_preflight(desired_generation=3, warmup=True)
    ready.complete_preflight(generation=3, residency="warmup_succeeded")
    assert ready.qwen_ready is True
    disabled = LlmComponent()
    disabled.start_preflight(desired_generation=4, warmup=False)
    disabled.complete_preflight(generation=4, residency="not_requested")
    assert disabled.qwen_ready is True
    failed = LlmComponent()
    failed.start_preflight(desired_generation=5, warmup=True)
    failed.complete_preflight(generation=5, residency="unavailable")
    assert failed.qwen_ready is False
    assert failed.authored_ready is True
    stale = LlmComponent()
    stale.start_preflight(desired_generation=6, warmup=True)
    assert (
        stale.complete_preflight(generation=5, residency="warmup_succeeded")
        == "stale_generation_noop"
    )
    assert stale.qwen_ready is False
    transport_failed = RealizerService(transport=FakeTransport(fail=True)).try_start(
        _intent(authored_text="Alex is closing on Morgan."),
        component=_ready_component(),
    )
    assert transport_failed.outcome == "failed"
    assert transport_failed.reason == "realization_transport"
    assert transport_failed.result is not None
    assert transport_failed.result.text is None
    assert transport_failed.result.backend == "qwen_compiled"
    observed.add("warmup_no_retry")

    metrics = latency_metrics(
        dispatched_mono_ms=91_000,
        transport_started_mono_ms=91_010,
        response_started_mono_ms=91_040,
        first_content_mono_ms=91_080,
        completed_mono_ms=91_200,
        result_reduced_mono_ms=91_220,
        planned_mono_ms=90_000,
    )
    assert metrics == {
        "admissionMs": 10,
        "ttfbMs": 30,
        "ttftMs": 70,
        "generationMs": 120,
        "totalMs": 190,
        "reducerLagMs": 20,
        "planToResultMs": 1220,
        "timeoutElapsedMs": None,
    }
    missing = latency_metrics(
        dispatched_mono_ms=91_000,
        transport_started_mono_ms=91_010,
        response_started_mono_ms=None,
        first_content_mono_ms=None,
        completed_mono_ms=91_200,
        result_reduced_mono_ms=91_220,
        planned_mono_ms=90_000,
        timeout_elapsed_ms=1_500,
    )
    assert missing["ttfbMs"] is None
    assert missing["ttftMs"] is None
    assert missing["timeoutElapsedMs"] == 1_500
    observed.add("exact_metrics")

    assert observed == expected
