"""Tests for runtime version resolution."""

from __future__ import annotations

import tomllib
from pathlib import Path

import irswitch


def test_resolve_version_in_checkout_matches_pyproject() -> None:
    """Editable/venv install must not keep a stale dist-info version."""
    root = Path(__file__).resolve().parents[1]
    with open(root / "pyproject.toml", "rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    assert irswitch.resolve_version() == expected


def test_checkout_prefers_pyproject_over_stale_metadata(monkeypatch) -> None:
    monkeypatch.setattr(irswitch, "_is_frozen", lambda: False)
    monkeypatch.setattr(irswitch, "_read_version_from_pyproject", lambda: "1.0.0")
    monkeypatch.setattr(irswitch, "_read_version_from_package_metadata", lambda: "0.7.0")
    monkeypatch.setattr(irswitch, "_read_version_from_build_info", lambda: None)
    assert irswitch.resolve_version() == "1.0.0"


def test_frozen_prefers_build_info(monkeypatch) -> None:
    monkeypatch.setattr(irswitch, "_is_frozen", lambda: True)
    monkeypatch.setattr(irswitch, "_read_version_from_build_info", lambda: "1.0.0")
    monkeypatch.setattr(irswitch, "_read_version_from_pyproject", lambda: "9.9.9")
    monkeypatch.setattr(irswitch, "_read_version_from_package_metadata", lambda: "0.7.0")
    assert irswitch.resolve_version() == "1.0.0"


def test_installed_wheel_uses_package_metadata(monkeypatch) -> None:
    monkeypatch.setattr(irswitch, "_is_frozen", lambda: False)
    monkeypatch.setattr(irswitch, "_read_version_from_pyproject", lambda: None)
    monkeypatch.setattr(irswitch, "_read_version_from_package_metadata", lambda: "1.2.3")
    monkeypatch.setattr(irswitch, "_read_version_from_build_info", lambda: None)
    assert irswitch.resolve_version() == "1.2.3"
