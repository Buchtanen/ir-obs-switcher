"""SessionInfo track + DriverInfo roster extraction (commentary H1)."""

from __future__ import annotations

from irswitch.iracing.session_context import (
    RosterDriver,
    SessionContext,
    SessionContextCache,
    extract_session_context,
    parse_roster,
    session_key,
    track_display_name,
)


def test_track_display_name_without_config() -> None:
    assert (
        track_display_name({"TrackDisplayName": "Spa-Francorchamps", "TrackConfigName": ""})
        == "Spa-Francorchamps"
    )
    assert track_display_name({"TrackDisplayName": "Monza"}) == "Monza"


def test_track_display_name_appends_config_when_not_already_included() -> None:
    assert (
        track_display_name(
            {
                "TrackDisplayName": "Spa-Francorchamps",
                "TrackConfigName": "Grand Prix Pits",
            }
        )
        == "Spa-Francorchamps - Grand Prix Pits"
    )


def test_track_display_name_skips_redundant_config() -> None:
    assert (
        track_display_name(
            {
                "TrackDisplayName": "Spa-Francorchamps - Grand Prix Pits",
                "TrackConfigName": "Grand Prix Pits",
            }
        )
        == "Spa-Francorchamps - Grand Prix Pits"
    )


def test_track_display_name_never_uses_track_id_alone() -> None:
    assert track_display_name({"TrackID": 123}) is None
    assert track_display_name({"TrackID": 123, "TrackDisplayName": ""}) is None
    assert track_display_name(None) is None
    assert track_display_name({}) is None


def test_parse_roster_empty() -> None:
    assert parse_roster(None) == ()
    assert parse_roster({}) == ()
    assert parse_roster({"Drivers": []}) == ()
    assert parse_roster({"Drivers": [None, {}, "x"]}) == ()


def test_parse_roster_excludes_pace_car() -> None:
    roster = parse_roster(
        {
            "Drivers": [
                {
                    "CarIdx": 0,
                    "CarIsPaceCar": 1,
                    "IsSpectator": 0,
                    "IRating": 1000,
                    "UserName": "Pace Car",
                },
                {
                    "CarIdx": 1,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 0,
                    "IRating": 2500,
                    "UserName": "Valentino Rossi",
                },
            ]
        }
    )
    assert len(roster) == 1
    assert roster[0].car_idx == 1
    assert roster[0].display_name == "Rossi"
    assert roster[0].car_is_pace_car is False


def test_parse_roster_excludes_spectator() -> None:
    roster = parse_roster(
        {
            "Drivers": [
                {
                    "CarIdx": 2,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 1,
                    "IRating": 3000,
                    "UserName": "Spec Tator",
                },
                {
                    "CarIdx": 3,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 0,
                    "IRating": 2100,
                    "UserName": "Racer One",
                },
            ]
        }
    )
    assert [d.car_idx for d in roster] == [3]


def test_parse_roster_missing_is_spectator_excludes_conservatively() -> None:
    """Missing IsSpectator → exclude (documented conservative policy)."""
    roster = parse_roster(
        {
            "Drivers": [
                {
                    "CarIdx": 4,
                    "CarIsPaceCar": 0,
                    "IRating": 1800,
                    "UserName": "Ambiguous Driver",
                },
                {
                    "CarIdx": 5,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 0,
                    "IRating": 1900,
                    "UserName": "Clear Racer",
                },
            ]
        }
    )
    assert [d.car_idx for d in roster] == [5]


def test_parse_roster_invalid_car_idx_and_empty_rows() -> None:
    roster = parse_roster(
        {
            "Drivers": [
                {"CarIdx": -1, "IsSpectator": 0, "IRating": 1000},
                {"CarIdx": "nope", "IsSpectator": 0, "IRating": 1000},
                {},
                None,
                {"CarIdx": 7, "IsSpectator": 0, "IRating": 1500, "UserName": "Ok Driver"},
            ]
        }
    )
    assert len(roster) == 1
    assert roster[0].car_idx == 7


def test_parse_roster_invalid_irating_keeps_driver_with_none() -> None:
    roster = parse_roster(
        {
            "Drivers": [
                {"CarIdx": 1, "IsSpectator": 0, "IRating": -1, "UserName": "Bad Rating"},
                {"CarIdx": 2, "IsSpectator": 0, "IRating": "x", "UserName": "Text Rating"},
                {"CarIdx": 3, "IsSpectator": 0, "UserName": "Missing Rating"},
                {"CarIdx": 4, "IsSpectator": 0, "IRating": 2450, "UserName": "Good Rating"},
            ]
        }
    )
    by_idx = {d.car_idx: d for d in roster}
    assert set(by_idx) == {1, 2, 3, 4}
    assert by_idx[1].i_rating is None
    assert by_idx[2].i_rating is None
    assert by_idx[3].i_rating is None
    assert by_idx[4].i_rating == 2450


