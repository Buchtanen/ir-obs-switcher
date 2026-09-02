from irswitch.overlay.models import TelemetrySnapshot
from irswitch.race.driver_facts import DriverFactLedger


def _data(*rows: object) -> dict[str, object]:
    return {"DriverInfo": {"Drivers": list(rows)}}


def _snap(**values: object) -> TelemetrySnapshot:
    defaults = {
        "connected": True,
        "session_type": "Race",
        "session_state": 3,
        "car_idx_class": (1, 1),
        "car_idx_class_position": (1, 2),
        "car_idx_position": (4, 5),
    }
    defaults.update(values)
    return TelemetrySnapshot(**defaults)


def test_driver_facts_normalize_and_capture_multiclass_start_once() -> None:
    ledger = DriverFactLedger()
    data = _data(
        {
            "CarIdx": 0,
            "UserID": 42,
            "UserName": "Ada Racer",
            "IRating": 2345,
            "LicString": "a 3.4",
            "CarScreenNameShort": "GT3",
            "ClubName": "Central-Eastern Europe",
        },
        {"CarIdx": 1, "UserID": 84, "UserName": "Bob Driver"},
    )
    ledger.refresh(
        data,
        _snap(car_idx_class=(1, 2)),
        session_id="s:0",
        observed_monotonic_ms=100,
    )
    profile = ledger.snapshot()["profiles"]["0"]
    assert profile["display_name"] == "Ada Racer"
    assert profile["i_rating"] == 2345
    assert profile["safety_rating"] == "A 3.40"
    assert profile["car_name"] == "GT3"
    assert profile["nationality"] is None
    assert profile["start_position"] == 1
    assert profile["start_position_scope"] == "class"

    ledger.refresh(
        data,
        _snap(car_idx_class=(1, 2), car_idx_class_position=(9, 8)),
        session_id="s:0",
        observed_monotonic_ms=200,
    )
    assert ledger.snapshot()["profiles"]["0"]["start_position"] == 1


def test_changed_user_replaces_identity_without_inheriting_facts() -> None:
    ledger = DriverFactLedger()
    ledger.refresh(
        _data({"CarIdx": 0, "UserID": 1, "IRating": 2000, "LicString": "B 2.50"}),
        _snap(),
        session_id="s:0",
        observed_monotonic_ms=100,
    )
    ledger.refresh(
        _data({"CarIdx": 0, "UserID": 2, "UserName": "New Driver"}),
        _snap(),
        session_id="s:0",
        observed_monotonic_ms=200,
    )
    profile = ledger.snapshot()["profiles"]["0"]
    assert profile["identity_epoch"] == 2
    assert profile["i_rating"] is None
    assert profile["safety_rating"] is None
    assert profile["start_position"] is None


def test_green_fallback_late_join_and_reset_are_explicit() -> None:
    ledger = DriverFactLedger()
    ledger.refresh(
        _data({"CarIdx": 0, "UserID": 1}),
        _snap(session_state=4),
        session_id="s:0",
        observed_monotonic_ms=100,
    )
    assert ledger.snapshot()["start_grid_green_fallback"] is True
    ledger.refresh(
        _data({"CarIdx": 0, "UserID": 1}, {"CarIdx": 1, "UserID": 2}),
        _snap(session_state=4),
        session_id="s:0",
        observed_monotonic_ms=200,
    )
    assert ledger.snapshot()["profiles"]["1"]["start_position"] is None
    ledger.refresh(
        _data({"CarIdx": 0, "UserID": 1}),
        TelemetrySnapshot.disconnected(),
        session_id="s:0",
        observed_monotonic_ms=300,
    )
    assert ledger.snapshot()["profiles"] == {}


def test_malformed_rows_and_values_fail_soft() -> None:
    ledger = DriverFactLedger()
    ledger.refresh(
        _data(None, "bad", {"CarIdx": -1}, {"CarIdx": 0, "IRating": float("nan")}),
        _snap(car_idx_position=()),
        session_id="s:0",
        observed_monotonic_ms=100,
    )
    assert ledger.snapshot()["profiles"]["0"]["i_rating"] is None
