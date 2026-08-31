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


def test_handover_wiring_exists() -> None:
    assert (ROOT / ".cursor" / "skills" / "dokumentace" / "SKILL.md").is_file()
    hook = ROOT / ".cursor" / "hooks" / "dokumentace_handover.py"
    assert hook.is_file()
    example = (ROOT / ".cursor" / "hooks.example.json").read_text(encoding="utf-8")
    assert "dokumentace_handover.py" in example
    keeper = (ROOT / ".cursor" / "agents" / "docs-keeper.md").read_text(encoding="utf-8")
    assert "docs/dokumentace" in keeper
    work_item = (ROOT / ".cursor" / "rules" / "02-work-item-definition.mdc").read_text(
        encoding="utf-8"
    )
    assert "docs/dokumentace/" in work_item


def test_handover_hook_domain_pages_exist() -> None:
    import importlib.util

    path = ROOT / ".cursor" / "hooks" / "dokumentace_handover.py"
    spec = importlib.util.spec_from_file_location("dokumentace_handover", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    missing = []
    for _prefix, doc in mod.DOMAIN_BY_PREFIX:
        if not (ROOT / doc).is_file():
            missing.append(doc)
    for _src, doc in mod.FILE_TO_DOC.items():
        if not (ROOT / doc).is_file():
            missing.append(doc)
    assert missing == []
