"""Core package for iRacing OBS scene switcher."""

from __future__ import annotations

import sys
import tomllib
from importlib import metadata
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None))


def _read_version_from_package_metadata() -> str | None:
    """Installed package metadata (wheel / last pip install)."""
    try:
        return metadata.version("irswitch")
    except metadata.PackageNotFoundError:
        return None


def _read_version_from_build_info() -> str | None:
    """
    Fallback for bundled distributions (e.g. PyInstaller + extracted ZIP).

    We generate BUILD_INFO.txt during CI build and ship it alongside the exe.
    """
    candidates: list[Path] = []

    # Common case: extracted zip contains BUILD_INFO.txt next to irswitchd.exe
    try:
        candidates.append(Path(sys.executable).resolve().parent / "BUILD_INFO.txt")
    except Exception:
        pass

    # PyInstaller onefile / runtime extraction folder (best-effort)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "BUILD_INFO.txt")

    # If user runs from the extracted folder and cwd is that folder
    candidates.append(Path.cwd() / "BUILD_INFO.txt")

    for path in candidates:
        try:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            continue
    return None


def _read_version_from_pyproject() -> str | None:
    """Read version from pyproject.toml when running from a source checkout."""
    pyproject = _PROJECT_ROOT / "pyproject.toml"
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        project = data.get("project")
        if not isinstance(project, dict):
            return None
        version = project.get("version")
        return version if isinstance(version, str) else None
    except (FileNotFoundError, KeyError, OSError, tomllib.TOMLDecodeError):
        return None


def resolve_version() -> str:
    """
    Resolve runtime version.

    Source checkout / editable install: pyproject.toml (stale dist-info is ignored).
    Frozen EXE: BUILD_INFO.txt, then package metadata.
    Installed wheel without checkout: package metadata.
    """
    if _is_frozen():
        return _read_version_from_build_info() or _read_version_from_package_metadata() or "0.0.0"
    pyproject = _read_version_from_pyproject()
    if pyproject:
        return pyproject
    return _read_version_from_package_metadata() or _read_version_from_build_info() or "0.0.0"


try:
    __version__ = resolve_version()
except Exception:
    # Ultra-safe fallback: never crash import due to version probing.
    __version__ = "0.0.0"
