"""Pure Strength-of-Field helpers (commentary H2)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from irswitch.iracing.sof import (
    SofBundle,
    compute_sof,
    compute_sof_bundle,
    format_sof_label,
)


@dataclass(frozen=True, slots=True)
class _Driver:
    i_rating: int | None
    car_class_id: int | None = 1
    car_is_pace_car: bool = False
    is_spectator: bool = False


def test_compute_sof_no_drivers() -> None:
    assert compute_sof([]) is None
    assert compute_sof_bundle([], player_class_id=1) == SofBundle(
        overall=None,
        class_sof=None,
        field_size=0,
        overall_samples=0,
        class_samples=0,
    )


def test_compute_sof_one_driver() -> None:
    assert compute_sof([2450]) == 2450
    bundle = compute_sof_bundle(
        [_Driver(i_rating=2450, car_class_id=7)],
        player_class_id=7,
    )
    assert bundle == SofBundle(
        overall=2450,
        class_sof=2450,
        field_size=1,
        overall_samples=1,
        class_samples=1,
    )


def test_compute_sof_multiclass() -> None:
    roster = [
        _Driver(i_rating=2000, car_class_id=1),
        _Driver(i_rating=3000, car_class_id=1),
        _Driver(i_rating=4000, car_class_id=2),
        _Driver(i_rating=5000, car_class_id=2),
    ]
    bundle = compute_sof_bundle(roster, player_class_id=1)
    # overall mean 3500; class 1 mean 2500
    assert bundle.overall == 3500
    assert bundle.class_sof == 2500
    assert bundle.field_size == 4
    assert bundle.overall_samples == 4
    assert bundle.class_samples == 2

    other = compute_sof_bundle(roster, player_class_id=2)
    assert other.class_sof == 4500
    assert other.class_samples == 2
    assert other.overall == 3500


def test_exclude_pace_car_and_spectator() -> None:
    roster = [
        _Driver(i_rating=2000, car_class_id=1),
        _Driver(i_rating=9999, car_class_id=1, car_is_pace_car=True),
        _Driver(i_rating=8888, car_class_id=1, is_spectator=True),
        {"i_rating": 3000, "car_class_id": 1, "car_is_pace_car": 0, "is_spectator": 0},
    ]
    bundle = compute_sof_bundle(roster, player_class_id=1)
    assert bundle.field_size == 2
    assert bundle.overall == 2500
    assert bundle.class_sof == 2500
    assert bundle.overall_samples == 2
    assert bundle.class_samples == 2


def test_invalid_ratings_skipped() -> None:
    assert compute_sof([-1, 2000, -100]) == 2000
    roster = [
        _Driver(i_rating=None, car_class_id=1),
        _Driver(i_rating=-5, car_class_id=1),
        _Driver(i_rating=1500, car_class_id=1),
        {"i_rating": "nope", "car_class_id": 1},
        {"i_rating": True, "car_class_id": 1},  # bool must not count as 1
    ]
    bundle = compute_sof_bundle(roster, player_class_id=1)
    assert bundle.field_size == 5  # all non-pace/non-spectator rows
    assert bundle.overall == 1500
    assert bundle.overall_samples == 1
    assert bundle.class_sof == 1500
    assert bundle.class_samples == 1


def test_missing_player_class_class_sof_none() -> None:
    roster = [
        _Driver(i_rating=2000, car_class_id=1),
        _Driver(i_rating=3000, car_class_id=2),
    ]
    bundle = compute_sof_bundle(roster, player_class_id=None)
    assert bundle.overall == 2500
    assert bundle.class_sof is None
    assert bundle.field_size == 2
    assert bundle.overall_samples == 2
    assert bundle.class_samples == 0


def test_player_class_with_no_matching_drivers() -> None:
    roster = [_Driver(i_rating=2000, car_class_id=1)]
    bundle = compute_sof_bundle(roster, player_class_id=99)
    assert bundle.overall == 2000
    assert bundle.class_sof is None
    assert bundle.class_samples == 0
    assert bundle.field_size == 1


def test_deterministic_rounding() -> None:
    # mean 2000.4 → 2000; mean 2000.6 → 2001; mean 2000.5 → banker's 2000
    assert compute_sof([2000, 2001, 2000]) == 2000  # 2000.333… → 2000
    assert compute_sof([1999, 2002]) == 2000  # 2000.5 → 2000 (banker's even)
    assert compute_sof([2000, 2003]) == 2002  # 2001.5 → 2002 (banker's even)
    assert compute_sof([1000, 1000, 1001]) == 1000  # 1000.333… → 1000
    assert compute_sof([1000, 1001, 1001]) == 1001  # 1000.666… → 1001


def test_format_sof_label_en_cs() -> None:
    assert format_sof_label(2450, "en") == "2,450"
    assert format_sof_label(2450, "cs") == "2 450"
    assert format_sof_label(2520, "EN") == "2,520"
    assert format_sof_label(2520, "cs-CZ") == "2 520"
    assert format_sof_label(None, "en") is None
    assert format_sof_label(0, "en") == "0"
    assert format_sof_label(999, "en") == "999"
    assert format_sof_label(1_000_000, "cs") == "1 000 000"


@pytest.mark.parametrize(
    ("ratings", "expected"),
    [
        ([0], 0),
        ([0, 0, 0], 0),
        ([1500, 1500, 1500], 1500),
    ],
)
def test_compute_sof_zero_and_uniform(ratings: list[int], expected: int) -> None:
    assert compute_sof(ratings) == expected
