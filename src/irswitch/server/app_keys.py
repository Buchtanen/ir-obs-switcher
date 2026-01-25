"""Shared aiohttp AppKey definitions to avoid circular imports."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from irswitch.config import AppConfig

# Application config keys - use AppKey instances to avoid NotAppKeyWarning
APP_CONFIG: web.AppKey[AppConfig] = web.AppKey("config")
APP_CONFIG_PATH: web.AppKey[Path] = web.AppKey("config_path")
