"""Real IBT excerpts plus negative cases that previously produced invented recovery."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_remote_commentary_microplan import plan

from irswitch.events.commentary_grounding import free_grounding_reasons
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.models import RaceState
from irswitch.race.aftermath import IncidentAftermathFsm


def state(**kwargs):
    return replace(
        RaceState(
            connected=True,
            overlay_mode="RACE",
            incidents=1,
            player_track_surface=3,
            speed_mps=0,
            player_lap_dist_pct=0.3,
        ),
        **kwargs,
    )


def test_actual_ibt_offtrack_and_pending_repairs():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/aftermath_ibt_20260929.json").read_text()
    )
    for scenario in fixture["scenarios"]:
        fsm = IncidentAftermathFsm()
        emitted = []
        for row in scenario["samples"]:
            snap = extract_telemetry(row, timestamp=row["SessionTime"])
            current = state(
                incidents=snap.incidents,
                speed_mps=snap.speed_mps,
                player_track_surface=snap.player_track_surface,
                player_tow_time=snap.player_tow_time,
                player_lap_dist_pct=snap.player_lap_dist_pct,
                engine_warnings=snap.engine_warnings,
                player_in_pit_stall=snap.player_in_pit_stall,
                pit_service_status=snap.pit_service_status,
                pit_repair_left=snap.pit_repair_left,
                pit_opt_repair_left=snap.pit_opt_repair_left,
            )
            emitted.extend(fsm.tick(current, row["SessionTime"]))
            fsm.take_pending()
        assert all(e.event_type != "BACK_UNDER_WAY" for e in emitted)
        if scenario["name"] == "moving_offtrack":
            assert [e.metrics["kind"] for e in emitted] == ["off_track", "rejoined"]
        if scenario["name"] == "pending_repair_not_service":
            repair = [e for e in emitted if e.metrics.get("fact") == "repairs"]
            assert len(repair) == 1
            assert repair[0].metrics["optionalRepairRequired"] is True
            assert repair[0].metrics["repairServiceActive"] is False
            assert "optionalRepairSeconds" not in repair[0].metrics


@pytest.mark.parametrize(
    "changes",
    [
        {"speed_mps": None},
        {"speed_mps": float("nan")},
        {"speed_mps": 40},
        {"data_quality": "stale"},
    ],
)
def test_unknown_or_moving_never_proves_stopped(changes):
    fsm = IncidentAftermathFsm()
    fsm.tick(state(**changes), 0)
    events = []
    for t in (0.2, 0.5, 0.9, 1.5):
        events.extend(fsm.tick(state(incidents=3, **changes), t))
    assert not any(e.metrics.get("kind") == "stopped" for e in events)


def test_stop_requires_consistent_motion_and_resets_with_run():
    fsm = IncidentAftermathFsm()
    fsm.tick(state(), 0)
    for i in range(1, 7):
        events = fsm.tick(state(incidents=3, player_lap_dist_pct=0.3 + i * 0.01), i * 0.2)
        assert not any(e.metrics.get("kind") == "stopped" for e in events)
    fsm.tick(state(run_epoch=1, incidents=3), 1.5)
    assert fsm.tick(state(run_epoch=1, incidents=3, speed_mps=30), 2.3) == []


def test_tow_completion_does_not_claim_driving_or_repairs_complete():
    fsm = IncidentAftermathFsm()
    fsm.tick(state(), 0)
    assert fsm.tick(state(incidents=3, player_tow_time=10), 0.2)[0].metrics["kind"] == "towing"
    assert fsm.tick(state(incidents=3, player_tow_time=0, speed_mps=30), 0.5) == []
    assert fsm.tick(state(incidents=3, speed_mps=30), 1.5) == []


def test_repairs_from_sdk_to_plan_and_guard():
    snap = extract_telemetry(
        {
            "EngineWarnings": 384,
            "PitRepairLeft": 30,
            "PitOptRepairLeft": 2.5,
            "PlayerCarInPitStall": True,
            "PlayerCarPitSvStatus": 1,
        },
        timestamp=1,
    )
    fsm = IncidentAftermathFsm()
    events = fsm.tick(
        state(
            engine_warnings=snap.engine_warnings,
            player_in_pit_stall=snap.player_in_pit_stall,
            pit_service_status=snap.pit_service_status,
            pit_repair_left=snap.pit_repair_left,
            pit_opt_repair_left=snap.pit_opt_repair_left,
        ),
        1,
    )
    result = plan("FIELD_FACT", events[0].metrics)
    assert result is not None
    assert dict(result.input_fields)["mandatory_repair_seconds"] == 30
    assert not free_grounding_reasons("Buchtanen needs mandatory repairs.", result)
    assert free_grounding_reasons("Buchtanen has fully repaired the car.", result)
    assert fsm.tick(state(engine_warnings=0), 1.2) == []


def test_rejoin_cannot_be_reworded_as_stop_or_recovery():
    result = plan("INCIDENT_AFTERMATH", {"kind": "rejoined", "surface": 3, "tow": False})
    assert result is not None
    assert not free_grounding_reasons("Buchtanen has returned to the track.", result)
    assert free_grounding_reasons("Buchtanen is back under way.", result)
    assert free_grounding_reasons("Buchtanen has stopped.", result)


def test_invalid_repair_samples_remain_unknown():
    snap = extract_telemetry(
        {"PitRepairLeft": float("nan"), "PitOptRepairLeft": -1, "EngineWarnings": -1}, timestamp=1
    )
    assert snap.pit_repair_left is None and snap.pit_opt_repair_left is None
    assert snap.engine_warnings is None
