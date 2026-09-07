"""Shared aiohttp AppKey definitions to avoid circular imports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from irswitch.config import AppConfig

if TYPE_CHECKING:
    from irswitch.config_reload import CommentaryConfigCoordinator

# Application config keys - use AppKey instances to avoid NotAppKeyWarning
APP_CONFIG: web.AppKey[AppConfig] = web.AppKey("config")
APP_CONFIG_PATH: web.AppKey[Path] = web.AppKey("config_path")
APP_COMMENTARY_CONFIG: web.AppKey[CommentaryConfigCoordinator] = web.AppKey("commentary_config")
