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

    # [iracing]
    poll_hz: int
    quit_stall_seconds: float

    # [obs]
    obs_ws_url: str
    obs_password: str
    required_profile: str | None  # Optional: if set, switcher only works when this profile is active

    # [switching]
    autoswitch_default: bool
    debounce_ms: int
    cooldown_ms: int
    override_seconds: int
    safe_scene: str

    # [hotkeys]
    restart_hotkey: str | None  # Optional: e.g. "ctrl+shift+r" - when held during QUIT, triggers RESTART mode

    # [scenes]
    scenes: Mapping[DrivingMode, str]

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
        notifications_enabled = parser.getboolean("app", "notifications_enabled", fallback=True)

        # [iracing]
        poll_hz = parser.getint("iracing", "poll_hz")
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
        safe_scene = switching_section.get("safe_scene")
        if not safe_scene:
            raise ValueError("switching.safe_scene is required")

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

        result = cls(
            http_host=http_host,
            http_port=http_port,
            log_level=log_level,
            notifications_enabled=notifications_enabled,
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
            restart_hotkey=restart_hotkey,
            scenes=scenes,
        )
        return result
