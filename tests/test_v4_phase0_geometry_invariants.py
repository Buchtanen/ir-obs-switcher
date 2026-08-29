"""Phase 0: CSS geometry invariants that survive a CSS-vars refactor."""

from __future__ import annotations

from golden_v4_shared import display_v4_css
from v4_css_geometry import assert_rule_px, css_rule_block, resolve_px, rule_decls


def test_v4_widget_canvas_is_420x140() -> None:
    css = display_v4_css()
    assert_rule_px(css, ".v4-widget", {"width": 420.0, "height": 140.0})


def test_v4_icon_full_canvas_not_64_crop() -> None:
    css = display_v4_css()
    assert_rule_px(
        css,
        ".v4-art .icon",
        {"width": 420.0, "height": 140.0},
        msg="icon well",
    )
    decls = rule_decls(css, ".v4-art .icon")
    sizes = decls["background-size"].split()
    assert resolve_px(sizes[0]) == 420.0
    assert resolve_px(sizes[1]) == 140.0
    # Guard against reintroducing the fixed 64×64 crop bug.
    assert "64px" not in css_rule_block(css, ".v4-art .icon")
    assert "28px" not in css_rule_block(css, ".v4-art .icon")


def test_v4_copy_title_slot_geometry() -> None:
    css = display_v4_css()
    assert_rule_px(
        css,
        ".v4-copy .title",
        {"left": 119.0, "top": 38.0, "right": 16.0},
    )
    title = rule_decls(css, ".v4-copy .title")
    assert title.get("position") == "absolute"


def test_v4_copy_not_centered_grid() -> None:
    css = display_v4_css()
    copy = css_rule_block(css, ".v4-copy")
    assert "grid-template-rows: auto auto 1fr auto" not in copy
    assert "align-content: center" not in copy
    assert "display: block" in copy


def test_v4_widget_clips_glow_overflow() -> None:
    css = display_v4_css()
    widget = rule_decls(css, ".v4-widget")
    assert widget.get("overflow") == "hidden"
    assert widget.get("contain") == "paint"
    assert widget.get("isolation") == "isolate"


def test_sizing_regression_detected_against_wrong_canvas() -> None:
    """Deliberate wrong sizes must fail the same invariants Phase 1 will keep."""
    bad = """
.v4-widget {
  width: 520px;
  height: 190px;
  overflow: hidden;
}
"""
    try:
        assert_rule_px(bad, ".v4-widget", {"width": 420.0, "height": 140.0})
    except AssertionError:
        return
    raise AssertionError("expected sizing mismatch to fail")


def test_css_vars_fallback_form_also_satisfies_invariants() -> None:
    """Phase 1 may rewrite literals to var(--x, Npx); invariants must still pass."""
    future = """
.v4-widget {
  width: var(--v4-canvas-w, 420px);
  height: var(--v4-canvas-h, 140px);
  overflow: hidden;
  isolation: isolate;
  contain: paint;
}
.v4-art .icon {
  inset: 0;
  width: var(--v4-canvas-w, 420px);
  height: var(--v4-canvas-h, 140px);
  background-size: var(--v4-canvas-w, 420px) var(--v4-canvas-h, 140px);
}
.v4-copy .title {
  position: absolute;
  left: var(--v4-title-x, 119px);
  right: var(--v4-safe-r, 16px);
  top: var(--v4-title-y, 38px);
}
"""
    assert_rule_px(future, ".v4-widget", {"width": 420.0, "height": 140.0})
    assert_rule_px(future, ".v4-art .icon", {"width": 420.0, "height": 140.0})
    assert_rule_px(future, ".v4-copy .title", {"left": 119.0, "top": 38.0, "right": 16.0})
