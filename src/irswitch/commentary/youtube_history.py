"""Bounded, cached YouTube history for prepared-commentary wording diversity."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from irswitch.oauth import OAuthError, OAuthReauthRequired

logger = logging.getLogger(__name__)

_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_REFRESH_INTERVAL_S = 30 * 60


class YouTubeHistorySource:
    """Fetch public completed streams from the already configured Google account."""

    def __init__(self, oauth_manager: Any | None) -> None:
        self.oauth_manager = oauth_manager
        self.enabled = False
        self.days = 90
        self.max_items = 100
        self.state = "disabled"
        self.titles: tuple[str, ...] = ()
        self.last_error: str | None = None
        self._last_refresh = 0.0
        self._task: asyncio.Task[None] | None = None

    def configure(self, *, enabled: bool, days: int, max_items: int) -> None:
        self.enabled = enabled
        self.days = days
        self.max_items = max_items
        if not enabled:
            self.state = "disabled"
            if self._task is not None:
                self._task.cancel()
                self._task = None
        elif self.oauth_manager is None:
            self.state = "not_configured"

    def observe(self) -> None:
        if not self.enabled or self.oauth_manager is None:
            return
        if self._task is not None and not self._task.done():
            return
        if self._last_refresh and time.monotonic() - self._last_refresh < _REFRESH_INTERVAL_S:
            return
        self.state = "loading"
        self._task = asyncio.create_task(self._refresh(), name="youtube-commentary-history")

    async def close(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._task = None

    def status(self) -> dict[str, object]:
        return {
            "state": self.state,
            "items": len(self.titles),
            "lastErrorCode": self.last_error,
        }

    async def _refresh(self) -> None:
        try:
            oauth_manager = self.oauth_manager
            if oauth_manager is None:
                self.state = "not_configured"
                return
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                token = await oauth_manager.get_valid_access_token(session, request_reauth=False)
                headers = {"Authorization": f"Bearer {token}"}
                uploads = await _uploads_playlist(session, headers)
                video_ids = await _playlist_video_ids(
                    session, headers, uploads, max_items=self.max_items * 2
                )
                items = await _video_items(session, headers, video_ids)
            cutoff = datetime.now(UTC) - timedelta(days=self.days)
            self.titles = parse_completed_stream_titles(
                items, cutoff=cutoff, max_items=self.max_items
            )
            self.state = "ready"
            self.last_error = None
            self._last_refresh = time.monotonic()
            logger.info("youtube commentary history refreshed items=%s", len(self.titles))
        except asyncio.CancelledError:
            raise
        except (OAuthError, OAuthReauthRequired):
            self.state = "auth_error"
            self.last_error = "oauth"
        except Exception:
            self.state = "api_error"
            self.last_error = "transport"
            logger.warning("youtube commentary history refresh failed", exc_info=True)
        finally:
            # Success and failure are both cached so a telemetry-rate context stream
            # cannot turn an unavailable external API into a retry storm.
            self._last_refresh = time.monotonic()
            self._task = None


def parse_completed_stream_titles(
    items: Iterable[object], *, cutoff: datetime, max_items: int
) -> tuple[str, ...]:
    """Keep only public streams with an actual end time, newest first."""
    accepted: list[tuple[datetime, str]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        snippet = raw.get("snippet")
        status = raw.get("status")
        live = raw.get("liveStreamingDetails")
        if (
            not isinstance(snippet, dict)
            or not isinstance(status, dict)
            or not isinstance(live, dict)
        ):
            continue
        if status.get("privacyStatus") != "public" or not live.get("actualEndTime"):
            continue
        published = _parse_timestamp(snippet.get("publishedAt"))
        title = str(snippet.get("title") or "").strip()
        if published is None or published < cutoff or not title:
            continue
        accepted.append((published, title))
    accepted.sort(key=lambda item: item[0], reverse=True)
    return tuple(title for _, title in accepted[: max(0, max_items)])


async def _uploads_playlist(session: aiohttp.ClientSession, headers: dict[str, str]) -> str:
    data = await _get_json(
        session,
        _CHANNELS_URL,
        headers,
        {"part": "contentDetails", "mine": "true", "maxResults": "1"},
    )
    items = data.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("channel_missing")
    content = items[0].get("contentDetails")
    related = content.get("relatedPlaylists") if isinstance(content, dict) else None
    uploads = related.get("uploads") if isinstance(related, dict) else None
    if not isinstance(uploads, str) or not uploads:
        raise ValueError("uploads_missing")
    return uploads


async def _playlist_video_ids(
    session: aiohttp.ClientSession,
    headers: dict[str, str],
    playlist_id: str,
    *,
    max_items: int,
) -> list[str]:
    video_ids: list[str] = []
    page_token: str | None = None
    while len(video_ids) < max_items:
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": "50"}
        if page_token:
            params["pageToken"] = page_token
        data = await _get_json(session, _PLAYLIST_ITEMS_URL, headers, params)
        items = data.get("items")
        if not isinstance(items, list):
            break
        for item in items:
            details = item.get("contentDetails") if isinstance(item, dict) else None
            video_id = details.get("videoId") if isinstance(details, dict) else None
            if isinstance(video_id, str) and video_id:
                video_ids.append(video_id)
                if len(video_ids) >= max_items:
                    break
        raw_token = data.get("nextPageToken")
        page_token = raw_token if isinstance(raw_token, str) and raw_token else None
        if page_token is None:
            break
    return video_ids


async def _video_items(
    session: aiohttp.ClientSession, headers: dict[str, str], video_ids: list[str]
) -> list[object]:
    out: list[object] = []
    for start in range(0, len(video_ids), 50):
        data = await _get_json(
            session,
            _VIDEOS_URL,
            headers,
            {
                "part": "snippet,status,liveStreamingDetails",
                "id": ",".join(video_ids[start : start + 50]),
                "maxResults": "50",
            },
        )
        items = data.get("items")
        if isinstance(items, list):
            out.extend(items)
    return out


async def _get_json(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
    params: dict[str, str],
) -> dict[str, Any]:
    async with session.get(url, headers=headers, params=params) as response:
        if response.status != 200:
            raise RuntimeError(f"youtube_http_{response.status}")
        data = await response.json()
    if not isinstance(data, dict):
        raise ValueError("youtube_json")
    return data


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
