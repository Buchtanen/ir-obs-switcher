# Overlay theme assets

Shipped pack: [ASSETS.md](ASSETS.md), [manifest.json](manifest.json), [composition_manifest.json](composition_manifest.json).

Battle V3 production rules: [V3_INTEGRATION.md](V3_INTEGRATION.md) and [V3_DESIGN_AND_MOTION_SPEC.md](V3_DESIGN_AND_MOTION_SPEC.md). Older V2 widget families (lap/session/bio/sysinfo) still use the raster plates listed in ASSETS.md until Phase B.

```
themes/<theme>/assets/<slot>.png
themes/<theme>/assets/battle_scan_enter.webm
themes/<theme>/assets/battle_signal_lock.webm
themes/<theme>/assets/battle_theme_motion.webm
themes/<theme>/assets/finish_accent_sweep.webm
```

50 PNG + 4 WebM per theme, snake_case, no baked text. Overlay reads slots from the WS/HTTP snapshot (`assets`). Missing file = CSS plate.

Battle layers are all **420×140** (including icons and radar). Tint mask layers with `mask-image` / `currentColor`. Pre-colored glow PNGs (`battle_glow_cyan|amber|red`) are images, mix-blend screen. Do not load `previews/` or MP4 review clips in the overlay.
