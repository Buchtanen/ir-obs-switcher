"""Post-race and stint gates for overlay emitters."""

from __future__ import annotations

from irswitch.iracing.trk_loc import is_esc_teleport, is_on_track, is_towing
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent

# After checkered/cooldown, keep finish (and EXIT so widgets can leave).
POST_RACE_KEEP_NAMES = frozenset({"finish", "final_lap"})


def filter_post_race(
    events: list[CandidateEvent],
    *,
    session_finished: bool,
) -> list[CandidateEvent]:
    if not session_finished:
        return events
    return [e for e in events if e.name in POST_RACE_KEEP_NAMES or e.phase == "exit"]


def should_begin_pit_cycle(
    state: RaceState,
    *,
    seen_on_track: bool,
    prev_surface: int | None,
    prev_dist: float | None = None,
) -> bool:
    """True only for a driven pit entry this stint, not lobby spawn or ESC/tow."""
    if not state.connected or state.session_finished:
        return False
    if is_towing(state.player_tow_time):
        return False
    if is_esc_teleport(
        prev_surface,
        state.player_track_surface,
        prev_dist,
        state.player_lap_dist_pct,
    ):
        return False
    if not seen_on_track and not is_on_track(state.player_track_surface):
        return False
    return True
