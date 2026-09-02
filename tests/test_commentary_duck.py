"""OBS volume duck while commentary speaks."""

from __future__ import annotations

import time
from typing import Any

import pytest

from irswitch.commentary.duck import (
    VolumeDucker,
    ducked_mul,
    ducker_from_settings,
    fade_mul,
    reset_shared_ducker,
)
from irswitch.overlay.settings import CommentarySettings


def test_ducked_mul_is_quarter() -> None:
    assert ducked_mul(0.2166, 0.25) == 0.2166 * 0.25
    assert ducked_mul(1.0, 0.25) == 0.25
    assert ducked_mul(0.8, 2.0) == 0.8


def test_ducker_saves_sets_and_restores() -> None:
    store = {"Zvuk plochy": 0.4}
    calls: list[tuple[str, float]] = []

    def get_mul(name: str) -> float | None:
        return store.get(name)

    def set_mul(name: str, mul: float) -> bool:
        store[name] = mul
        calls.append((name, mul))
        return True

    ducker = VolumeDucker("Zvuk plochy", 0.25, get_mul, set_mul)
    with ducker:
        assert store["Zvuk plochy"] == 0.1
    assert store["Zvuk plochy"] == 0.4
    assert calls == [("Zvuk plochy", 0.1), ("Zvuk plochy", 0.4)]


def test_ducker_nested_restores_once() -> None:
    store = {"Desktop": 0.8}

    def get_mul(name: str) -> float | None:
        return store[name]

    def set_mul(name: str, mul: float) -> bool:
        store[name] = mul
        return True

    ducker = VolumeDucker("Desktop", 0.25, get_mul, set_mul)
    ducker.enter()
    ducker.enter()
    assert store["Desktop"] == 0.2
    ducker.exit()
    assert store["Desktop"] == 0.2
    ducker.exit()
    assert store["Desktop"] == 0.8


def test_ducker_empty_input_is_noop() -> None:
    calls: list[str] = []
    ducker = VolumeDucker(
        "",
        0.25,
        lambda _n: calls.append("get") or 1.0,
        lambda _n, _m: calls.append("set") or True,
    )
    with ducker:
        pass
    assert calls == []


def test_ducker_skips_when_get_fails() -> None:
    sets: list[float] = []
    ducker = VolumeDucker("Missing", 0.25, lambda _n: None, lambda _n, m: sets.append(m) or True)
    with ducker:
        pass
    assert sets == []


def test_ducker_restores_if_speak_raises() -> None:
    store = {"A": 1.0}
    ducker = VolumeDucker(
        "A",
        0.25,
        lambda _n: store["A"],
        lambda _n, m: store.__setitem__("A", m) or True,
    )
    try:
        with ducker:
            assert store["A"] == 0.25
            raise RuntimeError("tts failed")
    except RuntimeError:
        pass
    assert store["A"] == 1.0


def test_shared_ducker_overlapping_speak_does_not_double_duck(monkeypatch: Any) -> None:
    reset_shared_ducker()
    store = {"Zvuk plochy": 0.4}

    def get_mul(name: str) -> float | None:
        return store[name]

    def set_mul(name: str, mul: float) -> bool:
        store[name] = mul
        return True

    monkeypatch.setattr("irswitch.commentary.duck._obs_get_mul", get_mul)
    monkeypatch.setattr("irswitch.commentary.duck._obs_set_mul", set_mul)
    settings = CommentarySettings(duck_input="Zvuk plochy", duck_ratio=0.1, duck_fade_ms=0)
    first = ducker_from_settings(settings)
    second = ducker_from_settings(settings)
    assert first is second
    with first:
        assert store["Zvuk plochy"] == pytest.approx(0.04)
        with second:
            assert store["Zvuk plochy"] == pytest.approx(0.04)
        assert store["Zvuk plochy"] == pytest.approx(0.04)
    assert store["Zvuk plochy"] == 0.4
    reset_shared_ducker()


