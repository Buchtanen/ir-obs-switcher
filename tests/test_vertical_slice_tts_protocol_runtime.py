"""#278 Slice 18 — offline F39 TTS request/callback protocol drivers.

Consumes frozen machine rows and proves ``speech_lane`` ownership of one-shot
ordered TTS protocol: immutable utterance snapshots, accept→terminal callback
sequence, consume-once, protocol quarantine, reset consumption rules, one
higher-generation restore, late no-ops, and a later manual token. Does not
rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
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
    STOP_TIMEOUT_MS,
    SpeechLane,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE18_IDS = ("F39",)
SAPI_BOUNDARY = ACCEPTANCE_BOUNDARIES["sapi"]


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_tts_protocol_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE18_IDS)
def test_slice18_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f39_tts_request_callback_protocol_is_one_shot_and_ordered(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F39: one-shot ordered callbacks; protocol quarantine; manual new token."""

    expected = set(fixtures_by_id["F39"]["expectations"])
    observed: set[str] = set()

    # --- normal: immutable snapshot, accept→terminal sequence, consume once ---
    queue = OpportunityQueue()
    admitted = queue.admit(_opp())
    reserved = queue.reserve(admitted.opportunity.opportunity_id, now_ms=10_000)
    token = reserved.opportunity.reservation_token
    assert token is not None

    lane = SpeechLane(queue)
    opened = lane.try_start(
        _intent(
            backend="sapi",
            available_backends=("sapi", "espeak"),
            reservation_token=token,
            text="Hold the inside line.",
        )
    )
    assert opened.reason == "started_building"
    assert opened.utterance is not None
    snapshot = opened.utterance
    try:
        snapshot.backend = "espeak"  # type: ignore[misc]
        raise AssertionError("utterance must be immutable after dispatch")
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    observed.add("immutable_utterance")

    assert lane.commit("utt:1", now_ms=10_100).reason == "committed"
    duck = lane.note_progress("utt:1", "duck_complete", now_ms=10_200)
    assert duck.reason == "progress_ignored"
    assert duck.opportunity_effect is None

    accepted = lane.acknowledge("utt:1", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_300)
    assert accepted.reason == "playback_accepted"
    assert accepted.accepted is True
    assert accepted.opportunity_effect == "consumed"
    assert accepted.public_command == "SPEECH_STARTED"
    assert lane._worker_sequence == 1

    completed = lane.callback(_cb("completed", sequence=2, now_ms=12_000))
    assert completed.reason == "speech_completed"
    assert completed.opportunity_effect == "consumed"
    assert lane.lane == "idle"
    assert lane.start_count == 1
    assert lane.terminal_count == 1
    observed.add("callback_sequence")
    observed.add("consume_once")

    # --- pre-accept failure releases and does not consume ---
    queue_fail = OpportunityQueue()
    admitted_fail = queue_fail.admit(_opp(opportunity_id="opp:fail"))
    reserved_fail = queue_fail.reserve(admitted_fail.opportunity.opportunity_id, now_ms=10_000)
    fail_lane = SpeechLane(queue_fail)
    fail_lane.try_start(_intent(reservation_token=reserved_fail.opportunity.reservation_token))
    fail_lane.commit("utt:1", now_ms=10_100)
    failed = fail_lane.callback(_cb("failed", detail="backend_rejected", sequence=1, now_ms=10_200))
    assert failed.reason == "speech_failed"
    assert failed.opportunity_effect == "released"
    assert failed.failover_attempted is False
    assert "opp:fail" in queue_fail.live_ids()

    # --- completion before accept + duplicate accept → protocol quarantine ---
    early_lane = SpeechLane()
    early_lane.try_start(_intent())
    early_lane.commit("utt:1", now_ms=10_100)
    early = early_lane.callback(_cb("completed", sequence=1))
    assert early.reason == "protocol_violation"
    assert early.lane == "stopping"
    assert early.opportunity_effect is None
    early_lane.cancel("shutdown", now_ms=10_150)
    quarantined = early_lane.watchdog("stop", now_ms=10_150 + STOP_TIMEOUT_MS)
    assert quarantined.reason == "quarantined"
    assert early_lane.lane == "idle"
    assert early_lane._quarantined == 4

    dup_lane = SpeechLane()
    dup_lane.try_start(_intent())
    dup_lane.commit("utt:1", now_ms=10_100)
    dup_lane.acknowledge("utt:1", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_300)
    duplicate = dup_lane.acknowledge("utt:1", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_400)
    assert duplicate.reason == "protocol_violation"
    dup_lane.cancel("shutdown", now_ms=10_450)
    assert dup_lane.watchdog("stop", now_ms=10_450 + STOP_TIMEOUT_MS).reason == "quarantined"
    observed.add("protocol_quarantine")

    # --- reset orders: before accept unconsumed; after accept stays consumed ---
    reset_before = SpeechLane()
    reset_before.try_start(_intent())
    reset_before.commit("utt:1", now_ms=10_100)
    cancelled = reset_before.cancel("occurrence_reset", now_ms=10_200)
    assert cancelled.reason == "cancel_requested"
    assert cancelled.opportunity_effect == "unconsumed"
    late_ack = reset_before.acknowledge(
        "utt:1", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_300
    )
    assert late_ack.reason == "stale_callback"
    reset_before.watchdog("stop", now_ms=10_200 + STOP_TIMEOUT_MS)

    queue_after = OpportunityQueue()
    admitted_after = queue_after.admit(_opp(opportunity_id="opp:after"))
    reserved_after = queue_after.reserve(admitted_after.opportunity.opportunity_id, now_ms=10_000)
    reset_after = SpeechLane(queue_after)
    reset_after.try_start(_intent(reservation_token=reserved_after.opportunity.reservation_token))
    reset_after.commit("utt:1", now_ms=10_100)
    reset_after.acknowledge("utt:1", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_300)
    cancelled_after = reset_after.cancel("occurrence_reset", now_ms=10_400)
    assert cancelled_after.opportunity_effect is None
    interrupted = reset_after.callback(_cb("interrupted", sequence=2, now_ms=10_500))
    assert interrupted.reason == "speech_interrupted"
    assert interrupted.opportunity_effect == "consumed"
    observed.add("reset_consumption_rules")

    # --- stop timeout quarantine, late noop, one higher-generation restore ---
    stop_lane = SpeechLane()
    stop_lane.try_start(_intent())
    stop_lane.commit("utt:1", now_ms=10_100)
    stop_lane.acknowledge("utt:1", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_300)
    stop_lane.cancel("shutdown", now_ms=10_400)
    assert stop_lane.watchdog("stop", now_ms=10_400 + STOP_TIMEOUT_MS).reason == "quarantined"
    late = stop_lane.callback(_cb("completed", sequence=2, now_ms=12_000))
    assert late.reason == "stale_callback"
    observed.add("late_noop")

    held = stop_lane.note_health(backend_generation=4, status="ready", now_ms=20_000)
    assert held.reason == "health_noted"
    assert stop_lane.try_start(_intent(backend_generation=4)).reason == "tts_unavailable"
    restored = stop_lane.note_health(backend_generation=5, status="ready", now_ms=20_100)
    assert restored.reason == "health_ready"
    again = stop_lane.try_start(_intent(utterance_id="utt:2", backend_generation=5))
    assert again.reason == "started_building"
    observed.add("one_restore")

    # --- duck failure is honest and does not change acceptance semantics ---
    duck_lane = SpeechLane()
    duck_lane.try_start(_intent(utterance_id="utt:duck"))
    duck_lane.commit("utt:duck", now_ms=10_100)
    duck_fail = duck_lane.note_progress("utt:duck", "duck_unavailable", now_ms=10_200)
    assert duck_fail.reason == "progress_ignored"
    duck_ack = duck_lane.acknowledge(
        "utt:duck", adapter="sapi", boundary=SAPI_BOUNDARY, now_ms=10_300
    )
    assert duck_ack.accepted is True
    duck_lane.callback(_cb("completed", utterance_id="utt:duck", sequence=2, now_ms=11_000))

    # --- later manual receives a new dispatch generation / token ---
    manual = duck_lane.try_start(
        _intent(
            utterance_id="utt:manual",
            source_kind="manual",
            opportunity_id=None,
            reservation_token=None,
            plan_id=None,
            beat_id=None,
            episode_id=None,
            manual_request_id="man:1",
            text="Check one two.",
            dispatch_generation=2,
            backend="sapi",
            available_backends=("sapi", "espeak"),
        )
    )
    assert manual.reason == "manual_committed"
    assert manual.utterance is not None
    assert manual.utterance.dispatch_generation == 2
    assert manual.opportunity_effect is None
    stale_old = duck_lane.callback(
        _cb("completed", utterance_id="utt:duck", sequence=3, now_ms=12_000)
    )
    assert stale_old.reason == "stale_callback"
    observed.add("manual_new_token")

    assert observed == expected
