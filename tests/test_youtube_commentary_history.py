from __future__ import annotations

from datetime import UTC, datetime

from irswitch.commentary.youtube_history import (
    YouTubeHistorySource,
    parse_completed_stream_titles,
)


def _item(
    title: str,
    published: str,
    *,
    privacy: str = "public",
    ended: bool = True,
) -> dict[str, object]:
    return {
        "snippet": {"title": title, "publishedAt": published},
        "status": {"privacyStatus": privacy},
        "liveStreamingDetails": {"actualEndTime": published} if ended else {},
    }


def test_history_keeps_only_recent_public_completed_streams() -> None:
    titles = parse_completed_stream_titles(
        [
            _item("new", "2026-09-03T20:00:00Z"),
            _item("private", "2026-09-02T20:00:00Z", privacy="private"),
            _item("still live", "2026-09-02T19:00:00Z", ended=False),
            _item("old", "2025-01-01T00:00:00Z"),
            _item("second", "2026-09-01T20:00:00Z"),
        ],
        cutoff=datetime(2026, 8, 1, tzinfo=UTC),
        max_items=2,
    )

    assert titles == ("new", "second")


def test_history_without_oauth_is_explicitly_not_configured() -> None:
    source = YouTubeHistorySource(None)
    source.configure(enabled=True, days=90, max_items=100)
    source.observe()

    assert source.status() == {
        "state": "not_configured",
        "items": 0,
        "lastErrorCode": None,
    }