def test_fade_mul_hits_endpoints() -> None:
    assert fade_mul(1.0, 0.25, 0.0) == 1.0
    assert fade_mul(1.0, 0.25, 1.0) == 0.25
    mid = fade_mul(1.0, 0.25, 0.5)
    assert 0.25 < mid < 1.0
    assert mid == pytest.approx(10 ** ((0.0 + (-12.0412) * 0.5) / 20.0), rel=1e-3)


def test_ducker_fades_out_and_in() -> None:
    store = {"A": 1.0}
    calls: list[float] = []
    sleeps: list[float] = []

    def set_mul(_name: str, mul: float) -> bool:
        store["A"] = mul
        calls.append(mul)
        return True

    ducker = VolumeDucker(
        "A",
        0.25,
        lambda _n: 1.0,
        set_mul,
        fade_ms=750,
        sleep=sleeps.append,
    )
    with ducker:
        assert store["A"] == pytest.approx(0.25)
        assert len(calls) == 15
        assert calls[0] != pytest.approx(0.25)
        assert calls[-1] == pytest.approx(0.25)
    assert store["A"] == pytest.approx(1.0)
    assert len(calls) == 30
    assert calls[-1] == pytest.approx(1.0)
    assert sum(sleeps) == pytest.approx(1.4)


def test_next_line_during_fade_in_does_not_ratchet_original() -> None:
    """A new line mid fade-in must duck from the first saved volume, not OBS mid-ramp."""
    store = {"A": 1.0}
    interrupting = {"armed": False}
    ducker: VolumeDucker

    def sleep(_s: float) -> None:
        if interrupting["armed"] and ducker._depth == 0:
            interrupting["armed"] = False
            ducker.enter()

    ducker = VolumeDucker(
        "A",
        0.1,
        lambda _n: store["A"],
        lambda _n, m: store.__setitem__("A", m) or True,
        fade_ms=200,
        sleep=sleep,
    )
    ducker.enter()
    interrupting["armed"] = True
    ducker.exit()
    assert store["A"] == pytest.approx(0.1)
    ducker.exit()
    assert store["A"] == pytest.approx(1.0)


def test_repeated_fade_in_interrupts_do_not_stack_to_silence() -> None:
    store = {"A": 1.0}
    interrupting = {"armed": False}
    ducker: VolumeDucker

    def sleep(_s: float) -> None:
        if interrupting["armed"] and ducker._depth == 0:
            interrupting["armed"] = False
            ducker.enter()

    ducker = VolumeDucker(
        "A",
        0.1,
        lambda _n: store["A"],
        lambda _n, m: store.__setitem__("A", m) or True,
        fade_ms=200,
        sleep=sleep,
    )
    for _ in range(8):
        ducker.enter()
        interrupting["armed"] = True
        ducker.exit()
        ducker.exit()
    assert store["A"] == pytest.approx(1.0)


def test_force_restore_puts_volume_back() -> None:
    store = {"A": 1.0}
    ducker = VolumeDucker(
        "A",
        0.1,
        lambda _n: store["A"],
        lambda _n, m: store.__setitem__("A", m) or True,
    )
    ducker.enter()
    assert store["A"] == pytest.approx(0.1)
    ducker.force_restore()
    assert store["A"] == pytest.approx(1.0)
    assert ducker._depth == 0
    assert ducker._saved is None


def test_enter_wait_false_overlaps_work() -> None:
    store = {"A": 1.0}
    ducker = VolumeDucker(
        "A",
        0.25,
        lambda _n: 1.0,
        lambda _n, m: store.__setitem__("A", m) or True,
        fade_ms=250,
        sleep=time.sleep,
    )
    started = time.perf_counter()
    ducker.enter(wait=False)
    time.sleep(0.08)
    ducker.wait_faded()
    elapsed = time.perf_counter() - started
    assert store["A"] == pytest.approx(0.25)
    assert elapsed < 0.26
    assert elapsed >= 0.15
    ducker.exit()
    assert store["A"] == pytest.approx(1.0)
