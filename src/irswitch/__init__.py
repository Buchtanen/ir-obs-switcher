"""Core package for iRacing OBS scene switcher."""

import tomllib
from pathlib import Path

# Načíst verzi z pyproject.toml (single source of truth)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_PYPROJECT_FILE = _PROJECT_ROOT / "pyproject.toml"

try:
    with open(_PYPROJECT_FILE, "rb") as f:
        _pyproject = tomllib.load(f)
    __version__ = _pyproject["project"]["version"]
except (FileNotFoundError, KeyError, ValueError):
    # Fallback pro edge cases (např. při buildu nebo testech)
    __version__ = "0.7.0"
