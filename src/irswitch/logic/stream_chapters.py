"""In-memory stream chapter markers for WS / status.

YouTube VOD description writes after the stream ends in ``obs.youtube_vod``
(called from the API layer when ``[stream_chapters] youtube_vod = true``).
"""

from __future__ import annotations

import configparser
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Ignore brief OBS stream flicker; clear / re-start only after this gap (seconds).
STREAM_FLICKER_DEBOUNCE_S = 2.0

DEFAULT_TRIGGER_SESSION_TYPES: tuple[str, ...] = ("Practice", "Qualify", "Race")
DEFAULT_START_TITLE = "Stream start"
DEFAULT_END_TITLE = "Stream end"


@dataclass(frozen=True)
class StreamChaptersSettings:
    """Config for stream chapter markers ([stream_chapters])."""

    enabled: bool = False
    start_title: str = DEFAULT_START_TITLE
    end_title: str = DEFAULT_END_TITLE
    trigger_session_types: tuple[str, ...] = DEFAULT_TRIGGER_SESSION_TYPES
    # Lowercase session_type -> display title
    session_titles: Mapping[str, str] = field(default_factory=dict)
    # Write chapter timestamps into the YouTube VOD description (needs youtube write scope).
    youtube_vod: bool = False


@dataclass(frozen=True)
class StreamChapter:
    """One chapter marker for the current OBS stream session."""

    title: str
    offset_seconds: int
    session_type: str | None
    created_at_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "offset_seconds": self.offset_seconds,
            "session_type": self.session_type,
            "created_at_ms": self.created_at_ms,
        }


def _normalize_session_type(session_type: str | None) -> str | None:
    if session_type is None:
        return None
    text = str(session_type).strip()
    if not text or text.lower() == "test":
        return None
    return text


def _offset_seconds(duration_current: float | None) -> int:
    if duration_current is None:
        return 0
    try:
        value = float(duration_current)
    except (TypeError, ValueError):
        return 0
    if value < 0:
        return 0
    return int(value)


