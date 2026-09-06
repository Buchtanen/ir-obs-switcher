"""Relative links in docs/dokumentace/ must resolve (agent lookup contract)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "dokumentace"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

REQUIRED = (
    DOC / "README.md",
    DOC / "jak-cist.md",
    DOC / "architektura.md",
    DOC / "mapa-souboru.md",
    DOC / "stav.md",
    DOC / "inflight" / "README.md",
    DOC / "inflight" / "commentary-architecture.md",
)


def _targets(md: Path) -> list[Path]:
    out: list[Path] = []
    for raw in LINK_RE.findall(md.read_text(encoding="utf-8")):
        href = raw.split("#", 1)[0].strip()
        if not href or href.startswith(("http://", "https://", "mailto:")):
            continue
        out.append((md.parent / href).resolve())
    return out


def test_required_dokumentace_pages_exist() -> None:
    missing = [p.relative_to(ROOT).as_posix() for p in REQUIRED if not p.is_file()]
    assert not missing, missing


def test_dokumentace_relative_links_resolve() -> None:
    broken: list[str] = []
    for md in sorted(DOC.rglob("*.md")):
        for target in _targets(md):
            if not target.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert not broken, "broken dokumentace links:\n" + "\n".join(broken)


def test_domain_pages_cover_src_packages() -> None:
    src = ROOT / "src" / "irswitch"
    pkgs = {p.name for p in src.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))}
    # packages that must have a domain page
    expected = pkgs - {"web"} | {"web"}
    domeny = {p.stem for p in (DOC / "domeny").glob("*.md")}
    # extra pages: oauth-youtube, runtime, config, i18n, testy-ci map to files not dirs
    missing = expected - domeny
    assert not missing, f"src packages without domeny page: {sorted(missing)}"
