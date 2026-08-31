"""Pit-cycle guard: suppress battle/rival after pit exit."""

from __future__ import annotations

from irswitch.events.arbitration import PitCycleGuard
from irswitch.overlay.protocol import CandidateEvent


def _cand(name: str, phase: str = "enter") -> CandidateEvent:
    return CandidateEvent(
        name=name,
        channel="battle",
        priority=20,
        phase=phase,
        data={},
    )


def test_pit_exit_grace_suppresses_battle_and_rival() -> None:
    guard = PitCycleGuard(post_exit_grace_s=5.0)
    guard.update(True, 1.0)
    assert guard.suppresses(_cand("battle"), 1.5)
    assert guard.suppresses(_cand("rival_threat"), 1.5)
    assert not guard.suppresses(_cand("lap_complete", "trigger"), 1.5)

    guard.update(False, 2.0)
    assert guard.suppresses(_cand("battle"), 4.0)
    assert guard.suppresses(_cand("position_change", "trigger"), 4.0)
    assert not guard.suppresses(_cand("battle"), 8.0)
