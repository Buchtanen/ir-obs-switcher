"""Classify config reload diffs into live-applied vs restart-required keys.

Canonical lists mirror CONFIG.md § Hot-reload. Only whitelisted keys appear in
API responses; other AppConfig fields are ignored for classification.
"""

from __future__ import annotations

from irswitch.config import AppConfig
from irswitch.models import DrivingMode
from irswitch.overlay.schema import overlay_values

# Keys that take effect after POST /config/reload without process restart.
LIVE_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "switching.safe_scene",
        "switching.debounce_ms",
        "switching.cooldown_ms",
        "switching.override_seconds",
        "switching.autoswitch_default",
        "switching.auto_start_broadcast",
        "switching.auto_start_at_percent",
        "switching.default_loading_time_seconds",
        "switching.auto_stop_stream",
        "switching.stop_stream_after_seconds",
        "iracing.poll_hz",
        "sampling.default_hz",
        "sampling.race.hz",
        "sampling.system.hz",
        "sampling.bio.hz",
        "overlay.enabled",
        "overlay.theme",
        "overlay.debug",
        "overlay.language",
        "overlay.v4_assets",
        "overlay.v4_renderer",
        "overlay.session_tape",
        "event_engine.v2_payload",
        "event_engine.practice",
        "event_engine.quali_projection",
        "event_engine.overtake_classifier",
        "event_engine.pit_story",
        "event_engine.hr_pressure",
        "commentary.enabled",
        "commentary.use_hr_emotion",
        "commentary.cooldown_s",
        "commentary.max_utterance_s",
        "commentary.tts_backend",
        "commentary.tts_voice",
        "commentary.tts_rate",
        "commentary.tts_steps",
        "commentary.audio_device",
        "commentary.duck_input",
        "commentary.duck_ratio",
        "commentary.duck_fade_ms",
        "commentary.decision_log_size",
        "commentary.sector_speak",
        "commentary.sector_speak_max_per_lap",
        "commentary.session_briefs",
        "commentary.stream_start",
        "commentary.gap_hunt_tts_in_practice",
        "commentary.gap_hunt_tts_in_qualifying",
        "race_observer.leader_pace_cooldown_s",
        "race_observer.incident_classify",
        "race_observer.flags",
        "race_observer.grid_story",
        "commentary.llm_polish",
        "commentary.llm_base_url",
        "commentary.llm_model",
        "commentary.llm_timeout_s",
        "commentary.llm_temperature",
        "commentary.llm_max_tokens",
        "commentary.llm_max_attempts",
        "commentary.driver_name",
        "commentary.driver_nickname",
        "commentary.graph_runtime.mode",
        "commentary.scheduler.defer_enabled",
        "commentary.scheduler.hard_interrupt",
        "commentary.scheduler.max_deferred",
        "commentary.scheduler.default_ttl_s",
        "commentary.scheduler.incident_ttl_s",
        "commentary.scheduler.max_silence_s",
        "commentary.scheduler.llm_past_framing",
        "battle.hunting.enter_gap",
        "battle.hunting.exit_gap",
        "battle.hunting.min_closing_rate",
        "battle.hunting.activation_delay",
        "battle.hunting.exit_delay",
        "battle.hunting.approach_enter_gap",
        "battle.hunting.approach_exit_gap",
        "battle.hunting.attack_enter_gap",
        "battle.hunting.attack_exit_gap",
        "battle.hunting.side_by_side_enter_gap",
        "battle.hunting.side_by_side_exit_gap",
        "battle.hunting.intensity_min_closing_rate",
        "battle.hunting.min_intensity_hold_s",
        "battle.hunting.update_min_interval_s",
        "battle.hunting.update_gap_epsilon_s",
        "battle.hunted.enter_gap",
        "battle.hunted.exit_gap",
        "battle.hunted.min_closing_rate",
        "battle.hunted.activation_delay",
        "battle.hunted.exit_delay",
        "battle.position_stable_seconds",
        "battle.gap_history_seconds",
        "battle.overtake.max_gap",
        "battle.overtake.min_closing_rate",
        "heart_rate.enabled",
        "heart_rate.source",
        "heart_rate.bluetooth.device",
        "heart_rate.bluetooth.reconnect",
        "heart_rate.baseline_window",
        "heart_rate.calm_delta",
        "heart_rate.focused_delta",
        "heart_rate.pushing_delta",
        "system_info.enabled",
        "system_info.cpu.enabled",
        "system_info.gpu.enabled",
        "system_info.memory.enabled",
        "system_info.cpu_temp_warn",
        "system_info.cpu_temp_crit",
        "system_info.gpu_temp_warn",
        "system_info.gpu_temp_crit",
        "events.system_events_on_overlay",
        "events.incident_min_delta",
        "events.lap_duration",
        "events.lap_cooldown",
        "events.priorities.hunting",
        "events.priorities.hunted",
        "events.priorities.lap_complete",
        "events.priorities.personal_best",
        "events.priorities.position_change",
        "events.priorities.leader_change",
        "events.priorities.incident",
        "events.priorities.final_lap",
        "events.priorities.finish",
        "dashboards.dashboard_update_fps",
        "dashboards.dashboard_gr_background_image",
        "dashboards.dashboard_gr_logo_obs",
        "dashboards.dashboard_gr_logo_iracing",
        "dashboards.dashboard_gr_logo_app",
        "dashboards.dashboard_vr_icons_path",
        "dashboards.dashboard_event_log_size",
        "stream_chapters.enabled",
        "stream_chapters.start_title",
        "stream_chapters.end_title",
        "stream_chapters.trigger_session_types",
        "stream_chapters.session_titles",
        "stream_chapters.youtube_vod",
        *(f"scenes.{mode.name}" for mode in DrivingMode),
    }
)

