"""Live race order vs official iRSDK place."""

from irswitch.events.position import PositionEmitter
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.iracing.trk_loc import NOT_IN_WORLD, ON_TRACK
from irswitch.overlay.models import TelemetrySnapshot
from irswitch.overlay.settings import BattleSettings, EventPrioritySettings
from irswitch.race.context import RaceContextAnalyzer
from irswitch.race.opponents import relevant_ahead_behind
from irswitch.race.order import calculate_race_order, field_tape_payload, race_progress


def _snap(**kwargs: object) -> TelemetrySnapshot:
    base: dict[str, object] = {
        "connected": True,
        "player_car_idx": 1,
        "session_type": "Race",
        "session_state": 4,
        "player_car_class": 1,
        "position": 2,
        "class_position": 2,
        "last_lap_time": 90.0,
        "car_idx_lap_dist_pct": (0.40, 0.50, 0.30),
        "car_idx_lap_completed": (10, 10, 10),
        "car_idx_lap": (11, 11, 11),
        "car_idx_class": (1, 1, 1),
        "car_idx_class_position": (3, 2, 1),
        "car_idx_position": (3, 2, 1),
        "car_idx_on_pit_road": (False, False, False),
        "car_idx_track_surface": (ON_TRACK, ON_TRACK, ON_TRACK),
        "car_idx_driver_name": ("A", "Hero", "C"),
    }
    base.update(kwargs)
    return TelemetrySnapshot(**base)  # type: ignore[arg-type]


def test_extracts_lap_f2_and_pace_sentinels() -> None:
    snap = extract_telemetry(
        {
            "CarIdxLap": [-1, 4],
            "CarIdxF2Time": [-1.0, 1.25],
            "CarIdxPaceLine": [-1, 0],
            "CarIdxPaceRow": [-1, 2],
        },
        1.0,
    )
    assert snap.car_idx_lap == (None, 4)
    assert snap.car_idx_f2_time == (None, 1.25)
    assert snap.car_idx_pace_line == (None, 0)
    assert snap.car_idx_pace_row == (None, 2)


def test_live_order_ignores_stale_official_mid_lap() -> None:
    snap = _snap(
        car_idx_lap_dist_pct=(0.40, 0.80, 0.50),
        car_idx_class_position=(1, 3, 2),
        car_idx_position=(1, 3, 2),
        position=3,
        class_position=3,
    )
    order = calculate_race_order(snap)
    assert order.source == "live"
    assert order.overall[1] == 1
    assert order.class_pos[1] == 1
    assert order.overall[0] == 3


def test_parade_does_not_rank_by_lap_dist() -> None:
    snap = _snap(
        session_state=3,
        car_idx_lap_completed=(None, None, None),
        car_idx_lap=(0, 0, 0),
        car_idx_lap_dist_pct=(0.91, 0.50, 0.10),
        car_idx_class_position=(1, 2, 3),
        car_idx_position=(1, 2, 3),
        position=2,
        class_position=2,
    )
    order = calculate_race_order(snap)
    assert order.source == "grid"
    assert order.overall == (1, 2, 3)
    assert race_progress(snap, 0) is None


def test_first_lap_uses_started_lap_when_completed_missing() -> None:
    snap = _snap(
        car_idx_lap_completed=(None, None, None),
        car_idx_lap=(1, 1, 1),
        car_idx_lap_dist_pct=(0.20, 0.55, 0.40),
        car_idx_class_position=(1, 2, 3),
        position=2,
        class_position=2,
    )
    order = calculate_race_order(snap)
    assert order.source == "live"
    assert order.class_pos[1] == 1
    assert order.class_pos[2] == 2
    assert order.class_pos[0] == 3


def test_qualify_keeps_official_standings() -> None:
    snap = _snap(
        session_type="Qualify",
        session_state=4,
        car_idx_lap_dist_pct=(0.90, 0.10, 0.50),
        car_idx_class_position=(2, 1, 3),
        position=1,
        class_position=1,
    )
    order = calculate_race_order(snap)
    assert order.source == "official"
    assert order.class_pos[1] == 1


