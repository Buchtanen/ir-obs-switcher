"""#278 Slice 7 — offline F21/F42 partition + silence-origin runtime drivers.

Consumes frozen machine rows and proves lossless context partition (64/64/2)
plus a single silence-clock origin across opening, busy and inactive states.
Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_context_batch import _event, _fact_view, _timeline
from test_silence_clock import OPEN

from irswitch.contracts import NarrativeEvent, derived_delivery_class
from irswitch.events.narrative import partition_context_batches
from irswitch.events.silence_clock import LONG_SILENCE_MS, SilenceClock

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE7_IDS = ("F21", "F42")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_partition_silence_builder_under_test"
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


def _result_event(index: int) -> NarrativeEvent:
    payload = _event(index).to_dict()
    payload["phase"] = "result"
    payload["deliveryClass"] = derived_delivery_class(payload["kind"], "result")
    return NarrativeEvent.from_dict(payload)


def _publication_130() -> tuple[NarrativeEvent, ...]:
    # Protected markers at the end of the first two 64-event chunks keep the
    # trailing 2-event remainder ordinary (machine: first_two_protected/last_ordinary).
    return tuple(
        _result_event(index) if index in (63, 127) else _event(index) for index in range(130)
    )


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE7_IDS)
def test_slice7_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f21_oversized_publication_partitions_losslessly(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F21: 130 events become protected 64 + protected 64 + ordinary 2 with stable order."""

    expected = set(fixtures_by_id["F21"]["expectations"])
    observed: set[str] = set()

    calc = fixtures_by_id["F21"]["calculations"][0]
    assert builder.evaluate(calc) == [64, 64, 2]
    events = _publication_130()
    assert len(events) == 130

    parts = partition_context_batches(
        timeline=_timeline(),
        fact_view=_fact_view(130),
        events=events,
        fanout_stream_sequence=11,
    )
    sizes = [len(part.batch.events) for part in parts]
    assert sizes == [64, 64, 2]
    observed.add("parts_64_64_2")

    assert parts[0].protected is True
    assert parts[1].protected is True
    observed.add("first_two_protected")
    assert parts[2].protected is False
    observed.add("last_ordinary")

    again = partition_context_batches(
        timeline=_timeline(),
        fact_view=_fact_view(130),
        events=events,
        fanout_stream_sequence=11,
    )
    assert [len(part.batch.events) for part in again] == [64, 64, 2]
    assert [part.protected for part in again] == [True, True, False]
    assert all(
        part.batch.timeline == parts[0].batch.timeline
        and part.batch.fact_view == parts[0].batch.fact_view
        for part in (*parts, *again)
    )
    observed.add("same_revision_idempotent")

    flat = tuple(event for part in parts for event in part.batch.events)
    assert flat == events
    assert [event.source_order.source_ordinal for event in flat] == list(range(130))
    observed.add("source_order_preserved")

    assert all(part.planning_impulse for part in parts)
    assert len(parts) == 3
    observed.add("three_impulses")

    assert observed == expected


def test_f42_silence_has_one_origin_across_states(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F42: run admission arms silence; busy/inactive/config follow one origin clock."""

    expected = set(fixtures_by_id["F42"]["expectations"])
    observed: set[str] = set()

    clock = SilenceClock()
    armed = clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    assert armed.reason == "armed"
    assert armed.generation == 1
    assert armed.deadline_mono_ms == LONG_SILENCE_MS
    observed.add("run_origin")

    cancelled = clock.on_playback_accepted(now_ms=20_000)
    assert cancelled.reason == "cancelled_playback_accepted"
    assert clock.deadline_mono_ms is None
    observed.add("acceptance_cancels")

    clock = SilenceClock()
    opening = clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    busy = clock.on_elapsed(
        generation=opening.generation,
        deadline_mono_ms=opening.deadline_mono_ms,
        now_ms=opening.deadline_mono_ms,
        lane="building",
    )
    assert busy.impulse is not None
    assert busy.impulse.kind == "LONG_SILENCE_ELAPSED"
    assert busy.filler is None
    assert busy.reason == "rearmed"
    assert busy.deadline_mono_ms == 2 * LONG_SILENCE_MS
    observed.add("busy_rearms")

    clock = SilenceClock()
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    paused = clock.on_obs_unknown(now_ms=400)
    assert paused.reason == "paused_obs_unknown"
    assert clock.deadline_mono_ms is None
    resumed = clock.on_audience_resume(now_ms=900, window=OPEN)
    assert resumed.reason == "armed"
    assert resumed.deadline_mono_ms == 900 + LONG_SILENCE_MS
    observed.add("inactive_no_credit")

    clock = SilenceClock()
    token = clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    clock.on_elapsed(
        generation=token.generation,
        deadline_mono_ms=token.deadline_mono_ms,
        now_ms=token.deadline_mono_ms,
        lane="idle",
    )
    stale = clock.on_elapsed(
        generation=token.generation,
        deadline_mono_ms=token.deadline_mono_ms,
        now_ms=token.deadline_mono_ms + 10,
        lane="idle",
    )
    assert stale.reason == "stale_token"
    assert stale.impulse is None
    observed.add("generation_stale")

    clock = SilenceClock(interval_ms=33_000)
    clock.after_lifecycle(now_ms=0, window=OPEN, speech_accepted=False)
    clock.set_interval_ms(45_000)
    assert clock.deadline_mono_ms == 33_000
    clock.on_playback_accepted(now_ms=100)
    terminal = clock.on_speech_terminal(now_ms=200, window=OPEN)
    assert terminal.reason == "armed"
    assert terminal.deadline_mono_ms == 200 + 45_000
    observed.add("new_value_next_arm")

    assert observed == expected
