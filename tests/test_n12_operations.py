from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

import pytest

from irswitch.events.async_fanout import AsyncEventFanout, ConsumerRecoveryRequired
from irswitch.events.envelope import make_envelope
from irswitch.events.replay import N12ReplayWriter, load_n12_replay
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    ConfigUpdate,
    FrozenAcceptedEventBatch,
    SessionReset,
    canonical_json_bytes,
    event_ids,
    freeze_accepted_event,
    freeze_config,
    freeze_context,
)
from irswitch.events.worker import WorkerSupervisor


def _batch(
    stream_sequence: int,
    event_sequence: int,
    *,
    origin_ms: int,
    coalescible: bool = False,
) -> FrozenAcceptedEventBatch:
    phase = "UPDATE" if coalescible else "RESULT"
    event = make_envelope(
        event_type="HUNTING" if coalescible else "LAP_COMPLETE",
        phase=phase,
        mode="RACE",
        event_id=f"session:event:{event_sequence}",
        sequence=event_sequence,
        session_id="session",
        priority=20 if coalescible else 50,
        monotonic_ms=origin_ms + event_sequence,
        dedupe_key="relation",
        correlation_id="relation",
    )
    accepted = freeze_accepted_event(
        event,
        audiences=("overlay", "commentary"),
        source="event_engine",
        source_ordinal=0,
        coalesce_key=("session", "front", "5", "8", "1", "HUNTING") if coalescible else None,
    )
    context = freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": 1,
            "session_id": "session",
            "captured_monotonic_ms": origin_ms,
            "identity": {},
            "race": {},
            "bio": {"bpm": 142},
            "story": {},
            "situation": {},
            "config": {},
        }
    )
    return FrozenAcceptedEventBatch(
        stream_sequence,
        "session",
        event_sequence,
        origin_ms + event_sequence,
        1,
        context,
        (accepted,),
    )


@pytest.mark.asyncio
async def test_replay_bundle_is_canonical_and_drives_both_subscriptions(
    tmp_path: Path,
) -> None:
    origin = 10_000
    path = tmp_path / "n12.jsonl"
    with N12ReplayWriter(
        path,
        source_commit="abc123",
        config_generation=2,
        config_digest="digest",
        locale="cs",
        monotonic_origin_ms=origin,
    ) as writer:
        writer.record(SessionReset("old", "session", "test", 1))
        writer.record(_batch(2, 1, origin_ms=origin))
        writer.record(ConfigUpdate(3, freeze_config({"generation": 3}), 3))
        writer.record_expected(
            overlay_wire_ids=["session:event:1"],
            commentary_decision_ids=["session:event:1"],
            commentary_speech_ids=["session:event:1"],
        )

    raw_lines = path.read_bytes().splitlines()
    assert all(line == canonical_json_bytes(json.loads(line)) for line in raw_lines)
    rows = [json.loads(line) for line in raw_lines]
    assert [row["row"] for row in rows] == [
        "header",
        "control",
        "context",
        "events",
        "control",
        "expected",
    ]

    fanout = AsyncEventFanout()
    overlay = fanout.subscribe("overlay")
    commentary = fanout.subscribe("commentary")
    bundle = load_n12_replay(path)
    await bundle.replay(fanout)
    overlay_items = [await overlay.get() for _ in range(3)]
    commentary_items = [await commentary.get() for _ in range(3)]
    assert [event_ids(item) for item in overlay_items] == [
        event_ids(item) for item in commentary_items
    ]
    assert event_ids(overlay_items[1]) == ("session:event:1",)
    assert bundle.expected[0]["commentary_speech_ids"] == ["session:event:1"]


def test_full_queue_500_batch_publication_meets_n12_deadline() -> None:
    origin = int(time.monotonic() * 1000)
    fanout = AsyncEventFanout()
    fanout.subscribe("overlay", capacity=4)
    fanout.subscribe("commentary", capacity=4)
    samples: list[float] = []
    for sequence in range(1, 501):
        started = time.perf_counter()
        fanout.publish(
            _batch(
                sequence,
                sequence,
                origin_ms=origin,
                coalescible=True,
            )
        )
        samples.append(time.perf_counter() - started)
    p95 = statistics.quantiles(samples, n=20)[18]
    status = fanout.status_snapshot()
    assert max(samples) < 0.05
    assert p95 < 0.2  # default race poll interval (5 Hz)
    for consumer in status["consumers"].values():
        assert consumer["depth"] <= consumer["capacity"]
        assert consumer["coalesced"] == 499
        assert consumer["overflows"] == 0


@pytest.mark.asyncio
async def test_protected_overflow_requests_restart_and_preserves_incoming_item() -> None:
    origin = int(time.monotonic() * 1000)
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("overlay", capacity=1)
    fanout.publish(_batch(1, 1, origin_ms=origin))
    fanout.publish(_batch(2, 2, origin_ms=origin))

    with pytest.raises(ConsumerRecoveryRequired):
        await subscription.get()
    recovered = await subscription.get()
    assert event_ids(recovered) == ("session:event:2",)
    status = fanout.status_snapshot()["consumers"]["overlay"]
    assert status["restart_requests"] == 1
    assert status["recovery_discards"] == 1


@pytest.mark.asyncio
async def test_supervisor_restarts_same_worker_instance_without_stopping_sibling() -> None:
    class _Flaky:
        def __init__(self) -> None:
            self.calls = 0
            self.state = {"cooldown": 42}
            self.running = asyncio.Event()

        async def run(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("injected crash")
            self.running.set()
            await asyncio.Event().wait()

    flaky = _Flaky()
    sibling_alive = asyncio.Event()

    async def sibling() -> None:
        sibling_alive.set()
        await asyncio.Event().wait()

    supervisor = WorkerSupervisor("flaky", flaky.run, initial_backoff_s=0)
    supervised_task = asyncio.create_task(supervisor.run())
    sibling_task = asyncio.create_task(sibling())
    try:
        await asyncio.wait_for(flaky.running.wait(), timeout=0.2)
        assert sibling_alive.is_set()
        assert flaky.calls == 2
        assert flaky.state == {"cooldown": 42}
        assert supervisor.restarts == 1
    finally:
        supervised_task.cancel()
        sibling_task.cancel()
        await asyncio.gather(supervised_task, sibling_task, return_exceptions=True)


def test_n12_architecture_has_no_private_overlay_commentary_chain() -> None:
    root = Path(__file__).parents[1] / "src" / "irswitch"
    overlay_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (root / "overlay").glob("*.py")
    )
    commentary_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (root / "commentary").glob("*.py")
    )
    runtime_text = (root / "race" / "runtime.py").read_text(encoding="utf-8")
    assert "from irswitch.commentary.director" not in overlay_text
    assert "CommentaryEventConsumer" not in overlay_text
    assert "from irswitch.overlay.bus import OverlayBus" not in commentary_text
    assert "def _observe_commentary(" not in runtime_text
    assert "def _dispatch_speech_envelopes(" not in runtime_text
