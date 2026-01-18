"""Configuration loading for irswitch."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    http_host: str
    http_port: int
    log_level: str
