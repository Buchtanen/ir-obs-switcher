"""CSS geometry helpers that accept bare px or ``var(--x, Npx)`` fallbacks.

Phase 0 / Phase 1 bridge: tests assert resolved pixel values, not source
substrings, so a later CSS-vars refactor does not break the suite.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

_DECL_RE = re.compile(
    r"(?P<prop>-?[a-zA-Z_][\w-]*)\s*:\s*(?P<value>[^;]+);",
    re.MULTILINE,
)
_VAR_FALLBACK_RE = re.compile(
    r"^var\(\s*--[\w-]+\s*,\s*(?P<fallback>.+)\)$",
    re.IGNORECASE | re.DOTALL,
)
_PX_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*px$", re.IGNORECASE)


def css_rule_block(css: str, selector: str) -> str:
    """Return the body of the first ``selector { ... }`` rule (no nested braces)."""
    needle = f"{selector} {{"
    start = css.find(needle)
    if start < 0:
        raise AssertionError(f"CSS rule not found: {selector!r}")
    body_start = start + len(needle)
    depth = 1
    i = body_start
    while i < len(css) and depth:
        ch = css[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth:
        raise AssertionError(f"Unbalanced braces for rule: {selector!r}")
    return css[body_start : i - 1]


def css_declarations(block: str) -> dict[str, str]:
    """Parse flat ``prop: value;`` declarations from a rule body."""
    out: dict[str, str] = {}
    for match in _DECL_RE.finditer(block):
        out[match.group("prop").strip()] = match.group("value").strip()
    return out


def resolve_css_value(value: str) -> str:
    """Unwrap one level of ``var(--name, fallback)``; otherwise return trimmed value."""
    text = value.strip()
    match = _VAR_FALLBACK_RE.match(text)
    if match:
        return match.group("fallback").strip()
    return text


def resolve_px(value: str) -> float:
    """Resolve a CSS length to pixels (bare ``Npx`` or ``var(--x, Npx)``)."""
    resolved = resolve_css_value(value)
    match = _PX_RE.match(resolved)
    if not match:
        raise AssertionError(f"Expected px length, got {value!r} (resolved {resolved!r})")
    return float(match.group(1))


def rule_decls(css: str, selector: str) -> dict[str, str]:
    return css_declarations(css_rule_block(css, selector))


def rule_px(css: str, selector: str, prop: str) -> float:
    decls = rule_decls(css, selector)
    if prop not in decls:
        raise AssertionError(f"Property {prop!r} missing on {selector!r}")
    return resolve_px(decls[prop])


def assert_rule_px(
    css: str,
    selector: str,
    expected: Mapping[str, float],
    *,
    msg: str = "",
) -> None:
    decls = rule_decls(css, selector)
    prefix = f"{msg}: " if msg else ""
    for prop, want in expected.items():
        assert prop in decls, f"{prefix}{selector} missing {prop}"
        got = resolve_px(decls[prop])
        assert got == want, f"{prefix}{selector} {prop}={got} (want {want})"
