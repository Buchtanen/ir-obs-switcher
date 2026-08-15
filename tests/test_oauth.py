"""Tests for OAuth token refresh / reauth behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from irswitch.oauth import OAuthManager, OAuthReauthRequired, OAuthToken, _is_invalid_grant


def _manager(tmp_path: Path) -> OAuthManager:
    return OAuthManager(
        client_id="client",
        client_secret="secret",
        redirect_uri="http://localhost:17321/oauth/callback",
        token_path=tmp_path / "youtube_oauth_token.json",
    )


def test_is_invalid_grant_detects_google_error() -> None:
    assert _is_invalid_grant('{"error":"invalid_grant","error_description":"Bad Request"}')
    assert not _is_invalid_grant('{"error":"invalid_client"}')


@pytest.mark.asyncio
async def test_refresh_invalid_grant_clears_token_and_raises(tmp_path: Path) -> None:
    mgr = _manager(tmp_path)
    mgr._token = OAuthToken(
        access_token="old",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
        token_type="Bearer",
        scope=None,
    )
    await mgr.save_token(mgr._token)
    assert mgr.token_path.exists()

    response = MagicMock()
    response.status = 400
    response.text = AsyncMock(
        return_value=json.dumps({"error": "invalid_grant", "error_description": "Bad Request"})
    )
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.post = MagicMock(return_value=response)

    with pytest.raises(OAuthReauthRequired):
        await mgr.refresh_access_token(session)

    assert mgr._token is None
    assert not mgr.token_path.exists()


@pytest.mark.asyncio
async def test_get_valid_access_token_requests_reauth_on_invalid_grant(
    tmp_path: Path,
) -> None:
    mgr = _manager(tmp_path)
    mgr._token = OAuthToken(
        access_token="old",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
        token_type="Bearer",
        scope=None,
    )
    mgr._loaded_from_disk = True

    import asyncio

    event = asyncio.Event()
    mgr.bind_reauth_event(event)

    response = MagicMock()
    response.status = 400
    response.text = AsyncMock(return_value='{"error":"invalid_grant"}')
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post = MagicMock(return_value=response)

    with pytest.raises(OAuthReauthRequired):
        await mgr.get_valid_access_token(session)

    assert event.is_set()
    assert mgr._token is None


def test_request_interactive_reauth_cooldown(tmp_path: Path) -> None:
    import asyncio

    mgr = _manager(tmp_path)
    event = asyncio.Event()
    mgr.bind_reauth_event(event)
    mgr._reauth_cooldown_s = 60.0

    assert mgr.request_interactive_reauth("first") is True
    assert event.is_set()
    event.clear()
    assert mgr.request_interactive_reauth("second") is False
    assert not event.is_set()
