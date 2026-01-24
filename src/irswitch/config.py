"""Configuration loading for irswitch."""

from __future__ import annotations

import configparser
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from irswitch.models import DrivingMode

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
        log_level = app_section.get("log_level", "INFO").upper()
        notifications_enabled = parser.getboolean(
            "app", "notifications_enabled", fallback=True
        )
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
        from irswitch.i18n import SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE

        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        # [iracing]
        poll_hz = parser.getint("iracing", "poll_hz")
        quit_stall_seconds = parser.getfloat(
            "iracing", "quit_stall_seconds", fallback=0.4
        )
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
        safe_scene = switching_section.get("safe_scene")
        if not safe_scene:
            raise ValueError("switching.safe_scene is required")

        # Auto-start broadcast settings
        auto_start_broadcast = parser.getboolean(
            "switching", "auto_start_broadcast", fallback=False
        )
        auto_start_at_percent = parser.getint(
            "switching", "auto_start_at_percent", fallback=50
        )
        if auto_start_at_percent < 0 or auto_start_at_percent > 100:
            raise ValueError(
                "switching.auto_start_at_percent must be between 0 and 100"
            )
        default_loading_time_seconds = parser.getfloat(
            "switching", "default_loading_time_seconds", fallback=12.0
        )
        if default_loading_time_seconds <= 0:
            raise ValueError("switching.default_loading_time_seconds must be > 0")

        # Auto-stop stream settings
        auto_stop_stream = parser.getboolean(
            "switching", "auto_stop_stream", fallback=False
        )
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
            except KeyError:
                raise ValueError(f"Unknown driving mode in config: {mode_name}")

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
            dashboard_update_fps = parser.getint(
                "dashboards", "dashboard_update_fps", fallback=2
            )
            if dashboard_update_fps <= 0:
                raise ValueError("dashboards.dashboard_update_fps must be > 0")

            dashboard_gr_background_image = (
                dashboards_section.get("dashboard_gr_background_image") or None
            )
            dashboard_gr_logo_obs = (
                dashboards_section.get("dashboard_gr_logo_obs") or None
            )
            dashboard_gr_logo_iracing = (
                dashboards_section.get("dashboard_gr_logo_iracing") or None
            )
            dashboard_gr_logo_app = (
                dashboards_section.get("dashboard_gr_logo_app") or None
            )
            dashboard_vr_icons_path = (
                dashboards_section.get("dashboard_vr_icons_path") or None
            )

            dashboard_event_log_size = parser.getint(
                "dashboards", "dashboard_event_log_size", fallback=50
            )
            if dashboard_event_log_size <= 0:
                raise ValueError("dashboards.dashboard_event_log_size must be > 0")

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
        )
        return result
