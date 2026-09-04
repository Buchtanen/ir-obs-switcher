from __future__ import annotations

from irswitch.overlay.models import BioState, OpponentInfo, RaceState
from irswitch.race.prepared_facts import PreparedFactCollector, extract_prepared_session_facts


def _data(**extra: object) -> dict[str, object]:
    data: dict[str, object] = {
        "SessionNum": 0,
        "WeekendInfo": {
            "TrackDisplayName": "Spa-Francorchamps",
            "TrackConfigName": "Grand Prix",
            "TrackCity": "Stavelot",
            "TrackCountry": "Belgium",
            "TrackLength": "7.004 km",
            "TrackNumTurns": 19,
            "TrackType": "road course",
            "TrackDirection": "neutral",
            "WeekendOptions": {"StandingStart": 0},
        },
        "SessionInfo": {"Sessions": [{"SessionTrackRubberState": "moderately usage"}]},
        "DriverInfo": {
            "DriverCarIdx": 0,
            "Drivers": [
                {
                    "CarIdx": 0,
                    "UserName": "Hero Driver",
                    "IRating": 2100,
                    "CarClassID": 7,
                    "CarIsAI": 0,
                    "IsSpectator": 0,
                },
                {
                    "CarIdx": 1,
                    "UserName": "Fast Rival",
                    "IRating": 3200,
                    "CarClassID": 7,
                    "CarIsAI": 0,
                    "IsSpectator": 0,
                },
                {
                    "CarIdx": 2,
                    "UserName": "AI Rival",
                    "IRating": 0,
                    "CarClassID": 7,
                    "CarIsAI": 1,
                    "IsSpectator": 0,
                },
            ],
        },
        "Skies": 2,
        "AirTemp": 18.0,
        "TrackTempCrew": 24.0,
        "WindVel": 3.0,
        "Precipitation": 0.0,
        "TrackWetness": 1,
        "CarIdxTrackSurface": [3, 3, 1],
        "CarIdxOnPitRoad": [False, False, False],
    }
    data.update(extra)
    return data


def _race(**changes: object) -> RaceState:
    values: dict[str, object] = {
        "connected": True,
        "subsession_id": "42",
        "session_num": 0,
        "run_epoch": 1,
        "overlay_mode": "RACE",
        "player_car_class": 7,
        "player_lap_dist_pct": 0.99,
        "speed_mps": 10.0,
        "session_state": 3,
    }
    values.update(changes)
    return RaceState(**values)  # type: ignore[arg-type]


def test_extracts_circuit_weather_roster_ai_and_start_facts() -> None:
    facts = extract_prepared_session_facts(_data(), player_class_id=7)

    assert facts["track"] == "Spa-Francorchamps - Grand Prix"
    assert facts["circuit_length"] == 7.004
    assert facts["turn_count"] == 19
    assert facts["surface_wetness"] == "dry"
    assert facts["rubber_state"] == "moderately usage"
    assert facts["field_size"] == 3
    assert facts["class_field_size"] == 3
    assert facts["overall_sof"] == 1767
    assert facts["ai_count"] == 1
    assert facts["ai_ratio"] == 1 / 3
    assert facts["highest_rated_driver"] == "Rival"
    assert facts["start_mode"] == "rolling"


def test_unknown_or_malformed_source_values_are_omitted() -> None:
    facts = extract_prepared_session_facts(
        _data(
            TrackWetness=0,
            WeekendInfo={
                "TrackDisplayName": "Spa",
                "TrackLength": "unknown",
                "TrackNumTurns": -1,
                "WeekendOptions": {"StandingStart": "maybe"},
            },
        ),
        player_class_id=7,
    )

    assert "surface_wetness" not in facts
    assert "circuit_length" not in facts
    assert "turn_count" not in facts
    assert "start_mode" not in facts


def test_collector_holds_engine_rollout_return_and_light_edges_for_stage() -> None:
    collector = PreparedFactCollector()
    race = _race(speed_mps=0.0, session_flag_names=())
    collector.observe(
        _data(EngineWarnings=8, RPM=0),
        race,
        BioState(state="focused"),
        stage="IN_CAR_PREP",
        stage_epoch=3,
        now_ms=1_000,
        in_car=True,
    )
    facts = collector.observe(
        _data(EngineWarnings=0, RPM=900),
        _race(speed_mps=2.0, session_flag_names=("startReady", "startSet")),
        BioState(state="focused"),
        stage="IN_CAR_PREP",
        stage_epoch=3,
        now_ms=1_200,
        in_car=True,
    )

    assert facts["engine_state"] == "started"
    assert facts["rollout_state"] == "moving"
    assert facts["start_ready"] is True
    assert facts["start_set"] is True

    collector.observe(
        _data(EngineWarnings=0, RPM=0),
        _race(speed_mps=0.0),
        BioState(),
        stage="IN_CAR_PREP",
        stage_epoch=4,
        now_ms=2_000,
        in_car=False,
    )
    returned = collector.observe(
        _data(EngineWarnings=0, RPM=0),
        _race(speed_mps=0.0),
        BioState(),
        stage="IN_CAR_PREP",
        stage_epoch=4,
        now_ms=2_100,
        in_car=True,
    )
    assert returned["returned_to_car"] is True


def test_collector_requires_hold_for_quiet_track_and_near_line_tension() -> None:
    collector = PreparedFactCollector()
    practice = _race(overlay_mode="PRACTICE", speed_mps=0.0, session_state=2)
    first = collector.observe(
        _data(),
        practice,
        BioState(),
        stage="STREAM_LOBBY_INTRO",
        stage_epoch=1,
        now_ms=1_000,
        in_car=False,
    )
    held = collector.observe(
        _data(),
        practice,
        BioState(),
        stage="STREAM_LOBBY_INTRO",
        stage_epoch=1,
        now_ms=11_000,
        in_car=False,
    )
    assert "circulating_cars" not in first
    assert held["circulating_cars"] == 2

    formation = _race(opponent_ahead=OpponentInfo(car_idx=1))
    early = collector.observe(
        _data(),
        formation,
        BioState(state="high"),
        stage="FORMATION_OR_LIGHTS",
        stage_epoch=2,
        now_ms=20_000,
        in_car=True,
    )
    near = collector.observe(
        _data(),
        formation,
        BioState(state="high"),
        stage="FORMATION_OR_LIGHTS",
        stage_epoch=2,
        now_ms=22_000,
        in_car=True,
    )
    assert "distance_to_start" not in early
    assert near["distance_to_start"] == "near"
    assert near["traffic_band"] == "nearby"
    assert near["hr_band"] == "high"