# Keys that are stored on reload but require a process restart to fully apply.
RESTART_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "app.http_host",
        "app.http_port",
        "app.log_level",
        "app.log_file",
        "app.log_max_bytes",
        "app.log_backup_count",
        "obs.ws_url",
        "obs.password",
        "obs.required_profile",
        "oauth.client_id",
        "oauth.client_secret",
        "hotkeys.restart_hotkey",
        "system_info.lhm_dll_path",
        "overlay.session_tape_dir",
    }
)


def snapshot_tracked_keys(config: AppConfig) -> dict[str, object]:
    """Map CONFIG.md-style keys to comparable values for diffing."""
    values: dict[str, object] = {
        "app.http_host": config.http_host,
        "app.http_port": config.http_port,
        "app.log_level": config.log_level,
        "app.log_file": config.log_file,
        "app.log_max_bytes": config.log_max_bytes,
        "app.log_backup_count": config.log_backup_count,
        "iracing.poll_hz": config.poll_hz,
        "obs.ws_url": config.obs_ws_url,
        "obs.password": config.obs_password,
        "obs.required_profile": config.required_profile,
        "switching.safe_scene": config.safe_scene,
        "switching.debounce_ms": config.debounce_ms,
        "switching.cooldown_ms": config.cooldown_ms,
        "switching.override_seconds": config.override_seconds,
        "switching.autoswitch_default": config.autoswitch_default,
        "switching.auto_start_broadcast": config.auto_start_broadcast,
        "switching.auto_start_at_percent": config.auto_start_at_percent,
        "switching.default_loading_time_seconds": config.default_loading_time_seconds,
        "switching.auto_stop_stream": config.auto_stop_stream,
        "switching.stop_stream_after_seconds": config.stop_stream_after_seconds,
        "hotkeys.restart_hotkey": config.restart_hotkey,
        "dashboards.dashboard_update_fps": config.dashboard_update_fps,
        "dashboards.dashboard_gr_background_image": config.dashboard_gr_background_image,
        "dashboards.dashboard_gr_logo_obs": config.dashboard_gr_logo_obs,
        "dashboards.dashboard_gr_logo_iracing": config.dashboard_gr_logo_iracing,
        "dashboards.dashboard_gr_logo_app": config.dashboard_gr_logo_app,
        "dashboards.dashboard_vr_icons_path": config.dashboard_vr_icons_path,
        "dashboards.dashboard_event_log_size": config.dashboard_event_log_size,
        "oauth.client_id": config.oauth_client_id,
        "oauth.client_secret": config.oauth_client_secret,
        "stream_chapters.enabled": config.stream_chapters.enabled,
        "stream_chapters.start_title": config.stream_chapters.start_title,
        "stream_chapters.end_title": config.stream_chapters.end_title,
        "stream_chapters.trigger_session_types": tuple(
            config.stream_chapters.trigger_session_types
        ),
        "stream_chapters.session_titles": dict(config.stream_chapters.session_titles),
        "stream_chapters.youtube_vod": config.stream_chapters.youtube_vod,
    }
    values.update(overlay_values(config.overlay))
    for mode in DrivingMode:
        values[f"scenes.{mode.name}"] = config.scenes.get(mode)
    return values


def classify_reload_diff(old: AppConfig | None, new: AppConfig) -> tuple[list[str], list[str]]:
    """
    Diff old vs new config and classify changed whitelisted keys.

    Returns:
        (applied_live, needs_restart) — sorted lists of dotted config keys.
        If ``old`` is None, both lists are empty (no baseline to compare).
    """
    if old is None:
        return [], []

    old_vals = snapshot_tracked_keys(old)
    new_vals = snapshot_tracked_keys(new)
    changed = sorted(k for k in new_vals if old_vals.get(k) != new_vals.get(k))

    applied_live = [k for k in changed if k in LIVE_CONFIG_KEYS]
    needs_restart = [k for k in changed if k in RESTART_CONFIG_KEYS]
    return applied_live, needs_restart