def test_analyzer_hud_place_is_live_after_pass() -> None:
    snap = _snap(
        car_idx_lap_dist_pct=(0.40, 0.80, 0.50),
        car_idx_class_position=(1, 3, 2),
        position=3,
        class_position=3,
    )
    state = RaceContextAnalyzer().analyze(snap)
    assert state.position_source == "live"
    assert state.class_position == 1
    assert state.official_class_position == 3
    assert state.opponent_ahead is None
    assert state.opponent_behind is not None
    assert state.opponent_behind.car_idx == 2


def test_near_field_follows_live_not_stale_official() -> None:
    snap = _snap(
        car_idx_lap_dist_pct=(0.40, 0.80, 0.50),
        car_idx_class_position=(1, 3, 2),
        position=3,
        class_position=3,
    )
    order = calculate_race_order(snap)
    ahead, behind = relevant_ahead_behind(snap, order)
    assert ahead is None
    assert behind == 2


def test_checkered_freeze_keeps_finished_car() -> None:
    analyzer = RaceContextAnalyzer()
    live = _snap(
        session_state=5,
        car_idx_lap_dist_pct=(0.20, 0.40, 0.90),
        car_idx_lap_completed=(10, 10, 11),
        car_idx_class_position=(3, 2, 1),
        position=2,
        class_position=2,
    )
    first = analyzer.analyze(live)
    assert first.class_position == 2
    gone = _snap(
        session_state=5,
        car_idx_lap_dist_pct=(0.25, 0.45, None),
        car_idx_lap_completed=(10, 10, None),
        car_idx_lap=(11, 11, None),
        car_idx_track_surface=(ON_TRACK, ON_TRACK, NOT_IN_WORLD),
        car_idx_class_position=(2, 1, None),
        position=1,
        class_position=1,
    )
    frozen = analyzer.analyze(gone)
    assert frozen.car_idx_live_class_position[2] == 1
    assert frozen.class_position == 2


def test_finished_hero_place_freezes_through_live_churn() -> None:
    analyzer = RaceContextAnalyzer()
    first = analyzer.analyze(
        _snap(
            session_state=6,
            car_idx_lap_dist_pct=(0.10, 0.20, 0.90),
            car_idx_lap_completed=(10, 10, 11),
            car_idx_class_position=(3, 2, 1),
            position=2,
            class_position=2,
        )
    )
    assert first.player_finished is True
    frozen_class = first.class_position
    frozen_field = first.class_field_size
    assert frozen_class == 2

    churn = analyzer.analyze(
        _snap(
            session_state=6,
            car_idx_lap_dist_pct=(0.95, 0.05, 0.50),
            car_idx_lap_completed=(12, 10, 11),
            car_idx_class_position=(1, 3, 2),
            position=3,
            class_position=3,
        )
    )
    assert churn.player_finished is True
    assert churn.class_position == frozen_class
    assert churn.position == first.position
    assert churn.class_field_size == frozen_field
    assert churn.official_class_position == 3


def test_position_emitter_silent_on_parade() -> None:
    emitter = PositionEmitter(BattleSettings(position_stable_seconds=0.0), EventPrioritySettings())
    parade = RaceContextAnalyzer().analyze(
        _snap(session_state=3, class_position=8, position=8, car_idx_class_position=(7, 8, 9))
    )
    assert parade.overlay_mode == "RACE"
    assert emitter.tick(parade, 0.0) == []
    jumped = RaceContextAnalyzer().analyze(
        _snap(session_state=3, class_position=4, position=4, car_idx_class_position=(7, 4, 9))
    )
    assert emitter.tick(jumped, 1.0) == []


def test_field_tape_payload_has_official_and_live() -> None:
    snap = _snap(
        car_idx_lap_dist_pct=(0.40, 0.80, 0.50),
        car_idx_class_position=(1, 3, 2),
        position=3,
        class_position=3,
        car_idx_est_time=(10.0, 12.0, 11.0),
        car_idx_f2_time=(2.0, 0.0, 1.0),
    )
    state = RaceContextAnalyzer().analyze(snap)
    payload = field_tape_payload(snap, state)
    assert payload["type"] == "field"
    assert payload["officialClassPosition"] == 3
    assert payload["liveClassPosition"] == 1
    assert payload["positionSource"] == "live"
    hero = next(car for car in payload["cars"] if car["idx"] == 1)
    assert hero["offCP"] == 3
    assert hero["liveCP"] == 1
    assert hero["pct"] == 0.8
