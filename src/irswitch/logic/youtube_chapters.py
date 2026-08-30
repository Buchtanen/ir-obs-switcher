"""YouTube VOD chapter block for video descriptions."""

from __future__ import annotations

from collections.abc import Sequence

from irswitch.logic.stream_chapters import StreamChapter

CHAPTER_BEGIN = "--- irswitch chapters ---"
CHAPTER_END = "--- end irswitch chapters ---"

YOUTUBE_WRITE_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    }
)


def format_chapter_offset(seconds: int) -> str:
    value = max(0, int(seconds))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def render_chapter_block(chapters: Sequence[StreamChapter]) -> str:
    lines: list[str] = []
    for chapter in chapters:
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


def token_allows_video_update(scope: str | None) -> bool:
    if not scope:
        return False
    parts = {part.strip() for part in scope.replace(",", " ").split() if part.strip()}
    return bool(parts & YOUTUBE_WRITE_SCOPES)
