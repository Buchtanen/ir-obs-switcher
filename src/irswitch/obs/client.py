"""OBS websocket client wrapper."""
from __future__ import annotations


class ObsClient:
    def __init__(self, ws_url: str, password: str) -> None:
        self.ws_url = ws_url
        self.password = password

    def is_connected(self) -> bool:
        return False
