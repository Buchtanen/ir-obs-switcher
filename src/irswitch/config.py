"""Configuration loading for irswitch."""

from __future__ import annotations

import configparser
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from irswitch.models import DrivingMode
from irswitch.overlay.i18n import normalize_language as normalize_overlay_language
from irswitch.overlay.settings import (
    BattleSettings,
    EventEngineFeatureSettings,
    EventPrioritySettings,
    EventSettings,
    HeartRateSettings,
    HuntingSettings,
    OverlaySettings,
    OverlayTapeSettings,
    OverlayV4Settings,
    OvertakeClassifierSettings,
    SamplingSettings,
    SystemInfoSettings,
)
from irswitch.sampling.scheduler import clamp_hz

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from INI file."""

    # [app]
    http_host: str
    http_port: int
    log_level: str
    notifications_enabled: bool
    log_file: str | None  # Optional: path to log file
    log_max_bytes: int  # Maximum log file size before rotation
    log_backup_count: int  # Number of backup log files to keep
    log_colors: bool  # Enable colored console output (default: True)
    language: str  # Language code (CS, EN, DE, FR, SP, PL, HU) - default: CS

    # [iracing]
    poll_hz: int
    quit_stall_seconds: float

    # [obs]
    obs_ws_url: str
    obs_password: str
    required_profile: (
        str | None
    )  # Optional: if set, switcher only works when this profile is active

    # [switching]
    autoswitch_default: bool
    debounce_ms: int
    cooldown_ms: int
    override_seconds: int
    safe_scene: str
    auto_start_broadcast: bool
    auto_start_at_percent: int
    default_loading_time_seconds: float
    auto_stop_stream: bool
    stop_stream_after_seconds: int

    # [hotkeys]
    restart_hotkey: (
        str | None
    )  # Optional: e.g. "ctrl+shift+r" - when held during QUIT, triggers RESTART mode

    # [scenes]
    scenes: Mapping[DrivingMode, str]

    # [dashboards]
    dashboard_update_fps: int
    dashboard_gr_background_image: str | None
    dashboard_gr_logo_obs: str | None
    dashboard_gr_logo_iracing: str | None
    dashboard_gr_logo_app: str | None
    dashboard_vr_icons_path: str | None
    dashboard_event_log_size: int

    # [oauth] - Optional OAuth credentials for YouTube API
    oauth_client_id: str | None
    oauth_client_secret: str | None

    # Overlay / race pipeline (optional INI sections, defaults apply)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)

    @classmethod
    def from_file(cls, path: Path | str) -> AppConfig:
        """Load configuration from INI file."""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")

        # [app]
        app_section = parser["app"]
        http_host = app_section.get("http_host", "127.0.0.1")
        http_port = parser.getint("app", "http_port")
        if http_port < 1 or http_port > 65535:
            raise ValueError("app.http_port must be between 1 and 65535")
        log_level = app_section.get("log_level", "INFO").upper()
        notifications_enabled = parser.getboolean("app", "notifications_enabled", fallback=True)
        log_file = app_section.get("log_file") or None
        log_max_bytes = parser.getint(
            "app", "log_max_bytes", fallback=10 * 1024 * 1024
        )  # 10 MB default
        if log_max_bytes <= 0:
            raise ValueError("app.log_max_bytes must be > 0")
        log_backup_count = parser.getint("app", "log_backup_count", fallback=5)
        if log_backup_count < 0:
            raise ValueError("app.log_backup_count must be >= 0")
        log_colors = parser.getboolean("app", "log_colors", fallback=True)
        language = app_section.get("language", "CS").upper()
        from irswitch.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        # [iracing]
        poll_hz = parser.getint("iracing", "poll_hz")
        if poll_hz < 1:
            raise ValueError("iracing.poll_hz must be >= 1")
        quit_stall_seconds = parser.getfloat("iracing", "quit_stall_seconds", fallback=0.4)
        if quit_stall_seconds <= 0:
            raise ValueError("iracing.quit_stall_seconds must be > 0")

        # [obs]
        obs_section = parser["obs"]
        obs_ws_url = obs_section.get("ws_url")
        obs_password = obs_section.get("password")
        if not obs_ws_url or not obs_password:
            raise ValueError("obs.ws_url and obs.password are required")
        required_profile = obs_section.get("required_profile")  # Optional

        # [switching]
        switching_section = parser["switching"]
        autoswitch_default = parser.getboolean("switching", "autoswitch_default")
        debounce_ms = parser.getint("switching", "debounce_ms")
        cooldown_ms = parser.getint("switching", "cooldown_ms")
        override_seconds = parser.getint("switching", "override_seconds")
        if debounce_ms < 0:
            raise ValueError("switching.debounce_ms must be >= 0")
        if cooldown_ms < 0:
            raise ValueError("switching.cooldown_ms must be >= 0")
        if override_seconds < 0:
            raise ValueError("switching.override_seconds must be >= 0")
        safe_scene = switching_section.get("safe_scene")
        if not safe_scene:
            raise ValueError("switching.safe_scene is required")

        # Auto-start broadcast settings
        auto_start_broadcast = parser.getboolean(
            "switching", "auto_start_broadcast", fallback=False
        )
        auto_start_at_percent = parser.getint("switching", "auto_start_at_percent", fallback=50)
        if auto_start_at_percent < 0 or auto_start_at_percent > 100:
            raise ValueError("switching.auto_start_at_percent must be between 0 and 100")
        default_loading_time_seconds = parser.getfloat(
            "switching", "default_loading_time_seconds", fallback=12.0
        )
        if default_loading_time_seconds <= 0:
            raise ValueError("switching.default_loading_time_seconds must be > 0")

        # Auto-stop stream settings
        auto_stop_stream = parser.getboolean("switching", "auto_stop_stream", fallback=False)
        stop_stream_after_seconds = parser.getint(
            "switching", "stop_stream_after_seconds", fallback=30
        )
        if stop_stream_after_seconds <= 0:
            raise ValueError("switching.stop_stream_after_seconds must be > 0")

        # [hotkeys] (optional section)
        restart_hotkey: str | None = None
        if parser.has_section("hotkeys"):
            restart_hotkey = parser.get("hotkeys", "restart_hotkey", fallback=None)
            if restart_hotkey:
                restart_hotkey = restart_hotkey.strip()
                if not restart_hotkey:
                    restart_hotkey = None

        # [scenes]
        scenes_section = parser["scenes"]
        scenes: dict[DrivingMode, str] = {}
        for mode_name, scene_name in scenes_section.items():
            try:
                mode = DrivingMode[mode_name.upper()]
                scenes[mode] = scene_name
            except KeyError as err:
                raise ValueError(f"Unknown driving mode in config: {mode_name}") from err

        # [dashboards] (optional section)
        dashboard_update_fps = 2
        dashboard_gr_background_image: str | None = None
        dashboard_gr_logo_obs: str | None = None
        dashboard_gr_logo_iracing: str | None = None
        dashboard_gr_logo_app: str | None = None
        dashboard_vr_icons_path: str | None = None
        dashboard_event_log_size = 50

        if parser.has_section("dashboards"):
            dashboards_section = parser["dashboards"]
            dashboard_update_fps = parser.getint("dashboards", "dashboard_update_fps", fallback=2)
            if dashboard_update_fps <= 0:
                raise ValueError("dashboards.dashboard_update_fps must be > 0")

            dashboard_gr_background_image = (
                dashboards_section.get("dashboard_gr_background_image") or None
            )
            dashboard_gr_logo_obs = dashboards_section.get("dashboard_gr_logo_obs") or None
            dashboard_gr_logo_iracing = dashboards_section.get("dashboard_gr_logo_iracing") or None
            dashboard_gr_logo_app = dashboards_section.get("dashboard_gr_logo_app") or None
            dashboard_vr_icons_path = dashboards_section.get("dashboard_vr_icons_path") or None

            dashboard_event_log_size = parser.getint(
                "dashboards", "dashboard_event_log_size", fallback=50
            )
            if dashboard_event_log_size <= 0:
                raise ValueError("dashboards.dashboard_event_log_size must be > 0")

        # [oauth] - Optional OAuth credentials for YouTube API
        oauth_client_id = None
        oauth_client_secret = None
        if parser.has_section("oauth"):
            oauth_section = parser["oauth"]
            oauth_client_id = oauth_section.get("client_id") or None
            oauth_client_secret = oauth_section.get("client_secret") or None
            # Strip whitespace if present
            if oauth_client_id:
                oauth_client_id = oauth_client_id.strip()
                if not oauth_client_id:
                    oauth_client_id = None
            if oauth_client_secret:
                oauth_client_secret = oauth_client_secret.strip()
                if not oauth_client_secret:
                    oauth_client_secret = None

        overlay = _load_overlay_settings(parser)

        result = cls(
            http_host=http_host,
            http_port=http_port,
            log_level=log_level,
            notifications_enabled=notifications_enabled,
            log_file=log_file,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
            log_colors=log_colors,
            language=language,
            poll_hz=poll_hz,
            quit_stall_seconds=quit_stall_seconds,
            obs_ws_url=obs_ws_url,
            obs_password=obs_password,
            required_profile=required_profile,
            autoswitch_default=autoswitch_default,
            debounce_ms=debounce_ms,
            cooldown_ms=cooldown_ms,
            override_seconds=override_seconds,
            safe_scene=safe_scene,
            auto_start_broadcast=auto_start_broadcast,
            auto_start_at_percent=auto_start_at_percent,
            default_loading_time_seconds=default_loading_time_seconds,
            auto_stop_stream=auto_stop_stream,
            stop_stream_after_seconds=stop_stream_after_seconds,
            restart_hotkey=restart_hotkey,
            scenes=scenes,
            dashboard_update_fps=dashboard_update_fps,
            dashboard_gr_background_image=dashboard_gr_background_image,
            dashboard_gr_logo_obs=dashboard_gr_logo_obs,
            dashboard_gr_logo_iracing=dashboard_gr_logo_iracing,
            dashboard_gr_logo_app=dashboard_gr_logo_app,
            dashboard_vr_icons_path=dashboard_vr_icons_path,
            dashboard_event_log_size=dashboard_event_log_size,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            overlay=overlay,
        )
        return result


def _optional_float(parser: configparser.ConfigParser, section: str, key: str) -> float | None:
    if not parser.has_section(section) or not parser.has_option(section, key):
        return None
    raw = parser.get(section, key, fallback="").strip()
    if raw == "":
        return None
    return parser.getfloat(section, key)


def _get_bool(parser: configparser.ConfigParser, section: str, key: str, fallback: bool) -> bool:
    if not parser.has_section(section):
        return fallback
    return parser.getboolean(section, key, fallback=fallback)


def _get_float(parser: configparser.ConfigParser, section: str, key: str, fallback: float) -> float:
    if not parser.has_section(section):
        return fallback
    return parser.getfloat(section, key, fallback=fallback)


def _get_int(parser: configparser.ConfigParser, section: str, key: str, fallback: int) -> int:
    if not parser.has_section(section):
        return fallback
    return parser.getint(section, key, fallback=fallback)


def _get_str(parser: configparser.ConfigParser, section: str, key: str, fallback: str) -> str:
    if not parser.has_section(section):
        return fallback
    return parser.get(section, key, fallback=fallback).strip() or fallback


def _load_hunting(parser: configparser.ConfigParser, section: str) -> HuntingSettings:
    defaults = HuntingSettings()
    return HuntingSettings(
        enter_gap=_get_float(parser, section, "enter_gap", defaults.enter_gap),
        exit_gap=_get_float(parser, section, "exit_gap", defaults.exit_gap),
        min_closing_rate=_get_float(parser, section, "min_closing_rate", defaults.min_closing_rate),
        activation_delay=_get_float(parser, section, "activation_delay", defaults.activation_delay),
        exit_delay=_get_float(parser, section, "exit_delay", defaults.exit_delay),
        approach_enter_gap=_get_float(
            parser, section, "approach_enter_gap", defaults.approach_enter_gap
        ),
        approach_exit_gap=_get_float(
            parser, section, "approach_exit_gap", defaults.approach_exit_gap
        ),
        attack_enter_gap=_get_float(parser, section, "attack_enter_gap", defaults.attack_enter_gap),
        attack_exit_gap=_get_float(parser, section, "attack_exit_gap", defaults.attack_exit_gap),
        side_by_side_enter_gap=_get_float(
            parser, section, "side_by_side_enter_gap", defaults.side_by_side_enter_gap
        ),
        side_by_side_exit_gap=_get_float(
            parser, section, "side_by_side_exit_gap", defaults.side_by_side_exit_gap
        ),
        intensity_min_closing_rate=_get_float(
            parser, section, "intensity_min_closing_rate", defaults.intensity_min_closing_rate
        ),
    )


def _load_overlay_settings(parser: configparser.ConfigParser) -> OverlaySettings:
    """Parse optional overlay INI sections. Missing keys keep defaults."""
    defaults = OverlaySettings()
    default_hz = _get_float(parser, "sampling", "default_hz", defaults.sampling.default_hz)
    sampling = SamplingSettings(
        default_hz=clamp_hz(default_hz) if default_hz > 0 else defaults.sampling.default_hz,
        race_hz=_optional_float(parser, "sampling.race", "hz"),
        system_hz=_optional_float(parser, "sampling.system", "hz"),
        bio_hz=_optional_float(parser, "sampling.bio", "hz"),
    )
    theme = _get_str(parser, "overlay", "theme", defaults.theme)
    allowed_themes = {
        "cyber_racing",
        "stealth_graphite",
        "night_attack",
        "pit_wall_dark",
        "pit_wall_light",
    }
    if theme not in allowed_themes:
        theme = defaults.theme

    language = normalize_overlay_language(
        _get_str(parser, "overlay", "language", defaults.language)
    )

    v4 = OverlayV4Settings(
        assets=_get_bool(parser, "overlay", "v4_assets", defaults.v4.assets),
        renderer=_get_bool(parser, "overlay", "v4_renderer", defaults.v4.renderer),
    )
    from irswitch.overlay.tape import safe_tape_dir

    tape = OverlayTapeSettings(
        enabled=_get_bool(parser, "overlay", "session_tape", defaults.tape.enabled),
        directory=safe_tape_dir(
            _get_str(parser, "overlay", "session_tape_dir", defaults.tape.directory)
        ),
    )

    ee_defaults = defaults.event_engine
    event_engine = EventEngineFeatureSettings(
        v2_payload=_get_bool(parser, "event_engine", "v2_payload", ee_defaults.v2_payload),
        practice=_get_bool(parser, "event_engine", "practice", ee_defaults.practice),
        quali_projection=_get_bool(
            parser, "event_engine", "quali_projection", ee_defaults.quali_projection
        ),
        overtake_classifier=_get_bool(
            parser, "event_engine", "overtake_classifier", ee_defaults.overtake_classifier
        ),
        pit_story=_get_bool(parser, "event_engine", "pit_story", ee_defaults.pit_story),
        hr_pressure=_get_bool(parser, "event_engine", "hr_pressure", ee_defaults.hr_pressure),
    )

    lhm_raw = ""
    if parser.has_section("system_info"):
        lhm_raw = parser.get("system_info", "lhm_dll_path", fallback="").strip()
    lhm_path = lhm_raw or None
    if lhm_path and ".." in lhm_path.replace("\\", "/"):
        raise ValueError("system_info.lhm_dll_path must not contain path traversal")

    pri = EventPrioritySettings(
        hunting=_get_int(
            parser, "events.priorities", "hunting", defaults.events.priorities.hunting
        ),
        hunted=_get_int(parser, "events.priorities", "hunted", defaults.events.priorities.hunted),
        battle_start=_get_int(
            parser, "events.priorities", "battle_start", defaults.events.priorities.battle_start
        ),
        lap_complete=_get_int(
            parser, "events.priorities", "lap_complete", defaults.events.priorities.lap_complete
        ),
        personal_best=_get_int(
            parser, "events.priorities", "personal_best", defaults.events.priorities.personal_best
        ),
        position_change=_get_int(
            parser,
            "events.priorities",
            "position_change",
            defaults.events.priorities.position_change,
        ),
        overtake=_get_int(
            parser, "events.priorities", "overtake", defaults.events.priorities.overtake
        ),
        incident=_get_int(
            parser, "events.priorities", "incident", defaults.events.priorities.incident
        ),
        pit=_get_int(parser, "events.priorities", "pit", defaults.events.priorities.pit),
        final_lap=_get_int(
            parser, "events.priorities", "final_lap", defaults.events.priorities.final_lap
        ),
        finish=_get_int(parser, "events.priorities", "finish", defaults.events.priorities.finish),
        bio=_get_int(parser, "events.priorities", "bio", defaults.events.priorities.bio),
        system=_get_int(parser, "events.priorities", "system", defaults.events.priorities.system),
    )

    return OverlaySettings(
        enabled=_get_bool(parser, "overlay", "enabled", defaults.enabled),
        theme=theme,
        debug=_get_bool(parser, "overlay", "debug", defaults.debug),
        language=language,
        v4=v4,
        tape=tape,
        event_engine=event_engine,
        sampling=sampling,
        battle=BattleSettings(
            hunting=_load_hunting(parser, "battle.hunting"),
            hunted=_load_hunting(parser, "battle.hunted"),
            position_stable_seconds=_get_float(
                parser, "battle", "position_stable_seconds", defaults.battle.position_stable_seconds
            ),
            gap_history_seconds=_get_float(
                parser, "battle", "gap_history_seconds", defaults.battle.gap_history_seconds
            ),
            overtake=OvertakeClassifierSettings(
                max_gap=_get_float(
                    parser,
                    "battle.overtake",
                    "max_gap",
                    defaults.battle.overtake.max_gap,
                ),
                min_closing_rate=_get_float(
                    parser,
                    "battle.overtake",
                    "min_closing_rate",
                    defaults.battle.overtake.min_closing_rate,
                ),
            ),
        ),
        heart_rate=HeartRateSettings(
            enabled=_get_bool(parser, "heart_rate", "enabled", defaults.heart_rate.enabled),
            source=_get_str(parser, "heart_rate", "source", defaults.heart_rate.source),
            device=_get_str(parser, "heart_rate.bluetooth", "device", defaults.heart_rate.device),
            reconnect=_get_bool(
                parser, "heart_rate.bluetooth", "reconnect", defaults.heart_rate.reconnect
            ),
            baseline_window=_get_float(
                parser, "heart_rate", "baseline_window", defaults.heart_rate.baseline_window
            ),
            calm_delta=_get_float(
                parser, "heart_rate", "calm_delta", defaults.heart_rate.calm_delta
            ),
            focused_delta=_get_float(
                parser, "heart_rate", "focused_delta", defaults.heart_rate.focused_delta
            ),
            pushing_delta=_get_float(
                parser, "heart_rate", "pushing_delta", defaults.heart_rate.pushing_delta
            ),
        ),
        system_info=SystemInfoSettings(
            enabled=_get_bool(parser, "system_info", "enabled", defaults.system_info.enabled),
            cpu_enabled=_get_bool(
                parser, "system_info.cpu", "enabled", defaults.system_info.cpu_enabled
            ),
            gpu_enabled=_get_bool(
                parser, "system_info.gpu", "enabled", defaults.system_info.gpu_enabled
            ),
            memory_enabled=_get_bool(
                parser, "system_info.memory", "enabled", defaults.system_info.memory_enabled
            ),
            lhm_dll_path=lhm_path,
            cpu_temp_warn=_get_float(
                parser, "system_info", "cpu_temp_warn", defaults.system_info.cpu_temp_warn
            ),
            cpu_temp_crit=_get_float(
                parser, "system_info", "cpu_temp_crit", defaults.system_info.cpu_temp_crit
            ),
            gpu_temp_warn=_get_float(
                parser, "system_info", "gpu_temp_warn", defaults.system_info.gpu_temp_warn
            ),
            gpu_temp_crit=_get_float(
                parser, "system_info", "gpu_temp_crit", defaults.system_info.gpu_temp_crit
            ),
        ),
        events=EventSettings(
            incident_min_delta=_get_int(
                parser, "events", "incident_min_delta", defaults.events.incident_min_delta
            ),
            lap_duration=_get_float(parser, "events", "lap_duration", defaults.events.lap_duration),
            lap_cooldown=_get_float(parser, "events", "lap_cooldown", defaults.events.lap_cooldown),
            alert_duration=_get_float(
                parser, "events", "alert_duration", defaults.events.alert_duration
            ),
            session_duration=_get_float(
                parser, "events", "session_duration", defaults.events.session_duration
            ),
            battle_update_hz=_get_float(
                parser, "events", "battle_update_hz", defaults.events.battle_update_hz
            ),
            system_events_on_overlay=_get_bool(
                parser,
                "events",
                "system_events_on_overlay",
                defaults.events.system_events_on_overlay,
            ),
            priorities=pri,
        ),
    )
