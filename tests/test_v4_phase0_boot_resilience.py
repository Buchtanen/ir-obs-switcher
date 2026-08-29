"""Phase 0: V4 boot resilience contracts (JS + presentation payload)."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from golden_v4_shared import display_v4_js

from irswitch.overlay.http import presentation_payload, web_root
from irswitch.overlay.settings import OverlaySettings, OverlayV4Settings


def overlay_js() -> str:
    return (web_root() / "overlay" / "js" / "overlay.js").read_text(encoding="utf-8")


def test_init_v4_marks_manifest_status_and_catches_failures() -> None:
    js = display_v4_js()
    assert "dataset.v4Manifest" in js
    assert '"fallback"' in js or "'fallback'" in js
    assert '"ok"' in js or "'ok'" in js
    assert "initV4" in js
    # Parse failures must not escape initV4.
    assert "manifestRes.json()" in js
    assert "catch" in js


def test_overlay_bootstrap_connects_ws_after_v4_init_failure() -> None:
    """Live V4 path must still call connectOverlay even if initV4 throws."""
    js = overlay_js()
    marker = 'window.__renderer = "v4";'
    live_idx = js.find(marker)
    assert live_idx >= 0, "expected V4 bootstrap branch"
    branch = js[live_idx : live_idx + 1600]
    assert "await initV4(" in branch
    assert "finally" in branch
    assert "connectOverlay()" in branch
    assert "if (demo)" in branch
    # connectOverlay must not be only inside the demo-false path after an uncaught await.
    finally_idx = branch.find("finally")
    connect_idx = branch.find("connectOverlay()", finally_idx)
    assert connect_idx > finally_idx


def test_presentation_payload_survives_broken_v4_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = replace(
        OverlaySettings(),
        theme="cyber_racing",
        v4=OverlayV4Settings(assets=True, renderer=True),
    )
    monkeypatch.setattr(
        "irswitch.server.api.get_app_config",
        lambda: SimpleNamespace(overlay=overlay),
    )

    def boom(*_a, **_k):  # noqa: ANN001
        raise RuntimeError("manifest corrupt")

    with patch("irswitch.overlay.http.V4AssetResolver.load", side_effect=boom):
        payload = presentation_payload()
    assert payload["theme"] == "cyber_racing"
    assert "v4" in payload
    assert payload["v4"]["assets"] is True
    assert payload["v4"]["renderer"] is True
    assert payload["v4"]["resolved"] is None
    assert payload["v4"]["manifestError"]
