"""YouTube VOD chapter description formatting (no API)."""

from __future__ import annotations

from irswitch.logic.stream_chapters import StreamChapter
from irswitch.logic.youtube_chapters import (
    CHAPTER_BEGIN,
    CHAPTER_END,
    apply_weekend_track,
    chapters_for_youtube,
    format_chapter_offset,
    merge_chapter_block,
    render_chapter_block,
    token_allows_video_update,
)


def test_format_chapter_offset() -> None:
    assert format_chapter_offset(0) == "00:00"
    assert format_chapter_offset(42) == "00:42"
    assert format_chapter_offset(842) == "14:02"
    assert format_chapter_offset(3661) == "1:01:01"


def test_render_and_merge_replaces_marked_block() -> None:
    chapters = (
        StreamChapter("Stream start", 0, None, 1),
        StreamChapter("Practice", 12, "Practice", 2),
        StreamChapter("Race", 842, "Race", 3),
    )
    block = render_chapter_block(chapters)
    assert "00:00 Stream start" in block
    assert "00:12 Practice" in block
    assert "14:02 Race" in block

    original = "Manual notes\nkeep me\n"
    first = merge_chapter_block(original, block)
    assert first.startswith("Manual notes")
    assert CHAPTER_BEGIN in first
    assert "00:00 Stream start" in first

    second = merge_chapter_block(first, render_chapter_block(chapters[:2]))
    assert second.count(CHAPTER_BEGIN) == 1
    assert "14:02 Race" not in second
    assert "keep me" in second


def test_apply_weekend_track_rewrites_track_line() -> None:
    original = "Overlay Commentary Test\nTrack: Imola\nWeather: Rain\n"
    out = apply_weekend_track(original, "Okayama International Circuit - Full Course")
    assert "Track: Okayama International Circuit - Full Course" in out
    assert "Track: Imola" not in out
    assert "Weather: Rain" in out
    assert apply_weekend_track(original, "  ") == original
    assert apply_weekend_track("No track line here", "Okayama") == "No track line here"


def test_merge_into_empty_description() -> None:
    out = merge_chapter_block("", "00:00 Stream start")
    assert CHAPTER_BEGIN in out
    assert CHAPTER_END in out
    assert "00:00 Stream start" in out


def test_token_allows_video_update() -> None:
    assert token_allows_video_update("https://www.googleapis.com/auth/youtube")
    assert token_allows_video_update(
        "https://www.googleapis.com/auth/youtube.force-ssl "
        "https://www.googleapis.com/auth/userinfo.email"
    )
    assert not token_allows_video_update("https://www.googleapis.com/auth/youtube.readonly")
    assert not token_allows_video_update(None)
    assert not token_allows_video_update("")


def test_chapters_for_youtube_keeps_zero_and_drops_sub_10s_gaps() -> None:
    raw = (
        StreamChapter("Stream start", 0, None, 1),
        StreamChapter("Too close", 4, "Practice", 2),
        StreamChapter("Practice", 12, "Practice", 3),
        StreamChapter("Race", 842, "Race", 4),
    )
    out = chapters_for_youtube(raw)
    assert [c.title for c in out] == ["Stream start", "Practice", "Race"]
    assert out[0].offset_seconds == 0
