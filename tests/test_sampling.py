"""Sampling scheduler helpers."""

from irswitch.sampling.scheduler import clamp_hz, resolve_component_hz


def test_clamp_hz_zero_is_push() -> None:
    assert clamp_hz(0) == 0.0
    assert clamp_hz(-1) == 0.0


def test_clamp_hz_bounds() -> None:
    assert clamp_hz(0.01) == 0.2
    assert clamp_hz(100) == 30.0
    assert clamp_hz(5) == 5.0


def test_resolve_override_and_bio_push_default() -> None:
    assert resolve_component_hz(5, None) == 5.0
    assert resolve_component_hz(5, 10) == 10.0
    assert resolve_component_hz(5, None, push_when_unset=True) == 0.0
    assert resolve_component_hz(5, 0, push_when_unset=True) == 0.0