def test_session_key_from_top_level_and_weekend() -> None:
    assert session_key({"SubSessionID": 100, "SessionNum": 2}) == (100, 2)
    assert session_key(
        {"SessionNum": 1, "WeekendInfo": {"SubSessionID": 55, "TrackDisplayName": "Monza"}}
    ) == (55, 1)
    assert session_key({"SubSessionID": 100}) is None
    assert session_key({"SessionNum": 2}) is None
    assert session_key(None) is None


def test_extract_session_context_multiclass_player_class() -> None:
    data = {
        "SubSessionID": 9001,
        "SessionNum": 0,
        "PlayerCarIdx": 2,
        "WeekendInfo": {
            "TrackDisplayName": "Okayama International Circuit",
            "TrackConfigName": "Full Course",
            "SubSessionID": 9001,
        },
        "DriverInfo": {
            "DriverCarIdx": 2,
            "Drivers": [
                {
                    "CarIdx": 1,
                    "CarClassID": 10,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 0,
                    "IRating": 2000,
                    "UserName": "GT3 A",
                },
                {
                    "CarIdx": 2,
                    "CarClassID": 20,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 0,
                    "IRating": 2600,
                    "UserName": "Me Player",
                },
                {
                    "CarIdx": 3,
                    "CarClassID": 10,
                    "CarIsPaceCar": 0,
                    "IsSpectator": 0,
                    "IRating": 2200,
                    "UserName": "GT3 B",
                },
                {
                    "CarIdx": 0,
                    "CarClassID": 0,
                    "CarIsPaceCar": 1,
                    "IsSpectator": 0,
                    "IRating": 0,
                    "UserName": "Pace Car",
                },
            ],
        },
    }
    ctx = extract_session_context(data)
    assert ctx is not None
    assert ctx.track == "Okayama International Circuit - Full Course"
    assert [d.car_idx for d in ctx.roster] == [1, 2, 3]
    assert ctx.player_car_idx == 2
    assert ctx.player_class_id == 20
    assert isinstance(ctx.roster[0], RosterDriver)
    assert isinstance(ctx, SessionContext)


def test_extract_session_context_fail_soft_on_garbage() -> None:
    assert extract_session_context(None) is None
    assert extract_session_context("not-a-mapping") is None
    ctx = extract_session_context({"WeekendInfo": "broken", "DriverInfo": 123})
    assert ctx is not None
    assert ctx.track is None
    assert ctx.roster == ()


def test_session_context_cache_resets_on_key_change() -> None:
    cache = SessionContextCache()
    first = {
        "SubSessionID": 1,
        "SessionNum": 0,
        "WeekendInfo": {"TrackDisplayName": "Monza"},
        "DriverInfo": {
            "Drivers": [
                {"CarIdx": 1, "IsSpectator": 0, "IRating": 2000, "UserName": "A Driver"},
            ]
        },
    }
    second = {
        "SubSessionID": 1,
        "SessionNum": 1,
        "WeekendInfo": {"TrackDisplayName": "Monza", "TrackConfigName": "GP"},
        "DriverInfo": {
            "Drivers": [
                {"CarIdx": 1, "IsSpectator": 0, "IRating": 2000, "UserName": "A Driver"},
                {"CarIdx": 2, "IsSpectator": 0, "IRating": 2100, "UserName": "B Driver"},
            ]
        },
    }
    ctx1 = cache.get_or_extract(first)
    assert ctx1 is not None
    assert ctx1.track == "Monza"
    assert len(ctx1.roster) == 1
    assert cache.key == (1, 0)

    # Same key → cached object identity
    again = cache.get_or_extract(first)
    assert again is ctx1

    ctx2 = cache.get_or_extract(second)
    assert ctx2 is not None
    assert ctx2 is not ctx1
    assert cache.key == (1, 1)
    assert ctx2.track == "Monza - GP"
    assert len(ctx2.roster) == 2

    # Missing key clears reuse of prior session
    missing = cache.get_or_extract({"WeekendInfo": {"TrackDisplayName": "Spa"}})
    assert missing is not None
    assert missing.track == "Spa"
    assert cache.key is None
