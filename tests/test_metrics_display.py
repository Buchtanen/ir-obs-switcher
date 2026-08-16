"""Tests for metrics display helpers."""

from __future__ import annotations

from irswitch.server.metrics_display import summarize_errors_total


def test_summarize_empty() -> None:
    assert summarize_errors_total(None) == (0, "")
    assert summarize_errors_total({}) == (0, "")


def test_summarize_total_and_breakdown_sorted() -> None:
    total, breakdown = summarize_errors_total(
        {"timeout_error": 1, "connection_error": 3, "other": 0}
    )
    assert total == 4
    assert breakdown == "connection_error: 3 · timeout_error: 1"
