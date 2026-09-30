import asyncio
import json
from types import SimpleNamespace

import pytest
from test_remote_commentary_runtime import admit, current_batch, drain, reply, setup

from irswitch.commentary.live_trace import LiveCommentaryTrace
from irswitch.events.commentary_microplan import plan_from_accepted
from irswitch.events.envelope import make_envelope
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.pipeline import AcceptedRecord
from irswitch.race.runtime import RaceRuntime


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_tts", [False, True])
async def test_trace_covers_input_decision_and_actual_tts_outcome(tmp_path, monkeypatch, fail_tts):
    trace = LiveCommentaryTrace(tmp_path, secrets=lambda: ["unit-secret"])
    _, client, sink, runtime = setup(monkeypatch)
    client._trace = trace.submit
    runtime._on_trace = trace.submit
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)
    assert plan is not None

    async def post(*args):
        return reply(plan.allowed[0], plan)

    def fail(*args):
        raise RuntimeError("synthetic playback failure")

    monkeypatch.setattr(client, "_post", post)
    if fail_tts:
        monkeypatch.setattr(sink, "enqueue", fail)
    trace.start()
    admit(runtime, batch)
    await drain(runtime, 60)
    await client.close()
    await runtime.wait_effects_idle()
    await trace.close()
    raw = trace.path.read_text(encoding="utf-8")
    assert "unit-secret" not in raw and "Authorization" not in raw
    records = [json.loads(line) for line in raw.splitlines()]
    kinds = {r["recordType"] for r in records}
    assert {
        "model_input",
        "model_outcome",
        "director_decision",
        "realization_requested",
        "speech_selection",
    } <= kinds
    reductions = [r["payload"] for r in records if r["recordType"] == "runtime_reduction"]
    terminal = next(
        r for r in reductions if r["kind"] == ("SPEECH_FAILED" if fail_tts else "SPEECH_COMPLETED")
    )
    assert terminal["token"]["utteranceId"]
    assert terminal["result"]["disposition"] == "handled"
    assert records[-1]["recordType"] == "trailer"
    assert records[-1]["payload"]["complete"] is True


@pytest.mark.asyncio
async def test_cancelled_attempt_survives_ring_and_trace_redacts(tmp_path, monkeypatch):
    trace = LiveCommentaryTrace(tmp_path, secrets=lambda: ["unit-secret"])
    _, client, _, runtime = setup(monkeypatch)
    client._trace = trace.submit
    entered = asyncio.Event()

    async def post(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(client, "_post", post)
    plan = plan_from_accepted(current_batch().events[0], current_batch())
    assert plan is not None
    trace.start()
    task = asyncio.create_task(client.realize(plan))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    trace.submit("test_redaction", {"text": "prefix unit-secret suffix"})
    # Durable record must not depend on the bounded API ring retaining an attempt.
    client._history.clear()
    await client.close()
    await runtime.wait_effects_idle()
    await trace.close()
    raw = trace.path.read_text(encoding="utf-8")
    assert "unit-secret" not in raw
    records = [json.loads(line) for line in raw.splitlines()]
    assert (
        next(r for r in records if r["recordType"] == "model_outcome")["payload"]["reason"]
        == "cancelled"
    )


@pytest.mark.asyncio
async def test_overflow_and_disk_failure_are_visible_and_do_not_raise(tmp_path, monkeypatch):
    trace = LiveCommentaryTrace(tmp_path, capacity=1)
    trace.start()
    trace.submit("overflow", {})
    assert trace.status()["drops"] == 1

    def disk_full(*args):
        raise OSError("disk full")

    monkeypatch.setattr(trace, "_append", disk_full)
    await trace.close()
    assert trace.status()["error"] == "write_failed"
    assert trace.status()["complete"] is False


@pytest.mark.asyncio
async def test_size_limit_keeps_explicit_incomplete_trailer(tmp_path):
    trace = LiveCommentaryTrace(tmp_path, max_bytes=1)
    trace.start()
    trace.submit("event", {"text": "data"})
    await trace.close()
    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert rows[-1]["payload"]["error"] == "size_limit"
    assert rows[-1]["payload"]["complete"] is False


@pytest.mark.asyncio
async def test_restart_creates_independent_complete_journals(tmp_path):
    trace = LiveCommentaryTrace(tmp_path)
    trace.start()
    first = trace.path
    await trace.close()
    trace.start()
    second = trace.path
    await trace.close()
    assert first != second
    for path in (first, second):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert [row["recordType"] for row in rows] == ["manifest", "trailer"]
        assert rows[-1]["payload"]["complete"] is True


@pytest.mark.asyncio
async def test_suppression_reasons_are_traced(monkeypatch):
    from dataclasses import replace

    from irswitch.events.narrative_realization_bridge import _realize_microplan

    _, client, _, runtime = setup(monkeypatch)
    records = []
    client._trace = lambda kind, payload: records.append((kind, payload))
    plan = plan_from_accepted(current_batch().events[0], current_batch())
    assert plan is not None
    client._busy = True
    assert await client.realize(plan) is None
    assert records[-1][1]["reason"] == "busy"
    client._busy = False
    cfg = replace(client.settings(), speech_enabled=False)
    monkeypatch.setattr(client, "settings", lambda: cfg)
    token = {
        "microplan": plan.to_dict(),
        "requestId": "test",
        "requestOrdinal": 1,
        "dispatchGeneration": 1,
    }
    await _realize_microplan(token, client)
    assert records[-1][0] == "realization_not_attempted"
    assert records[-1][1]["reason"] == "speech_disabled"
    await client.close()
    await runtime.wait_effects_idle()


@pytest.mark.asyncio
async def test_accepted_source_uses_final_pipeline_event_identity():
    config = SimpleNamespace(overlay=OverlaySettings())
    runtime = RaceRuntime(lambda: config, None, OverlayBus(), mode="mock")
    captured = []
    runtime._live_trace = SimpleNamespace(
        submit=lambda kind, payload: captured.append((kind, payload))
    )
    await runtime._tick_race()  # Establish the mock session; its reset clears pending records.

    envelope = make_envelope(
        event_type="FIELD_FACT",
        phase="RESULT",
        mode="RACE",
        monotonic_ms=1000,
        metrics={"fact": "position", "position": 7},
    )
    provisional_id = envelope.event_id
    runtime._pending_stream_records.append(AcceptedRecord(envelope, "trace_test"))
    await runtime._tick_race()

    source = next(
        payload
        for kind, payload in captured
        if kind == "accepted_source" and payload["source"] == "trace_test"
    )
    assert envelope.sequence > 0
    assert envelope.event_id != provisional_id
    assert source["event"]["eventId"] == envelope.event_id
    assert source["event"]["sequence"] == envelope.sequence
    assert source["sessionId"] == envelope.session_id
