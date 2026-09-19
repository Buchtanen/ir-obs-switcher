"""#278 Slice 20 — offline F43 tape-channel funnel drivers.

Consumes frozen machine rows and proves ``OpportunityQueue`` ownership of the
tape-channel funnel: candidate/protocol identity, exact FunnelLink fields,
once-only stage counts, terminal stage shapes, live counters without tape,
incomplete-gap rates, and valid denominators. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_opportunity_queue import _ctx, _intent

from irswitch.events.opportunity_queue import (
    OpportunityQueue,
    cohort_funnel_rates,
    project_by_tape_channel_status,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE20_IDS = ("F43",)
CHANNEL = "race.battle.closing"


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_tape_funnel_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE20_IDS)
def test_slice20_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f43_tape_channel_funnel_preserves_identity_and_valid_denominators(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F43: FunnelLink identity, once-only counts, live counters, valid rates."""

    expected = set(fixtures_by_id["F43"]["expectations"])
    observed: set[str] = set()

    queue = OpportunityQueue()
    admitted = queue.admit(_intent(tape_channel=CHANNEL, candidate_id="cand:proto"))
    assert admitted.reason == "queued"
    assert admitted.opportunity is not None
    funnel = admitted.opportunity.funnel
    try:
        funnel.candidate_id = "mutated"  # type: ignore[misc]
        raise AssertionError("FunnelLink must be immutable")
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    assert funnel.candidate_id == "cand:proto"
    assert funnel.tape_channel == CHANNEL
    assert funnel.event_id == "event:1"
    assert funnel.opportunity_id == "opp:1"
    observed.add("candidate_protocol_identity")

    reserved = queue.reserve("opp:1", now_ms=10_000)
    assert reserved.opportunity is not None
    assert reserved.opportunity.funnel.candidate_id == "cand:proto"
    assert reserved.opportunity.funnel.event_id == funnel.event_id
    assert reserved.opportunity.funnel.tape_channel == CHANNEL
    token = reserved.opportunity.reservation_token
    assert token is not None
    consumed = queue.consume_speech_started(token, now_ms=10_300)
    assert consumed.opportunity is not None
    assert consumed.opportunity.funnel.opportunity_id == "opp:1"
    assert consumed.opportunity.funnel.candidate_id == "cand:proto"
    observed.add("exact_links")

    before = queue.tape_channel_status_counts()[CHANNEL]
    assert before["kick"] == 1
    assert before["queued"] == 1
    assert before["started"] == 1
    again = queue.consume_speech_started(token, now_ms=10_400)
    assert again.reason == "not_reserved"
    after = queue.tape_channel_status_counts()[CHANNEL]
    assert after["started"] == 1
    observed.add("once_only_counts")

    kick_queue = OpportunityQueue()
    kick_only = kick_queue.admit(
        _intent(
            opportunity_id="opp:kick",
            event_id="event:kick",
            candidate_id="cand:kick",
            tape_channel=CHANNEL,
            current_identifier="UNKNOWN",
        )
    )
    assert kick_only.reason == "not_speakable"
    assert kick_queue.tape_channel_status_counts()[CHANNEL] == {
        "kick": 1,
        "accepted": 0,
        "queued": 0,
        "selected": 0,
        "started": 0,
        "expired": 0,
    }

    expire_queue = OpportunityQueue()
    pending = expire_queue.admit(
        _intent(
            opportunity_id="opp:exp",
            event_id="event:exp",
            candidate_id="cand:exp",
            tape_channel=CHANNEL,
            created_mono_ms=10_000,
        )
    )
    assert pending.opportunity is not None
    expired = expire_queue.expire_due(now_ms=pending.opportunity.expires_mono_ms)
    assert expired and expired[0].reason == "expired"
    assert expire_queue.tape_channel_status_counts()[CHANNEL]["expired"] == 1

    select_queue = OpportunityQueue()
    select_queue.admit(
        _intent(
            opportunity_id="opp:sel",
            event_id="event:sel",
            candidate_id="cand:sel",
            tape_channel=CHANNEL,
        )
    )
    decision = select_queue.arbitrate(_ctx())
    assert decision.selected is not None
    assert select_queue.channel_counters(CHANNEL).selected == 1
    selected = select_queue.reserve("opp:sel", now_ms=10_000)
    assert selected.opportunity is not None
    select_queue.consume_speech_started(selected.opportunity.reservation_token, now_ms=10_200)
    spoken = select_queue.note_spoken("opp:sel", now_ms=10_500)
    assert spoken.reason == "spoken"
    assert select_queue.tape_channel_status_counts()[CHANNEL]["accepted"] == 1
    observed.add("terminal_stages")

    live = select_queue.tape_channel_status_counts()
    projected = project_by_tape_channel_status(live)
    assert CHANNEL in projected
    assert projected[CHANNEL]["kick"] >= 1
    filtered = project_by_tape_channel_status(
        {
            CHANNEL: {
                "kick": 0,
                "accepted": 0,
                "queued": 0,
                "selected": 0,
                "started": 0,
                "expired": 0,
            },
            "z.other": {
                "kick": 1,
                "accepted": 0,
                "queued": 0,
                "selected": 0,
                "started": 0,
                "expired": 0,
            },
        }
    )
    assert CHANNEL not in filtered
    assert "z.other" in filtered
    observed.add("live_counters_without_tape")

    gap_rates = cohort_funnel_rates(
        {
            "kick": 0,
            "accepted": 0,
            "queued": 1,
            "selected": 1,
            "started": 0,
            "expired": 0,
        }
    )
    assert gap_rates["kickToAccepted"] is None
    assert gap_rates["acceptedToQueued"] is None
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
    assert visual_only["acceptedToQueued"] is None
    assert visual_only["selectedToStarted"] is None
    observed.add("incomplete_replay")

    full = cohort_funnel_rates(
        {
            "kick": 4,
            "accepted": 2,
            "queued": 2,
            "selected": 2,
            "started": 1,
            "expired": 0,
        }
    )
    assert full == {
        "kickToAccepted": 0.5,
        "acceptedToQueued": 1.0,
        "selectedToStarted": 0.5,
    }
    empty = cohort_funnel_rates(
        {
            "kick": 0,
            "accepted": 0,
            "queued": 0,
            "selected": 0,
            "started": 0,
            "expired": 0,
        }
    )
    assert empty == {
        "kickToAccepted": None,
        "acceptedToQueued": None,
        "selectedToStarted": None,
    }
    observed.add("valid_denominators")

    assert observed == expected
