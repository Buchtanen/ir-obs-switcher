"""#269 bounded Qwen transport and warm-up."""

from __future__ import annotations

import binascii
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from irswitch.contracts.primitives import canonical_json, canonical_sha256
from irswitch.events import __all__ as events_exports
from irswitch.events.qwen_transport import (
    SCHEMA_REQUEST,
    WARMUP_TIMEOUT_MS,
    AttemptReducer,
    FakeTransport,
    LlmComponent,
    RealizationIntent,
    RealizerService,
    StdlibTransport,
    build_qwen_backend_request,
    build_realization_request,
    latency_metrics,
    load_transport_goldens,
    parse_sse,
    warmup_request_body,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "irswitch" / "events" / "qwen_transport.py"
FIXTURES = ROOT / "tests" / "fixtures" / "qwen_transport"
GOLDENS = ROOT / "docs" / "v2.0.0" / "machine" / "qwen-transport-goldens.json"
HASH = "sha256:" + ("55" * 32)
BUNDLE = "sha256:" + ("88" * 32)


def _goldens() -> dict:
    return load_transport_goldens()


def _prompt() -> dict:
    return dict(_goldens()["compiledPrompt"])


def _intent(**overrides: object) -> RealizationIntent:
    prompt = _prompt()
    values: dict[str, object] = {
        "process_instance_id": "process-1",
        "request_ordinal": 2,
        "dispatch_generation": 7,
        "backend": "qwen_compiled",
        "plan_id": "plan:88",
        "planning_cycle_id": "cycle:44",
        "cycle_attempt_ordinal": 1,
        "bundle_id": "bundle:88",
        "bundle_hash": BUNDLE,
        "compiled_prompt": prompt,
        "component_generation": 3,
        "config_generation": 5,
        "effective_config_hash": HASH,
        "config_apply_sequence": 12,
        "capture_prompt": "hash",
        "capture_completion": True,
        "dispatched_mono_ms": 91_000,
        "deadline_mono_ms": 92_500,
        "beat_id": "battle.approach",
        "episode_revision": 4,
        "model": "qwen3:4b-instruct-2507-q4_K_M",
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 96,
        "seed": 17,
        "pattern_id": "battle.approach:tight:1",
        "render_contract_version": 2,
        "now_ms": 91_000,
    }
    values.update(overrides)
    return RealizationIntent(**values)  # type: ignore[arg-type]


def _ready_component() -> LlmComponent:
    component = LlmComponent()
    component.start_preflight(desired_generation=3, warmup=True)
    component.complete_preflight(generation=3, residency="warmup_succeeded")
    return component


def _chunks(name: str, *, valid: bool = True) -> list[bytes]:
    group = "valid" if valid else "invalid"
    for row in _goldens()["sse"][group]:
        if row["id"] == name:
            return [binascii.unhexlify(item) for item in row["chunksHex"]]
    raise AssertionError(name)


def test_golden_requests_hash_and_backend_bytes() -> None:
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
    assert str(canonical_sha256({k: v for k, v in authored.items() if k != "requestHash"})) == (
        authored["requestHash"]
    )
    backend = build_qwen_backend_request(_intent())
    assert backend == goldens["canonicalBackendRequest"]
    raw = bytes.fromhex(goldens["http"]["requestBytesHex"])
    assert raw == canonical_json(backend).encode("utf-8")
    assert goldens["http"]["environmentProxy"] is False
    assert goldens["http"]["redirects"] is False


def test_one_request_one_candidate_no_queue() -> None:
    service = RealizerService(
        transport=FakeTransport(chunks=_chunks("role_content_usage_done"), hold=True)
    )
    admitted = service.try_start(_intent(), component=_ready_component())
    busy = service.try_start(
        _intent(request_ordinal=3, now_ms=91_010), component=_ready_component()
    )
    finished = service.finish(now_ms=91_200)

    assert admitted.outcome == "admitted"
    assert admitted.result is None
    assert busy.reason == "realization_transport"
    assert busy.result is None
    assert finished.outcome == "succeeded"
    assert finished.result is not None
    assert finished.result.text == "Alex is closing on Morgan."
    assert service.active_count == 0


def test_qwen_sse_valid_goldens() -> None:
    goldens = _goldens()
    for row in goldens["sse"]["valid"]:
        parsed = parse_sse([binascii.unhexlify(item) for item in row["chunksHex"]])
        assert parsed.reason is None
        assert parsed.text == row["text"]
        assert parsed.finish_reason == row["finishReason"]
        assert parsed.usage == (None if row["usage"] is None else tuple(row["usage"]))


def test_qwen_sse_invalid_goldens() -> None:
    for row in _goldens()["sse"]["invalid"]:
        parsed = parse_sse([binascii.unhexlify(item) for item in row["chunksHex"]])
        assert parsed.reason == row["reason"]
        assert parsed.text is None


def test_timeout_and_cancel_fail_closed() -> None:
    service = RealizerService(transport=FakeTransport(chunks=_chunks("role_content_usage_done")))
    late = service.try_start(_intent(now_ms=92_500), component=_ready_component())
    cancelled = service.try_start(
        _intent(cancelled=True, now_ms=91_000), component=_ready_component()
    )

    assert late.outcome == "failed"
    assert late.reason == "realization_timeout"
    assert cancelled.outcome == "cancelled"
    assert cancelled.reason == "realization_cancelled"
    assert late.result is not None and late.result.text is None
    assert cancelled.result is not None and cancelled.result.text is None


def test_transport_failure_does_not_authored_fallback() -> None:
    service = RealizerService(transport=FakeTransport(fail=True))
    step = service.try_start(
        _intent(authored_text="Alex is closing on Morgan."),
        component=_ready_component(),
    )

    assert step.outcome == "failed"
    assert step.reason == "realization_transport"
    assert step.result is not None
    assert step.result.text is None
    assert step.result.backend == "qwen_compiled"


def test_warmup_enabled_disabled_failure_and_stale_generation() -> None:
    body = warmup_request_body("qwen3:4b-instruct-2507-q4_K_M")
    expected = dict(_goldens()["warmup"]["body"])
    expected["model"] = "qwen3:4b-instruct-2507-q4_K_M"
    assert body == expected
    assert WARMUP_TIMEOUT_MS == _goldens()["warmup"]["timeoutMs"] == 10_000

    ready = LlmComponent()
    ready.start_preflight(desired_generation=3, warmup=True)
    assert ready.status == "pending"
    assert ready.qwen_ready is False
    ready.complete_preflight(generation=3, residency="warmup_succeeded")
    assert ready.residency == "warmup_succeeded"
    assert ready.qwen_ready is True

    disabled = LlmComponent()
    disabled.start_preflight(desired_generation=4, warmup=False)
    disabled.complete_preflight(generation=4, residency="not_requested")
    assert disabled.residency == "not_requested"
    assert disabled.qwen_ready is True

    failed = LlmComponent()
    failed.start_preflight(desired_generation=5, warmup=True)
    failed.complete_preflight(generation=5, residency="component_unavailable")
    assert failed.qwen_ready is False
    assert failed.authored_ready is True

    stale = LlmComponent()
    stale.start_preflight(desired_generation=6, warmup=True)
    assert stale.complete_preflight(generation=5, residency="warmup_succeeded") == (
        "stale_generation_noop"
    )
    assert stale.qwen_ready is False


def test_qwen_ineligible_while_generation_pending_authored_ok() -> None:
    pending = LlmComponent()
    pending.start_preflight(desired_generation=3, warmup=True)
    service = RealizerService(transport=FakeTransport(chunks=_chunks("role_content_usage_done")))
    blocked = service.try_start(_intent(), component=pending)
    authored = service.try_start(
        _intent(
            backend="authored",
            request_ordinal=1,
            compiled_prompt=None,
            component_generation=None,
            authored_text="The stream is live.",
        ),
        component=pending,
    )

    assert blocked.reason == "realization_transport"
    assert authored.outcome == "succeeded"
    assert authored.result is not None
    assert authored.result.text == "The stream is live."
    assert authored.result.first_content_mono_ms is None
    assert authored.result.response_started_mono_ms is None


def test_deadline_races_one_terminal_attempt() -> None:
    for row in _goldens()["deadlineRaces"]:
        reducer = AttemptReducer()
        dispositions = [reducer.reduce(kind) for kind in row["reducerOrder"]]
        assert dispositions[0] == "terminal"
        assert dispositions[1] == row["lateDisposition"]
        assert reducer.terminal_attempts == row["terminalAttempts"]


def test_latency_metrics_from_milestones() -> None:
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


def test_no_proxy_no_redirect_local_fake_endpoint() -> None:
    payload = (
        b'data: {"choices":[{"index":0,"delta":{"content":"OK"},'
        b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.server.seen_body = self.rfile.read(length)  # type: ignore[attr-defined]
            self.server.seen_accept = self.headers.get("Accept")  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        transport = StdlibTransport()
        response = transport.post(
            url,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            body=b'{"stream":true}',
            stream=True,
            timeout_ms=1000,
        )
        assert response.status == 200
        assert response.content_type.startswith("text/event-stream")
        assert b"".join(response.chunks) == payload
        assert transport.used_proxies == {}
        assert transport.followed_redirects is False
        parsed = parse_sse(response.chunks)
        assert parsed.text == "OK"
    finally:
        server.shutdown()
        server.server_close()


def test_listening_fixtures_cover_transition_identity_and_expiry() -> None:
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))
    service = RealizerService(transport=FakeTransport(chunks=_chunks("role_content_usage_done")))
    ok = service.try_start(
        _intent(beat_id=transition["beatId"], now_ms=transition["nowMs"]),
        component=_ready_component(),
    )
    assert ok.outcome == transition["expectOutcome"]
    assert ok.result is not None
    assert ok.result.text == transition["expectText"]

    failing = RealizerService(transport=FakeTransport(fail=True))
    first = failing.try_start(
        _intent(beat_id=identity["beatId"], episode_revision=identity["episodeRevision"]),
        component=_ready_component(),
    )
    retry = failing.try_start(
        _intent(
            beat_id=identity["beatId"],
            episode_revision=identity["episodeRevision"],
            request_ordinal=3,
        ),
        component=_ready_component(),
    )
    assert first.reason == identity["expectFirstReason"]
    assert retry.reason == identity["expectRetryReason"]

    late = RealizerService(transport=FakeTransport(chunks=_chunks("role_content_usage_done")))
    timed = late.try_start(
        _intent(now_ms=expiry["nowMs"], deadline_mono_ms=expiry["deadlineMonoMs"]),
        component=_ready_component(),
    )
    assert timed.reason == expiry["expectReason"]


def test_transport_is_not_exported_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "qwen_transport" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay"):
        assert banned not in source
    assert "FactView" not in source
    assert source.count("try_start") >= 1
