# Overlay theme assets

Shipped pack: [ASSETS.md](ASSETS.md) (PNG pixels / WebM) and [manifest.json](manifest.json).

Prompt for a new export: [GRAPHICS_BRIEF.md](GRAPHICS_BRIEF.md).

Themes (`cyber_racing`, `stealth_graphite`, `night_attack`) share **filenames and geometry**. Only color/glow changes.

```
themes/<theme>/assets/<slot>.png
themes/<theme>/assets/battle_radar_loop.webm
themes/<theme>/assets/battle_scan_enter.webm
themes/<theme>/assets/finish_accent_sweep.webm
```

37 PNG + 3 WebM per theme, snake_case, no baked text. Overlay reads slots from the WS/HTTP snapshot (`assets`). Missing file = CSS plate. State icons/dividers/corners use CSS `mask-image` and `currentColor`, not `<img>`. Background/frame PNGs are normal images. `final_lap_flag.png` is painted white (last lap); `finish_flag.png` is the checkered mask (race end). Glow is authored at 420×140 (`inset: 0`) and reused on the other widget plates.
