"""Parametric replay-input scenario tests (Spec §23 scenarios 1–10)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from irswitch.overlay.replay_input import (
    ReplayInputRunner,
    assert_expected_sequence,
    load_fixture,
    reset_session,
    run_scenario,
)
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.replay import _race_from_dict
from irswitch.overlay.settings import OverlaySettings

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "replay_input"
SCENARIO_PATHS = sorted(FIXTURES_DIR.glob("scenario_*.json"))


@pytest.mark.parametrize("path", SCENARIO_PATHS, ids=lambda p: p.stem)
def test_replay_input_scenario(path: Path) -> None:
    fixture = load_fixture(path)
    result = run_scenario(path)
    expected = fixture.get("expected") or []
    assert_expected_sequence(result, expected)

    forbidden = fixture.get("forbidden") or []
    actual = result.event_sequence()
    for row in forbidden:
        pair = (row["eventType"], row["phase"])
        assert pair not in actual, f"forbidden event {pair!r} present in {actual!r}"


def test_empty_fixture_produces_no_events(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text(
        '{"name": "empty", "mode": "RACE", "ticks": []}',
        encoding="utf-8",
    )
    result = run_scenario(path)
    assert result.events == []
    assert result.event_sequence() == []


def test_session_reset_clears_emitter_state() -> None:
    runner = ReplayInputRunner()
    hunting_tick = {
        "t": 0.0,
        "race": {
            "connected": True,
            "player_car_idx": 4,
            "opponent_ahead": {
                "car_idx": 17,
                "position": 6,
                "gap": 2.0,
                "closing_rate": 0.3,
            },
            "gap_ahead": 2.0,
            "closing_rate_ahead": 0.3,
        },
    }
    first = runner.run_fixture(
        {
            "name": "warm",
            "mode": "RACE",
            "flags": {"battle": {"hunting": {"activation_delay": 0.0}}},
            "ticks": [hunting_tick],
        }
    )
    assert any(event_type == "HUNTING" for _, event_type, _ in first.events)

    reset_session(runner, session_id="replay:1:0")
    second = runner.run_fixture(
        {
            "name": "after reset",
            "mode": "RACE",
            "flags": {"battle": {"hunting": {"activation_delay": 0.0}}},
            "ticks": [hunting_tick],
        }
    )
    assert any(event_type == "HUNTING" for _, event_type, _ in second.events)
    assert runner._engine is not None
    assert runner._engine.battle.hunting.state == "ACTIVE"


def test_emitter_isolation_survives_failure(caplog) -> None:
    class _FailingEmitter:
        def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
            raise RuntimeError("boom")

    class _Survivor:
        def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
            return [
                CandidateEvent(
                    name="lap_complete",
                    channel="lap",
                    priority=40,
                    phase="trigger",
                    data={"lap": 11, "lapTime": 95.0, "bestLap": 94.0, "deltaToBest": 1.0},
                )
            ]

    runner = ReplayInputRunner()
    assert runner._engine is not None
    runner._engine.register(_FailingEmitter())
    runner._engine.register(_Survivor())

    race = {
        "connected": True,
        "lap_completed": 11,
        "last_lap_time": 95.0,
        "best_lap_time": 94.0,
    }
    with caplog.at_level(logging.WARNING, logger="irswitch.events.engine"):
        events = runner._tick_once(_race_from_dict(race), 1.0, bio=None, mode="RACE")

    assert any(event_type == "LAP_COMPLETE" for _, event_type, _ in events)
    assert any("_FailingEmitter tick failed" in record.message for record in caplog.records)


def test_run_scenario_accepts_overlay_settings() -> None:
    overlay = OverlaySettings()
    result = run_scenario(SCENARIO_PATHS[0], overlay_settings=overlay)
    assert result.name
