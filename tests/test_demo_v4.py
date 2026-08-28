"""V4 cyclic dry-test demo wiring and asset checks."""

from __future__ import annotations

from irswitch.overlay.http import web_root


def _demo_v4_js() -> str:
    return (web_root() / "overlay" / "js" / "demo-v4.js").read_text(encoding="utf-8")


def _overlay_js() -> str:
    return (web_root() / "overlay" / "js" / "overlay.js").read_text(encoding="utf-8")


def _demo_html() -> str:
    return (web_root() / "demo" / "index.html").read_text(encoding="utf-8")


def test_demo_v4_js_exists_and_exports_loop() -> None:
    js = _demo_v4_js()
    assert "export function startV4DemoLoop" in js
    assert "export function stopV4Demo" in js
    assert "const LOOP_MS = 28000" in js
    assert 'type: "overlay-demo-cue"' in js


def test_demo_v4_js_uses_display_v4_fixtures() -> None:
    js = _demo_v4_js()
    for name in (
        "v4FixtureHunting",
        "v4FixtureHunted",
        "v4FixtureLapComplete",
        "v4FixturePersonalBest",
        "v4FixturePositionGained",
        "v4FixtureIncident",
        "v4FixtureHrPressure",
        "v4FixtureFinalLap",
        "v4FixtureFinish",
        "DisplayV4",
        "syncSysinfoGlow",
    ):
        assert name in js, f"demo-v4.js missing {name}"


def test_demo_v4_js_cue_beat_labels() -> None:
    js = _demo_v4_js()
    for label in (
        "HUNTING",
        "HUNTED",
        "LAP COMPLETE",
        "PERSONAL BEST",
        "POSITION +1",
        "INCIDENT",
        "HEART RATE",
        "FINAL LAP",
        "FINISH",
    ):
        assert f'cue("{label}")' in js, f"missing cue {label!r}"


def test_overlay_js_starts_v4_cyclic_demo_without_fixture() -> None:
    js = _overlay_js()
    assert 'import("./demo-v4.js")' in js
    assert "startV4DemoLoop" in js
    assert 'params.get("fixture") || "lap_complete"' not in js


def test_demo_stage_defaults_to_v4_renderer() -> None:
    html = _demo_html()
    assert "renderer=v4" in html
    assert 'option value="v4" selected' in html
    assert "v3 (legacy)" in html
