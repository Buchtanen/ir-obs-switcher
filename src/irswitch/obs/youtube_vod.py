"""Push in-memory stream chapters into the YouTube VOD description. Fail-soft."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import aiohttp

from irswitch.logic.stream_chapters import StreamChapter
from irswitch.logic.youtube_chapters import (
    merge_chapter_block,
    render_chapter_block,
    token_allows_video_update,
)
from irswitch.oauth import OAuthError, OAuthReauthRequired

logger = logging.getLogger(__name__)

_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


async def push_youtube_vod_chapters(
    *,
    oauth_manager: Any,
    video_id: str,
    chapters: Sequence[StreamChapter],
) -> bool:
    """Replace the marked chapter block on the YouTube video description.

    Returns True when YouTube accepted the update. Never raises to callers.
    """
    if not video_id or not chapters:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            try:
                access_token = await oauth_manager.get_valid_access_token(
                    session, request_reauth=False
                )
            except (OAuthReauthRequired, OAuthError):
                logger.info("youtube VOD chapters skipped: OAuth token not usable")
                return False
            token = getattr(oauth_manager, "_token", None)
            scope = getattr(token, "scope", None) if token is not None else None
            if not token_allows_video_update(scope):
                logger.info(
                    "youtube VOD chapters skipped: token is youtube.readonly; "
                    "re-authorize at /oauth/initiate"
                )
                return False
            headers = {"Authorization": f"Bearer {access_token}"}
            snippet = await _fetch_snippet(session, headers, video_id)
            if snippet is None:
                return False
            description = str(snippet.get("description") or "")
            updated = merge_chapter_block(description, render_chapter_block(chapters))
            if _descriptions_equal(description, updated):
                return True
            snippet = dict(snippet)
            snippet["description"] = updated.rstrip("\n")
            title = snippet.get("title")
            category_id = snippet.get("categoryId")
            if not title or not category_id:
                logger.warning("youtube VOD chapters skipped: snippet missing title/categoryId")
                return False
            payload = {"id": video_id, "snippet": snippet}
            async with session.put(
                _VIDEOS_URL,
                params={"part": "snippet"},
                json=payload,
                headers={**headers, "Content-Type": "application/json"},
            ) as response:
                if response.status in (200, 201):
                    logger.info(
                        "youtube VOD chapters updated video_id=%s count=%s",
                        video_id,
                        len(chapters),
                    )
                    return True
                body = await response.text()
                logger.warning(
                    "youtube VOD chapters update failed status=%s body=%s",
                    response.status,
                    body[:300],
                )
                return False
    except Exception:
        logger.exception("youtube VOD chapters push failed")
        return False


def _descriptions_equal(left: str, right: str) -> bool:
    return left.replace("\r\n", "\n").rstrip("\n") == right.replace("\r\n", "\n").rstrip("\n")


async def _fetch_snippet(
    session: aiohttp.ClientSession,
    headers: dict[str, str],
    video_id: str,
) -> dict[str, Any] | None:
    async with session.get(
        _VIDEOS_URL,
        params={"part": "snippet", "id": video_id},
        headers=headers,
    ) as response:
        if response.status != 200:
            body = await response.text()
            logger.warning(
                "youtube VOD chapters list failed status=%s body=%s",
                response.status,
                body[:300],
            )
            return None
        data = await response.json()
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        logger.warning("youtube VOD chapters list empty video_id=%s", video_id)
        return None
    snippet = items[0].get("snippet") if isinstance(items[0], dict) else None
    if not isinstance(snippet, dict):
        return None
    return snippet
