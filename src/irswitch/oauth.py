"""OAuth 2.0 token management for YouTube API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)


# YouTube OAuth endpoints
GOOGLE_OAUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Default cooldown between interactive reauth attempts (browser open)
DEFAULT_REAUTH_COOLDOWN_S = 300.0


def _is_invalid_grant(error_text: str) -> bool:
    """Return True if Google token error indicates revoked/expired refresh token."""
    lowered = error_text.lower()
    return "invalid_grant" in lowered


@dataclass
class OAuthToken:
    """OAuth token data structure."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime  # UTC datetime when token expires
    token_type: str
    scope: str | None

    def is_expired(self, margin_seconds: int = 60) -> bool:
        """Check if token is expired or will expire soon."""
        expiry_threshold = datetime.now(UTC) + timedelta(seconds=margin_seconds)
        return self.expires_at <= expiry_threshold

    def expires_in_seconds(self) -> int:
        """Return seconds until token expiration."""
        now = datetime.now(UTC)
        if self.expires_at <= now:
            return 0
        return int((self.expires_at - now).total_seconds())

    def to_json(self) -> str:
        """Serialize token to JSON string."""
        data = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
            "token_type": self.token_type,
            "scope": self.scope,
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> OAuthToken | None:
        """Deserialize token from JSON string."""
        try:
            data = json.loads(json_str)
            return cls(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=datetime.fromisoformat(data["expires_at"]),
                token_type=data.get("token_type", "Bearer"),
                scope=data.get("scope"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Failed to parse OAuth token: {e}")
            return None


class OAuthManager:
    """
    Manages OAuth 2.0 authentication for YouTube API.

    Handles token storage, refresh, and access token retrieval.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_path: Path | str,
        scopes: list[str] | None = None,
    ) -> None:
        """
        Initialize OAuth manager.

        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: Redirect URI for OAuth callback
            token_path: Path to store/load OAuth tokens
            scopes: OAuth scopes to request (default: YouTube readonly)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_path = Path(token_path)
        self.scopes = scopes or ["https://www.googleapis.com/auth/youtube.readonly"]

        self._token: OAuthToken | None = None
        self._loaded_from_disk = False
        self._reauth_event: asyncio.Event | None = None
        self._reauth_cooldown_until: float = 0.0
        self._reauth_cooldown_s = DEFAULT_REAUTH_COOLDOWN_S

    def bind_reauth_event(self, event: asyncio.Event) -> None:
        """Bind an asyncio.Event used to wake the interactive reauth watchdog."""
        self._reauth_event = event

    def clear_local_token(self) -> None:
        """Delete persisted token and clear in-memory state (no Google revoke call)."""
        if self.token_path.exists():
            try:
                self.token_path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete OAuth token file: {e}")
        self._token = None
        self._loaded_from_disk = True  # avoid reloading deleted/corrupt file blindly
        logger.info("Local OAuth token cleared")

    def request_interactive_reauth(self, reason: str = "reauth_required") -> bool:
        """
        Request browser-based reauthorization (rate-limited).

        Returns:
            True if a new reauth was scheduled, False if skipped (cooldown / no event).
        """
        now = time.monotonic()
        if now < self._reauth_cooldown_until:
            logger.debug(
                "OAuth interactive reauth skipped (cooldown %.0fs remaining): %s",
                self._reauth_cooldown_until - now,
                reason,
            )
            return False

        self.clear_local_token()
        self._reauth_cooldown_until = now + self._reauth_cooldown_s

        if self._reauth_event is None:
            logger.warning(
                "OAuth reauth required (%s) but no reauth event bound; open /oauth/initiate manually",
                reason,
            )
            return False

        self._reauth_event.set()
        logger.warning("OAuth interactive reauth requested: %s", reason)
        return True

    def get_authorization_url(self, state: str) -> str:
        """
        Generate authorization URL for OAuth consent.

        Args:
            state: Random state string for CSRF protection

        Returns:
            Authorization URL to open in browser
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "access_type": "offline",
            "prompt": "consent",  # Force consent to get refresh token
            "state": state,
        }
        return f"{GOOGLE_OAUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        authorization_code: str,
        http_session: aiohttp.ClientSession,
    ) -> OAuthToken:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            authorization_code: Code received from OAuth callback
            http_session: aiohttp session for HTTP requests

        Returns:
            OAuthToken with access and refresh tokens

        Raises:
            OAuthError: If token exchange fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": authorization_code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }

        async with http_session.post(GOOGLE_TOKEN_URL, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise OAuthError(f"Token exchange failed ({response.status}): {error_text}")

            token_data = await response.json()

            expires_in = int(token_data.get("expires_in", 3600))
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            token = OAuthToken(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_at=expires_at,
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
            )

            await self.save_token(token)
            self._token = token
            logger.info("OAuth tokens obtained and saved")

            return token

    async def refresh_access_token(
        self,
        http_session: aiohttp.ClientSession,
    ) -> OAuthToken:
        """
        Refresh access token using refresh token.

        Args:
            http_session: aiohttp session for HTTP requests

        Returns:
            New OAuthToken with refreshed access token

        Raises:
            OAuthError: If refresh fails (no refresh token or invalid)
        """
        if self._token is None or self._token.refresh_token is None:
            raise OAuthError("No refresh token available")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self._token.refresh_token,
            "grant_type": "refresh_token",
        }

        async with http_session.post(GOOGLE_TOKEN_URL, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                if _is_invalid_grant(error_text):
                    self.clear_local_token()
                    raise OAuthReauthRequired(
                        f"Token refresh failed ({response.status}): {error_text}"
                    )
                raise OAuthError(f"Token refresh failed ({response.status}): {error_text}")

            token_data = await response.json()

            expires_in = int(token_data.get("expires_in", 3600))
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            # Prefer new refresh_token if Google rotated it
            refresh_token = token_data.get("refresh_token") or self._token.refresh_token

            token = OAuthToken(
                access_token=token_data["access_token"],
                refresh_token=refresh_token,
                expires_at=expires_at,
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
            )

            await self.save_token(token)
            self._token = token
            logger.info("OAuth access token refreshed")

            return token

    async def get_valid_access_token(
        self,
        http_session: aiohttp.ClientSession,
        *,
        request_reauth: bool = True,
    ) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Args:
            http_session: aiohttp session for HTTP requests
            request_reauth: If True, schedule interactive browser reauth on revoked token

        Returns:
            Valid access token string

        Raises:
            OAuthReauthRequired: Refresh token revoked — interactive reauth needed
            OAuthError: If no token available or refresh fails
        """
        # Load token from disk if not loaded
        if not self._loaded_from_disk:
            await self.load_token()
            self._loaded_from_disk = True

        if self._token is None:
            if request_reauth:
                self.request_interactive_reauth("missing_token")
            raise OAuthReauthRequired("No OAuth token available. Please authenticate first.")

        # Refresh if expired or expiring soon
        if self._token.is_expired(margin_seconds=120):
            logger.debug("OAuth token expired or expiring soon, refreshing...")
            try:
                await self.refresh_access_token(http_session)
            except OAuthReauthRequired:
                if request_reauth:
                    self.request_interactive_reauth("invalid_grant_or_missing_token")
                raise

        if self._token is None:
            if request_reauth:
                self.request_interactive_reauth("token_unavailable_after_refresh")
            raise OAuthReauthRequired("OAuth token unavailable after refresh")

        return self._token.access_token

    async def ensure_refreshable(
        self,
        http_session: aiohttp.ClientSession,
    ) -> bool:
        """
        Probe that we have a usable token (refresh if expired).

        Returns:
            True if access token is usable, False if interactive reauth is required.
        """
        try:
            await self.get_valid_access_token(http_session, request_reauth=False)
            return True
        except OAuthReauthRequired as e:
            logger.warning("OAuth token not usable: %s", e)
            return False
        except OAuthError as e:
            logger.warning("OAuth token check failed: %s", e)
            return False

    async def revoke_token(self, http_session: aiohttp.ClientSession) -> None:
        """
        Revoke current access token.

        Args:
            http_session: aiohttp session for HTTP requests
        """
        if self._token is None:
            return

        token_to_revoke = self._token.access_token

        async with http_session.post(
            GOOGLE_REVOKE_URL,
            data={"token": token_to_revoke},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ):
            pass  # Ignore response - revocation may fail but we continue

        # Delete local token file
        self.clear_local_token()
        logger.info("OAuth token revoked")

    async def save_token(self, token: OAuthToken) -> None:
        """Save token to disk."""
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(token.to_json(), encoding="utf-8")
        self._token = token
        self._loaded_from_disk = True
        logger.debug(f"OAuth token saved to {self.token_path}")

    async def load_token(self) -> bool:
        """Load token from disk."""
        if not self.token_path.exists():
            logger.debug(f"OAuth token file not found: {self.token_path}")
            self._token = None
            self._loaded_from_disk = True
            return False

        json_str = self.token_path.read_text(encoding="utf-8")
        token = OAuthToken.from_json(json_str)

        if token is None:
            logger.warning(f"Invalid OAuth token file: {self.token_path}")
            self._token = None
            self._loaded_from_disk = True
            return False

        self._token = token
        self._loaded_from_disk = True
        logger.debug(f"OAuth token loaded from {self.token_path}")
        return True

    def is_authenticated(self) -> bool:
        """Check if we have a valid (or expired) token loaded."""
        # Load token synchronously if not loaded yet
        if self._token is None and self.token_path.exists():
            try:
                json_str = self.token_path.read_text(encoding="utf-8")
                token = OAuthToken.from_json(json_str)
                if token is not None:
                    self._token = token
                    self._loaded_from_disk = True
                    logger.debug(f"OAuth token loaded synchronously from {self.token_path}")
            except Exception as e:
                logger.debug(f"Failed to load OAuth token synchronously: {e}")
        return self._token is not None

    def has_refresh_token(self) -> bool:
        """Check if we have a refresh token for automatic renewal."""
        return self._token is not None and self._token.refresh_token is not None


class OAuthError(Exception):
    """OAuth-related error."""

    pass


class OAuthReauthRequired(OAuthError):
    """Refresh token missing/revoked — interactive browser authorization required."""

    pass


# Factory function for creating OAuth manager from environment/config
def create_oauth_manager(
    client_id: str | None = None,
    client_secret: str | None = None,
    redirect_uri: str = "http://localhost:17321/oauth/callback",
    token_dir: str | None = None,
) -> OAuthManager | None:
    """
    Create OAuth manager from environment variables or return None if not configured.

    Environment variables:
        GOOGLE_OAUTH_CLIENT_ID: OAuth client ID
        GOOGLE_OAUTH_CLIENT_SECRET: OAuth client secret
        GOOGLE_OAUTH_REDIRECT_URI: Redirect URI (default: http://localhost:17321/oauth/callback)
        GOOGLE_OAUTH_TOKEN_DIR: Directory for token storage (default: app config dir)

    Args:
        client_id: Override client ID from env var
        client_secret: Override client secret from env var
        redirect_uri: Override redirect URI
        token_dir: Override token directory

    Returns:
        OAuthManager instance or None if not configured
    """
    oauth_client_id = client_id or os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    oauth_client_secret = client_secret or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    if not oauth_client_id or not oauth_client_secret:
        logger.debug("OAuth not configured - missing client ID or secret")
        return None

    oauth_redirect_uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", redirect_uri)

    if token_dir is None:
        # Default to app config directory
        # Handle PyInstaller EXE - use working directory instead of temp _MEIPASS
        if hasattr(sys, "frozen") and sys.frozen:
            # Running as PyInstaller EXE - use working directory
            if hasattr(sys, "_MEIPASS"):
                # PyInstaller onefile mode - use current working directory
                token_dir = os.environ.get("GOOGLE_OAUTH_TOKEN_DIR", str(Path.cwd() / "data"))
            else:
                # PyInstaller onedir mode - use exe directory
                token_dir = os.environ.get(
                    "GOOGLE_OAUTH_TOKEN_DIR", str(Path(sys.executable).parent / "data")
                )
        else:
            # Normal execution - use relative to source code
            token_dir = os.environ.get(
                "GOOGLE_OAUTH_TOKEN_DIR", str(Path(__file__).parent.parent.parent / "data")
            )

    token_path = Path(token_dir) / "youtube_oauth_token.json"

    return OAuthManager(
        client_id=oauth_client_id,
        client_secret=oauth_client_secret,
        redirect_uri=oauth_redirect_uri,
        token_path=token_path,
    )
