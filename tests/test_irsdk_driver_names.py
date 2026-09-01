"""iRSDK DriverInfo → speakable names for commentary slots."""

from __future__ import annotations

from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.adapters.position import position_race_event_to_envelope
from irswitch.events.battle import BattleEmitter
from irswitch.events.rival_threat import RivalThreatEmitter
from irswitch.iracing.drivers import (
    driver_names_by_car_idx,
    speakable_driver_name,
    speakable_name_mix,
)
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.protocol import RaceEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings, HuntingSettings
from irswitch.race.context import RaceContextAnalyzer


def test_speakable_driver_name_prefers_last_token_of_user_name() -> None:
    assert (
        speakable_driver_name({"UserName": "Valentino Rossi", "AbbrevName": "V. Rossi"}) == "Rossi"
    )
    assert speakable_driver_name({"UserName": "Senna"}) == "Senna"
    assert speakable_driver_name({"AbbrevName": "J. Smith"}) == "Smith"
    assert speakable_driver_name({}) is None


def test_speakable_name_mix_first_and_last() -> None:
    assert speakable_name_mix({"UserName": "Richard Buchtanen"}) == ("Richard", "Buchtanen")
    assert speakable_name_mix({"UserName": "Buchtanen"}) == ("Buchtanen",)
    assert speakable_name_mix({"UserName": "Valentino Rossi"}) == ("Valentino", "Rossi")
    assert speakable_name_mix({}) == ()


def test_driver_names_by_car_idx_from_driver_info() -> None:
    names = driver_names_by_car_idx(
        {
            "Drivers": [
                {"CarIdx": 0, "UserName": "Player One"},
                {"CarIdx": 2, "UserName": "Valentino Rossi"},
                {"CarIdx": 5, "AbbrevName": "H. Kovalainen"},
            ]
        }
    )
    assert names[2] == "Rossi"
    assert names[5] == "Kovalainen"
    assert names[0] == "One"
    assert names[1] is None


def test_extract_telemetry_includes_driver_names() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 1,
            "DriverInfo": {
                "Drivers": [
                    {"CarIdx": 1, "UserName": "Me Player"},
                    {"CarIdx": 3, "UserName": "Lewis Hamilton"},
                ]
            },
        },
        timestamp=1.0,
    )
    assert snap.car_idx_driver_name[3] == "Hamilton"


def test_race_context_copies_display_name_onto_opponents() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 1,
            "PlayerCarPosition": 7,
            "PlayerCarClassPosition": 5,
            "PlayerCarClass": 1,
            "LapCompleted": 11,
            "LapLastLapTime": 90.0,
            "OnPitRoad": False,
            "SessionState": 4,
            "CarIdxLapDistPct": [0.52, 0.50, 0.48, 0.1],
            "CarIdxLapCompleted": [11, 11, 11, 11],
            "CarIdxClass": [1, 1, 1, 1],
            "CarIdxClassPosition": [4, 5, 6, 9],
            "CarIdxPosition": [4, 7, 8, 20],
            "CarIdxOnPitRoad": [False, False, False, False],
            "CarIdxTrackSurface": [4, 4, 4, 4],
            "DriverInfo": {
                "Drivers": [
                    {"CarIdx": 0, "UserName": "Ahead Driver"},
                    {"CarIdx": 2, "UserName": "Behind Driver"},
                ]
            },
        },
        timestamp=1.0,
    )
    state = RaceContextAnalyzer().analyze(snap)
    assert state.opponent_ahead is not None
    assert state.opponent_ahead.car_idx == 0
    assert state.opponent_ahead.display_name == "Driver"
    assert state.opponent_behind is not None
    assert state.opponent_behind.display_name == "Driver"


def test_battle_and_rival_emit_target_name() -> None:
    ahead = OpponentInfo(car_idx=17, position=6, gap=2.0, closing_rate=0.3, display_name="Rossi")
    behind = OpponentInfo(
        car_idx=23, position=8, gap=1.5, closing_rate=0.4, display_name="Kovalainen"
    )
    state = RaceState(
        connected=True,
        position=7,
        opponent_ahead=ahead,
        opponent_behind=behind,
        gap_ahead=2.0,
        gap_behind=1.5,
        closing_rate_ahead=0.3,
        closing_rate_behind=0.4,
        overlay_mode="RACE",
    )
    hunting = HuntingSettings(activation_delay=0.0, enter_gap=3.0, exit_gap=4.0)
    battle = BattleEmitter(hunting, hunting)
    events = battle.tick(state, 10.0)
    hunting_enter = next(e for e in events if e.data.get("state") == "hunting")
    assert hunting_enter.data["targetName"] == "Rossi"

    rival = RivalThreatEmitter(EventSettings(), EventPrioritySettings())
    rival_events = rival.tick(state, 10.0)
    assert rival_events[0].data["targetName"] == "Kovalainen"


def test_adapters_bind_irsdk_display_name() -> None:
    battle_env = battle_race_event_to_envelope(
        RaceEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            timestamp=1.0,
            data={
                "state": "hunting",
                "gap": 1.2,
                "targetCarIdx": 17,
                "targetPosition": 6,
                "targetName": "Rossi",
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert battle_env is not None
    assert battle_env.target is not None
    assert battle_env.target.display_name == "Rossi"
    assert battle_env.metrics["targetName"] == "Rossi"

    ot = position_race_event_to_envelope(
        RaceEvent(
            name="overtake",
            channel="alert",
            priority=80,
            phase="trigger",
            timestamp=2.0,
            data={
                "oldPosition": 7,
                "newPosition": 6,
                "targetCarIdx": 17,
                "targetName": "Rossi",
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=12.0,
    )
    assert ot is not None
    assert ot.target is not None
    assert ot.target.display_name == "Rossi"
