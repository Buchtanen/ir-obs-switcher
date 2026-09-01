"""Battle / lap / position / incident / pit / session emitters."""

from irswitch.events.battle import BattleEmitter
from irswitch.events.incident import IncidentEmitter
from irswitch.events.lap import LapEmitter
from irswitch.events.pit import PitEmitter
from irswitch.events.position import PositionEmitter
from irswitch.events.session import SessionEmitter
from irswitch.iracing.trk_loc import IN_PIT_STALL, ON_TRACK
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.settings import (
    BattleSettings,
    EventPrioritySettings,
    EventSettings,
    HuntingSettings,
    RaceObserverSettings,
)


def _state(**overrides: object) -> RaceState:
    base = {
        "connected": True,
        "player_car_idx": 4,
        "position": 7,
        "class_position": 5,
        "lap": 12,
        "lap_completed": 11,
        "last_lap_time": 94.0,
        "best_lap_time": 94.5,
        "incidents": 2,
        "on_pit_road": False,
        "player_track_surface": ON_TRACK,
    }
    base.update(overrides)
    if overrides.get("on_pit_road") is True and "player_track_surface" not in overrides:
        base["player_track_surface"] = IN_PIT_STALL
    return RaceState(**base)  # type: ignore[arg-type]


def test_hunting_candidate_then_enter_then_exit() -> None:
    emitter = BattleEmitter(
        HuntingSettings(
            activation_delay=2.0,
            exit_delay=1.5,
            min_intensity_hold_s=0.0,
            update_min_interval_s=0.25,
            update_gap_epsilon_s=0.05,
        ),
        HuntingSettings(),
    )
    ahead = OpponentInfo(car_idx=17, position=6, gap=2.0, closing_rate=0.3)
    t = 10.0
    out = emitter.tick(_state(opponent_ahead=ahead, gap_ahead=2.0, closing_rate_ahead=0.3), t)
    assert out == []
    assert emitter.hunting.state == "CANDIDATE"
    out = emitter.tick(_state(opponent_ahead=ahead, gap_ahead=2.0, closing_rate_ahead=0.3), t + 2.0)
    assert any(e.phase == "enter" and e.data["state"] == "hunting" for e in out)
    # stay
    out = emitter.tick(_state(opponent_ahead=ahead, gap_ahead=2.2, closing_rate_ahead=0.2), t + 2.5)
    assert any(e.phase == "update" for e in out)
    # fail then exit after delay
    far = OpponentInfo(car_idx=17, position=6, gap=5.0, closing_rate=-0.1)
    emitter.tick(_state(opponent_ahead=far, gap_ahead=5.0, closing_rate_ahead=-0.1), t + 3.0)
    out = emitter.tick(_state(opponent_ahead=far, gap_ahead=5.0, closing_rate_ahead=-0.1), t + 4.6)
    assert any(e.phase == "exit" for e in out)


def test_hunting_exits_immediately_when_session_finished() -> None:
    emitter = BattleEmitter(
        HuntingSettings(activation_delay=0.0, exit_delay=1.5, min_intensity_hold_s=0.0),
        HuntingSettings(),
    )
    ahead = OpponentInfo(car_idx=17, position=6, gap=2.0, closing_rate=0.3)
    racing = _state(opponent_ahead=ahead, gap_ahead=2.0, closing_rate_ahead=0.3)
    out = emitter.tick(racing, 10.0)
    assert any(e.phase == "enter" and e.data["state"] == "hunting" for e in out)
    out = emitter.tick(_state(session_finished=True, opponent_ahead=ahead, gap_ahead=2.0), 10.1)
    assert any(e.phase == "exit" and e.data.get("reason") == "session_finished" for e in out)
    assert emitter.hunting.state == "NONE"
    assert emitter.tick(_state(session_finished=True), 10.2) == []


def test_hunting_continues_when_checkered_but_player_not_finished() -> None:
    emitter = BattleEmitter(
        HuntingSettings(activation_delay=0.0, exit_delay=1.5, min_intensity_hold_s=0.0),
        HuntingSettings(),
    )
    ahead = OpponentInfo(car_idx=17, position=6, gap=2.0, closing_rate=0.3)
    racing = _state(opponent_ahead=ahead, gap_ahead=2.0, closing_rate_ahead=0.3)
    assert any(e.phase == "enter" for e in emitter.tick(racing, 10.0))
    still = _state(
        opponent_ahead=ahead,
        gap_ahead=2.0,
        closing_rate_ahead=0.3,
        session_checkered=True,
        session_state=5,
        player_finished=False,
        mute_field=False,
        session_finished=False,
    )
    out = emitter.tick(still, 10.1)
    assert not any(e.data.get("reason") == "session_finished" for e in out)
    assert emitter.hunting.state != "NONE"


