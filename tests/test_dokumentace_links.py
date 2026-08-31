"""Relative links in docs/dokumentace must resolve (agent index contract)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "dokumentace"
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _markdown_files() -> list[Path]:
    return sorted(DOC_ROOT.rglob("*.md"))


def test_dokumentace_index_exists() -> None:
    assert (DOC_ROOT / "README.md").is_file()
    assert (DOC_ROOT / "inflight" / "README.md").is_file()


def test_dokumentace_relative_links_resolve() -> None:
    missing: list[str] = []
    checked = 0
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in MD_LINK.finditer(text):
            raw = match.group(1).strip()
            if raw.startswith(("http://", "https://", "mailto:")):
                continue
            if raw.startswith("#"):
                continue
            href = raw.split("#", 1)[0]
            if not href:
                continue
            checked += 1
            target = (path.parent / href).resolve()
            if not target.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {raw}")
    assert checked >= 50, f"expected a dense index, only {checked} relative links"
    assert missing == [], "broken relative links:\n" + "\n".join(missing)


def test_readme_points_at_dokumentace() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/dokumentace/README.md" in readme
