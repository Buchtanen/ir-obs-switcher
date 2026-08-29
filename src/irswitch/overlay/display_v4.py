"""V4 manifest-driven asset resolver. Separate from V3 ``ASSET_SLOTS``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

V4_MANIFEST_REL = "themes-v4/manifest.json"


def manifest_rel_to_web(rel: str) -> str:
    """Map manifest ``themes/…`` paths to shipped ``themes-v4/…`` tree."""
    if rel.startswith("themes/"):
        return "themes-v4/" + rel[len("themes/") :]
    return rel.replace("\\", "/")


def v4_manifest_path(web_root: Path) -> Path:
    return web_root / V4_MANIFEST_REL


def load_v4_manifest(web_root: Path) -> dict[str, Any]:
    parsed = json.loads(v4_manifest_path(web_root).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("V4 manifest root must be a JSON object")
    return cast(dict[str, Any], parsed)


class V4AssetResolver:
    """Resolve ``(theme, family, state)`` → layer paths from V4 ``manifest.json``."""

    def __init__(
        self,
        theme: str,
        web_root: Path,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self.theme = theme
        self.web_root = web_root
        self._manifest = manifest if manifest is not None else load_v4_manifest(web_root)

    @classmethod
    def load(cls, theme: str, web_root: Path) -> V4AssetResolver:
        return cls(theme, web_root)

    def _resolve_file(self, rel: str) -> str | None:
        disk_rel = manifest_rel_to_web(rel)
        path = self.web_root / disk_rel
        return disk_rel if path.is_file() else None

    def family_for_state(self, state: str) -> str | None:
        meta = self._manifest.get("states", {}).get(state)
        if not meta:
            return None
        family = meta.get("family")
        return str(family) if family else None

    def resolve_motion(self, motion: str) -> str | None:
        motions = self._manifest.get("motions") or []
        if motion not in motions:
            return None
        rel = f"themes/{self.theme}/motion/{motion}.webm"
        return self._resolve_file(rel)

    def resolve(self, family: str, state: str) -> dict[str, Any]:
        """Resolve ``(theme, family, state)`` to layer paths and icon."""
        state_meta = self._manifest.get("states", {}).get(state) or {}
        if state_meta.get("family"):
            family = str(state_meta["family"])

        theme_cfg = self._manifest.get("themes", {}).get(self.theme) or {}
        family_cfg = (theme_cfg.get("families") or {}).get(family)
        if not family_cfg:
            return {
                "family": family,
                "state": state,
                "tone": str(state_meta.get("tone", "primary")),
                "layers": [],
                "icon": None,
                "functional": None,
            }

        layer_dir = str(family_cfg.get("layer_dir", ""))
        layers: list[dict[str, Any]] = []
        for layer in family_cfg.get("layers") or []:
            file_name = str(layer.get("file", ""))
            rel = f"{layer_dir}/{file_name}"
            layers.append(
                {
                    "file": file_name,
                    "mode": str(layer.get("mode", "image")),
                    "path": self._resolve_file(rel),
                }
            )

        icon_dir = str(family_cfg.get("icon_dir", ""))
        icon_rel = f"{icon_dir}/{state}.png"
        functional = family_cfg.get("functional_component")
        functional_path = self._resolve_file(f"{layer_dir}/{functional}") if functional else None

        return {
            "family": family,
            "state": state,
            "tone": str(state_meta.get("tone", "primary")),
            "layers": layers,
            "icon": self._resolve_file(icon_rel),
            "functional": functional_path,
        }

    def resolve_state(self, state: str) -> dict[str, Any] | None:
        family = self.family_for_state(state)
        if not family:
            return None
        return self.resolve(family, state)

    def to_dict(self) -> dict[str, Any]:
        """Resolved asset map for presentation payload / tests."""
        states: dict[str, Any] = {}
        for state in self._manifest.get("states") or {}:
            resolved = self.resolve_state(state)
            if resolved:
                states[state] = resolved

        motions: dict[str, str | None] = {}
        for motion in self._manifest.get("motions") or []:
            motions[str(motion)] = self.resolve_motion(str(motion))

        theme_block = (self._manifest.get("themes") or {}).get(self.theme) or {}
        return {
            "theme": self.theme,
            "manifest_schema": self._manifest.get("manifest_schema"),
            "transient_canvas": self._manifest.get("transient_canvas"),
            "sysinfo_canvas": self._manifest.get("sysinfo_canvas"),
            "canvases": self._manifest.get("canvases"),
            "theme_canvases": theme_block.get("canvases"),
            "zones": self._manifest.get("zones"),
            "transitions": self._manifest.get("transitions"),
            "states": states,
            "motions": motions,
        }
