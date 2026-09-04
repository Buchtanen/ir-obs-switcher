"""Reviewed identifiers accepted by the scenario-definition loader.

The registry is deliberately data-only in the foundation slice. Guard and action
implementations are bound explicitly by the engine; JSON never contains executable
expressions.
"""

from __future__ import annotations

REGISTERED_GUARD_IDS: frozenset[str] = frozenset(
    {
        "classification_deadline_without_supported_state",
        "episode_age_exceeded",
        "incident_count_rising",
        "incident_count_rising_within_coalesce_window",
        "on_track_motion_held",
        "on_track_not_towing_motion_held",
        "on_track_stopped_held",
        "surface_off_track_held_in_incident_window",
        "tow_active",
        "tow_cleared_on_track_motion_held",
    }
)

REGISTERED_ACTION_IDS: frozenset[str] = frozenset(
    {
        "capture_preincident_surface_window",
        "create_episode",
        "emit_aftermath_off_track",
        "emit_aftermath_rolling",
        "emit_aftermath_stalled_on_track",
        "emit_aftermath_towing",
        "emit_back_under_way",
        "emit_incident_if_narratable",
        "emit_incident_off_track_if_narratable",
        "emit_incident_unknown_if_narratable",
        "increase_episode_delta",
        "record_abstention",
        "record_timeout",
        "schedule_incident_root",
        "update_incident_total",
    }
)

REGISTERED_ESTIMATOR_IDS: frozenset[str] = frozenset(
    {
        "bounded_categorical_history",
        "counter_positive_delta",
        "speed_with_wrapped_lap_distance_fallback",
    }
)

REGISTERED_UNITS: frozenset[str] = frozenset(
    {
        "count",
        "iracing_track_location",
        "lap_fraction",
        "meters_per_second",
        "ordinal",
        "seconds",
    }
)

REGISTERED_RESET_REASONS: frozenset[str] = frozenset(
    {
        "disconnect_grace_exceeded",
        "hero_changed",
        "run_epoch_changed",
        "session_changed",
    }
)

REGISTERED_RESET_ACTIONS: frozenset[str] = frozenset({"invalidate_without_emission"})
REGISTERED_RESET_SCOPES: frozenset[str] = frozenset({"episode", "run", "session"})
REGISTERED_MISSING_POLICIES: frozenset[str] = frozenset(
    {"omit_metric", "unknown", "use_lap_distance_fallback"}
)