def test_hunting_and_hunted_both_independent() -> None:
    emitter = BattleEmitter(
        HuntingSettings(activation_delay=0.0, min_intensity_hold_s=0.0),
        HuntingSettings(activation_delay=0.0),
    )
    state = _state(
        opponent_ahead=OpponentInfo(car_idx=1, position=6, gap=1.0, closing_rate=0.4),
        opponent_behind=OpponentInfo(car_idx=2, position=8, gap=0.8, closing_rate=0.3),
        gap_ahead=1.0,
        gap_behind=0.8,
        closing_rate_ahead=0.4,
        closing_rate_behind=0.3,
    )
    out = emitter.tick(state, 1.0)
    states = {e.data["state"] for e in out if e.phase == "enter"}
    assert {"hunting", "hunted"}.issubset(states)


def test_lap_complete_and_personal_best() -> None:
    emitter = LapEmitter(EventSettings(), EventPrioritySettings())
    emitter.tick(_state(lap_completed=10, last_lap_time=95.0, best_lap_time=94.0), 1.0)
    out = emitter.tick(_state(lap_completed=11, last_lap_time=94.0, best_lap_time=94.0), 2.0)
    assert out[0].name == "personal_best"
    out = emitter.tick(_state(lap_completed=12, last_lap_time=95.2, best_lap_time=94.0), 3.0)
    assert out[0].name == "lap_complete"


def test_lap_complete_waits_for_valid_sdk_time() -> None:
    emitter = LapEmitter(EventSettings(), EventPrioritySettings())
    emitter.tick(_state(lap_completed=10, last_lap_time=95.0), 1.0)
    assert emitter.tick(_state(lap_completed=11, last_lap_time=None), 2.0) == []
    out = emitter.tick(_state(lap_completed=11, last_lap_time=94.2, best_lap_time=94.0), 3.0)
    assert out[0].name == "lap_complete"
    assert out[0].data["lapTime"] == 94.2


def test_position_requires_stability() -> None:
    emitter = PositionEmitter(BattleSettings(position_stable_seconds=1.0), EventPrioritySettings())
    emitter.tick(_state(class_position=8), 0.0)
    assert emitter.tick(_state(class_position=7), 0.2) == []
    out = emitter.tick(_state(class_position=7), 1.2)
    assert out[0].data["direction"] == "gain"
    assert out[0].data["delta"] == 1


def test_incident_respects_min_delta() -> None:
    emitter = IncidentEmitter(EventSettings(incident_min_delta=2), EventPrioritySettings())
    emitter.tick(_state(incidents=2), 0.0)
    assert emitter.tick(_state(incidents=3), 1.0) == []
    out = emitter.tick(_state(incidents=5), 2.0)
    assert out[0].data["value"] == 2
    assert "branch" not in out[0].data


def test_incident_classify_off_track_vs_unknown() -> None:
    from irswitch.iracing.trk_loc import OFF_TRACK

    settings = RaceObserverSettings(incident_classify=True)
    emitter = IncidentEmitter(
        EventSettings(incident_min_delta=2), EventPrioritySettings(), settings
    )
    emitter.tick(_state(incidents=2, player_track_surface=OFF_TRACK), 0.0)
    off = emitter.tick(_state(incidents=4, player_track_surface=OFF_TRACK), 1.0)
    assert off[0].data["branch"] == "off_track"
    assert "kind" not in off[0].data

    on_track = IncidentEmitter(
        EventSettings(incident_min_delta=2), EventPrioritySettings(), settings
    )
    on_track.tick(_state(incidents=2), 0.0)
    unknown = on_track.tick(_state(incidents=4), 1.0)
    assert unknown[0].data["branch"] == "unknown"
    assert unknown[0].data.get("kind") != "contact_object"
    assert "nearbyCarIdx" not in unknown[0].data


def test_incident_nearby_car_is_metric_only() -> None:
    settings = RaceObserverSettings(incident_classify=True)
    emitter = IncidentEmitter(
        EventSettings(incident_min_delta=2), EventPrioritySettings(), settings
    )
    ahead = OpponentInfo(car_idx=17, position=6, gap=0.4)
    emitter.tick(_state(incidents=2, opponent_ahead=ahead), 0.0)
    out = emitter.tick(_state(incidents=4, opponent_ahead=ahead), 1.0)
    assert out[0].data["branch"] == "unknown"
    assert out[0].data["nearbyCarIdx"] == 17
    assert out[0].data["nearbyGap"] == 0.4
    assert out[0].data.get("kind") != "contact_car"


def test_pit_edges() -> None:
    emitter = PitEmitter(EventPrioritySettings())
    emitter.tick(_state(on_pit_road=False), 0.0)
    out = emitter.tick(_state(on_pit_road=True), 1.0)
    assert out[0].name == "pit_entry"
    out = emitter.tick(_state(on_pit_road=False, class_position=9), 2.0)
    assert out[0].name == "pit_exit"
    assert out[0].data["position"] == 9


def test_final_lap_and_finish_once() -> None:
    emitter = SessionEmitter(EventSettings(), EventPrioritySettings())
    out = emitter.tick(_state(is_final_lap=True), 1.0)
    assert out[0].name == "final_lap"
    assert out[0].data["position"] == 7
    assert out[0].data["classPosition"] == 5
    assert emitter.tick(_state(is_final_lap=True), 2.0) == []
    out = emitter.tick(_state(session_finished=True), 3.0)
    assert out[0].name == "finish"
