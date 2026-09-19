"""#278 Slice 19 — offline F41 TTS software-boundary drivers.

Consumes frozen machine rows and proves ``speech_lane`` ownership of auditable
TTS acceptance boundaries: exact per-adapter boundaries, no early consumption,
ordered accept→terminal callbacks, protocol quarantine, watchdog authority, and
no backend retry. Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does
not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_speech_lane import _cb, _intent, _opp

from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.speech_lane import (
    ACCEPTANCE_BOUNDARIES,
    START_TIMEOUT_MS,
    STOP_TIMEOUT_MS,
    SpeechLane,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE19_IDS = ("F41",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_tts_boundaries_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE19_IDS)
def test_slice19_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f41_every_tts_backend_acknowledges_one_auditable_software_boundary(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F41: exact boundaries; no early consume; ordered callbacks; no retry."""

    expected = set(fixtures_by_id["F41"]["expectations"])
    observed: set[str] = set()

    assert ACCEPTANCE_BOUNDARIES == {
        "sapi": "async_speak_positive_stream",
        "sapi_waveout": "waveout_write_success",
        "espeak": "owned_spawn_probe_ok",
        "supertonic": "sounddevice_play_accepted",
    }
    observed.add("exact_software_boundaries")

    # --- synthesis / wrong boundary never consumes; one valid accept does ---
    queue = OpportunityQueue()
    admitted = queue.admit(_opp())
    reserved = queue.reserve(admitted.opportunity.opportunity_id, now_ms=10_000)
    token = reserved.opportunity.reservation_token
    assert token is not None

    lane = SpeechLane(queue)
    opened = lane.try_start(
        _intent(
            reservation_token=token,
            backend="sapi",
            adapter="sapi",
            available_backends=("sapi",),
            text="Hold the inside line.",
        )
    )
    assert opened.reason == "started_building"
    lane.commit("utt:1", now_ms=10_100)
    progress = lane.note_progress("utt:1", "synthesis_pcm", now_ms=10_200)
    assert progress.reason == "progress_ignored"
    assert progress.opportunity_effect is None

    early = lane.acknowledge("utt:1", adapter="sapi", boundary="synthesis_pcm", now_ms=10_300)
    assert early.reason == "boundary_not_reached"
    assert early.accepted is False
    assert early.opportunity_effect is None

    accepted = lane.acknowledge(
        "utt:1",
        adapter="sapi",
        boundary=ACCEPTANCE_BOUNDARIES["sapi"],
        now_ms=10_400,
    )
    assert accepted.reason == "playback_accepted"
    assert accepted.accepted is True
    assert accepted.opportunity_effect == "consumed"
    observed.add("no_early_consumption")

    # --- ordered accept→terminal across SAPI / waveOut / eSpeak / SuperTonic ---
    cases = (
        ("sapi", "sapi", ("sapi",)),
        ("sapi", "sapi_waveout", ("sapi",)),
        ("espeak", "espeak", ("espeak",)),
        ("supertonic", "supertonic", ("supertonic",)),
    )
    for backend, adapter, available in cases:
        ordered = SpeechLane()
        started = ordered.try_start(
            _intent(
                backend=backend,
                adapter=adapter,
                available_backends=available,
            )
        )
        assert started.utterance is not None
        assert started.utterance.backend == backend
        assert started.utterance.adapter == adapter
        ordered.commit("utt:1", now_ms=10_100)
        ack = ordered.acknowledge(
            "utt:1",
            adapter=adapter,
            boundary=ACCEPTANCE_BOUNDARIES[adapter],
            now_ms=10_300,
        )
        assert ack.accepted is True
        assert ordered._worker_sequence == 1
        done = ordered.callback(_cb("completed", sequence=2, backend=backend))
        assert done.reason == "speech_completed"
        assert ordered.start_count == 1
        assert ordered.terminal_count == 1
    observed.add("ordered_callbacks")

    # --- duplicate accept / completion-before-accept → protocol quarantine ---
    dup = SpeechLane()
    dup.try_start(_intent())
    dup.commit("utt:1", now_ms=10_100)
    dup.acknowledge(
        "utt:1",
        adapter="sapi",
        boundary=ACCEPTANCE_BOUNDARIES["sapi"],
        now_ms=10_300,
    )
    duplicate = dup.acknowledge(
        "utt:1",
        adapter="sapi",
        boundary=ACCEPTANCE_BOUNDARIES["sapi"],
        now_ms=10_400,
    )
    assert duplicate.reason == "protocol_violation"
    dup.cancel("shutdown", now_ms=10_450)
    assert dup.watchdog("stop", now_ms=10_450 + STOP_TIMEOUT_MS).reason == "quarantined"
    assert dup._quarantined == 4

    early_complete = SpeechLane()
    early_complete.try_start(_intent())
    early_complete.commit("utt:1", now_ms=10_100)
    assert early_complete.callback(_cb("completed", sequence=1)).reason == "protocol_violation"
    observed.add("protocol_quarantine")

    # --- watchdog authority: timeout-first stale ack; ack-first cancels start wd ---
    timeout_first = SpeechLane()
    timeout_first.try_start(_intent())
    timeout_first.commit("utt:1", now_ms=10_000)
    timed = timeout_first.watchdog("start", now_ms=10_000 + START_TIMEOUT_MS)
    assert timed.reason == "watchdog_start"
    late_ack = timeout_first.acknowledge(
        "utt:1",
        adapter="sapi",
        boundary=ACCEPTANCE_BOUNDARIES["sapi"],
        now_ms=10_000 + START_TIMEOUT_MS + 50,
    )
    assert late_ack.reason == "stale_callback"

    ack_first = SpeechLane()
    ack_first.try_start(_intent())
    ack_first.commit("utt:1", now_ms=10_000)
    ack_first.acknowledge(
        "utt:1",
        adapter="sapi",
        boundary=ACCEPTANCE_BOUNDARIES["sapi"],
        now_ms=10_100,
    )
    after_ack = ack_first.watchdog("start", now_ms=10_000 + START_TIMEOUT_MS)
    assert after_ack.reason == "stale_callback"
    observed.add("watchdog_authority")

    # --- pre-boundary failure and post-boundary interrupt never retry backends ---
    fail_lane = SpeechLane()
    fail_lane.try_start(_intent(backend="sapi", available_backends=("sapi", "espeak")))
    fail_lane.commit("utt:1", now_ms=10_100)
    failed = fail_lane.callback(_cb("failed", detail="preboundary", sequence=1, now_ms=10_200))
    assert failed.reason == "speech_failed"
    assert failed.failover_attempted is False
    assert fail_lane.lane == "idle"

    cancel_lane = SpeechLane()
    cancel_lane.try_start(_intent())
    cancel_lane.commit("utt:1", now_ms=10_100)
    cancel_lane.acknowledge(
        "utt:1",
        adapter="sapi",
        boundary=ACCEPTANCE_BOUNDARIES["sapi"],
        now_ms=10_300,
    )
    cancel_lane.cancel("stream_end", now_ms=10_400)
    interrupted = cancel_lane.callback(_cb("interrupted", sequence=2, now_ms=10_500))
    assert interrupted.reason == "speech_interrupted"
    assert interrupted.failover_attempted is False
    observed.add("no_backend_retry")

    assert observed == expected
