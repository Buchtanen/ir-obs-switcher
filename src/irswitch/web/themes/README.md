# Overlay theme assets

Shipped pack: [ASSETS.md](ASSETS.md) (rozměry / viewBox) a [manifest.json](manifest.json).

Prompt pro nový export: [GRAPHICS_BRIEF.md](GRAPHICS_BRIEF.md).

Themes (`cyber_racing`, `stealth_graphite`, `night_attack`) mají **stejné filenames i geometrii**. Liší se barvy.

```
themes/<theme>/assets/<slot>.svg
themes/<theme>/assets/battle_glow.png
```

37 souborů na theme, snake_case, žádný zapečený text. Overlay čte sloty z WS/HTTP snapshotu (`assets`). Chybějící soubor = CSS deska. Stavové ikony používají `currentColor` a na HUD jdou přes CSS mask, ne `<img>`.