class StreamChapterTracker:
    """Tracks chapter markers for the active stream; pure logic, no IO."""

    def __init__(
        self,
        settings: StreamChaptersSettings | None = None,
        *,
        time_mono: Callable[[], float] | None = None,
        time_wall_ms: Callable[[], int] | None = None,
    ) -> None:
        self._settings = settings or StreamChaptersSettings()
        self._time_mono = time_mono or time.monotonic
        self._time_wall_ms = time_wall_ms or (lambda: int(time.time() * 1000))
        self._chapters: list[StreamChapter] = []
        self._streaming = False
        self._pending_stop_mono: float | None = None
        self._last_session_type: str | None = None
        self._pending_new: list[StreamChapter] = []
        self._last_offset = 0
        self._end_appended = False
        self._vod_flush_pending = False

    @property
    def settings(self) -> StreamChaptersSettings:
        return self._settings

    def apply_settings(self, settings: StreamChaptersSettings) -> None:
        """Hot-reload settings. Disabling clears markers."""
        was_enabled = self._settings.enabled
        self._settings = settings
        if was_enabled and not settings.enabled:
            self.clear()
            self._streaming = False
            self._pending_stop_mono = None
            self._last_session_type = None
            self._vod_flush_pending = False

    def clear(self) -> None:
        self._chapters.clear()
        self._pending_new.clear()
        self._end_appended = False
        self._last_offset = 0
        self._vod_flush_pending = False

    def consume_vod_flush(self) -> bool:
        """True once after stream end / QUIT freeze, until the next arm."""
        if not self._vod_flush_pending:
            return False
        self._vod_flush_pending = False
        return True

    def prepare_vod_flush(self) -> None:
        """Arm a YouTube VOD rewrite without waiting for OBS streaming=false."""
        if not self._settings.enabled or not self._chapters:
            return
        self._append_end_if_needed()
        self._vod_flush_pending = True

    def chapters(self) -> list[StreamChapter]:
        return list(self._chapters)

    def chapters_as_dicts(self) -> list[dict[str, object]]:
        return [c.to_dict() for c in self._chapters]

    def take_pending(self) -> list[StreamChapter]:
        pending = list(self._pending_new)
        self._pending_new.clear()
        return pending

    def _title_for_session(self, session_type: str) -> str:
        key = session_type.lower()
        custom = self._settings.session_titles.get(key)
        if custom:
            return custom
        return session_type

    def _triggers(self) -> set[str]:
        return {t.lower() for t in self._settings.trigger_session_types}

    def _append(
        self,
        *,
        title: str,
        offset_seconds: int,
        session_type: str | None,
    ) -> StreamChapter:
        chapter = StreamChapter(
            title=title,
            offset_seconds=offset_seconds,
            session_type=session_type,
            created_at_ms=int(self._time_wall_ms()),
        )
        self._chapters.append(chapter)
        self._pending_new.append(chapter)
        logger.info(
            "stream_chapter title=%r offset_seconds=%s session_type=%r",
            title,
            offset_seconds,
            session_type,
        )
        return chapter

    def _append_end_if_needed(self) -> None:
        title = (self._settings.end_title or "").strip()
        if not title or self._end_appended or not self._chapters:
            return
        last = self._chapters[-1]
        offset = max(self._last_offset, last.offset_seconds)
        if offset - last.offset_seconds < 10:
            return
        self._append(title=title, offset_seconds=offset, session_type=None)
        self._end_appended = True

    def _start_stream(self, duration_current: float | None, session_type: str | None) -> None:
        self.clear()
        self._streaming = True
        self._pending_stop_mono = None
        self._last_session_type = session_type
        self._last_offset = 0
        self._append(
            title=self._settings.start_title,
            offset_seconds=0,
            session_type=None,
        )
        _ = duration_current

    def _confirm_stop(self) -> None:
        self._append_end_if_needed()
        self._streaming = False
        self._pending_stop_mono = None
        self._vod_flush_pending = True

    def update(
        self,
        *,
        streaming: bool,
        duration_current_seconds: float | None,
        session_type: str | None,
    ) -> list[StreamChapter]:
        """
        Advance tracker from latest streaming / session snapshot.

        Returns newly created chapters since the previous ``take_pending`` /
        update cycle (also stored until ``take_pending``).
        """
        if not self._settings.enabled:
            if self._chapters or self._streaming or self._pending_stop_mono is not None:
                self.clear()
                self._streaming = False
                self._pending_stop_mono = None
                self._last_session_type = None
            return []

        now = float(self._time_mono())
        normalized = _normalize_session_type(session_type)
        before = len(self._pending_new)

        try:
            if streaming:
                if self._pending_stop_mono is not None:
                    # Flicker resume within debounce — keep history, no new start.
                    self._pending_stop_mono = None
                    self._streaming = True
                elif not self._streaming:
                    self._start_stream(duration_current_seconds, normalized)
                else:
                    self._maybe_session_chapter(normalized, duration_current_seconds)
                self._last_offset = _offset_seconds(duration_current_seconds)
            else:
                if self._streaming and self._pending_stop_mono is None:
                    self._pending_stop_mono = now
                elif self._pending_stop_mono is not None:
                    if now - self._pending_stop_mono >= STREAM_FLICKER_DEBOUNCE_S:
                        self._confirm_stop()
        except Exception:
            logger.exception("stream_chapters update failed; continuing")
            return []

        return list(self._pending_new[before:])

    def _maybe_session_chapter(
        self,
        session_type: str | None,
        duration_current_seconds: float | None,
    ) -> None:
        if session_type is None:
            return
        if session_type.lower() not in self._triggers():
            # Still remember last seen type so leaving a non-trigger then
            # entering a trigger fires once.
            if session_type != self._last_session_type:
                self._last_session_type = session_type
            return
        if session_type == self._last_session_type:
            return
        self._last_session_type = session_type
        self._append(
            title=self._title_for_session(session_type),
            offset_seconds=_offset_seconds(duration_current_seconds),
            session_type=session_type,
        )


def load_stream_chapters_settings(parser: configparser.ConfigParser) -> StreamChaptersSettings:
    """Parse optional ``[stream_chapters]`` from a ConfigParser."""
    defaults = StreamChaptersSettings()
    if not parser.has_section("stream_chapters"):
        return defaults

    enabled = parser.getboolean("stream_chapters", "enabled", fallback=defaults.enabled)
    start_title = parser.get(
        "stream_chapters", "start_title", fallback=defaults.start_title
    ).strip()
    if not start_title:
        start_title = defaults.start_title

    raw_end = parser.get("stream_chapters", "end_title", fallback=defaults.end_title)
    end_title = raw_end.strip() if raw_end is not None else defaults.end_title

    raw_triggers = parser.get(
        "stream_chapters",
        "trigger_session_types",
        fallback=",".join(defaults.trigger_session_types),
    )
    triggers = tuple(
        part.strip()
        for part in raw_triggers.split(",")
        if part.strip() and part.strip().lower() != "test"
    )
    if not triggers:
        triggers = defaults.trigger_session_types

    titles: dict[str, str] = {}
    try:
        for key, value in parser.items("stream_chapters"):
            key_l = key.strip().lower()
            if key_l.startswith("title_") and value.strip():
                titles[key_l[len("title_") :]] = value.strip()
            elif (
                key_l in {"practice", "qualify", "race", "warmup", "lone qualify"} and value.strip()
            ):
                titles[key_l] = value.strip()
    except Exception:
        logger.debug("Failed reading stream_chapters title keys", exc_info=True)

    youtube_vod = parser.getboolean("stream_chapters", "youtube_vod", fallback=defaults.youtube_vod)

    return StreamChaptersSettings(
        enabled=enabled,
        start_title=start_title,
        end_title=end_title,
        trigger_session_types=triggers,
        session_titles=titles,
        youtube_vod=youtube_vod,
    )
