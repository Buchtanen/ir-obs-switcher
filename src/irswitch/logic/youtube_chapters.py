"""YouTube VOD chapter block for video descriptions."""

from __future__ import annotations

import re
from collections.abc import Sequence

from irswitch.logic.stream_chapters import StreamChapter

CHAPTER_BEGIN = "--- irswitch chapters ---"
CHAPTER_END = "--- end irswitch chapters ---"
YOUTUBE_MIN_CHAPTER_GAP_S = 10
YOUTUBE_MIN_CHAPTERS = 3

YOUTUBE_WRITE_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    }
)
_TRACK_LINE = re.compile(r"(?im)^Track:\s*.*$")


def format_chapter_offset(seconds: int) -> str:
    value = max(0, int(seconds))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def chapters_for_youtube(chapters: Sequence[StreamChapter]) -> list[StreamChapter]:
    """Keep YouTube-legal stamps: 00:00 first, ascending, ≥10s apart."""
    ordered = sorted(chapters, key=lambda c: (int(c.offset_seconds), int(c.created_at_ms)))
    out: list[StreamChapter] = []
    for chapter in ordered:
        offset = max(0, int(chapter.offset_seconds))
        if not out:
            if offset != 0:
                continue
            out.append(chapter)
            continue
        if offset - out[-1].offset_seconds < YOUTUBE_MIN_CHAPTER_GAP_S:
            continue
        out.append(chapter)
    return out


def render_chapter_block(chapters: Sequence[StreamChapter]) -> str:
    lines: list[str] = []
    for chapter in chapters_for_youtube(chapters):
        title = str(chapter.title).strip() or "Chapter"
        lines.append(f"{format_chapter_offset(chapter.offset_seconds)} {title}")
    return "\n".join(lines)


def merge_chapter_block(description: str, chapter_text: str) -> str:
    """Replace or append a marked chapter block; keep the rest of the description."""
    body = (description or "").replace("\r\n", "\n")
    block = f"{CHAPTER_BEGIN}\n{chapter_text.strip()}\n{CHAPTER_END}"
    start = body.find(CHAPTER_BEGIN)
    if start >= 0:
        end = body.find(CHAPTER_END, start)
        if end >= 0:
            end += len(CHAPTER_END)
            return (body[:start].rstrip() + "\n\n" + block + body[end:].lstrip("\n")).strip() + "\n"
        return body[:start].rstrip() + "\n\n" + block + "\n"
    if not body.strip():
        return block + "\n"
    return body.rstrip() + "\n\n" + block + "\n"


def apply_weekend_track(description: str, track: str | None) -> str:
    """Replace a ``Track:`` line with the WeekendInfo display name. No-op if missing."""
    name = (track or "").strip()
    body = description or ""
    if not name or not _TRACK_LINE.search(body):
        return body
    return _TRACK_LINE.sub(f"Track: {name}", body, count=1)


def token_allows_video_update(scope: str | None) -> bool:
    if not scope:
        return False
    parts = {part.strip() for part in scope.replace(",", " ").split() if part.strip()}
    return bool(parts & YOUTUBE_WRITE_SCOPES)
