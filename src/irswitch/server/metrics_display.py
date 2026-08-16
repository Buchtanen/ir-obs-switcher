"""Helpers for presenting metrics on dashboards."""

from __future__ import annotations


def summarize_errors_total(errors_total: dict[str, int] | None) -> tuple[int, str]:
    """
    Summarize errors_total for GR metrics display.

    Returns:
        (total_count, breakdown_text) where breakdown is "type: n · ..." or "".
    """
    if not errors_total:
        return 0, ""

    total = sum(int(v) for v in errors_total.values())
    parts = [
        f"{key}: {count}"
        for key, count in sorted(errors_total.items(), key=lambda item: (-int(item[1]), item[0]))
        if int(count) > 0
    ]
    return total, " · ".join(parts)
