"""Unit tests for runtime log level helpers."""

from __future__ import annotations

import logging

import pytest

from irswitch.util.logging import get_runtime_log_level, set_runtime_log_level


def test_set_runtime_log_level_debug_and_info() -> None:
    set_runtime_log_level("INFO")
    assert get_runtime_log_level() == "INFO"
    assert logging.getLogger().getEffectiveLevel() == logging.INFO

    assert set_runtime_log_level("debug") == "DEBUG"
    assert get_runtime_log_level() == "DEBUG"
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

    assert set_runtime_log_level("INFO") == "INFO"


def test_set_runtime_log_level_rejects_other_levels() -> None:
    with pytest.raises(ValueError, match="DEBUG or INFO"):
        set_runtime_log_level("WARNING")
