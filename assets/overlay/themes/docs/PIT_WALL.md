# Pit Wall V4 theme packs

Runtime theme ids: `pit_wall_dark`, `pit_wall_light`.
Art source: `assets/overlay/themes/pit_wall_{dark,light}/`.
Ingest: `scripts/ingest_pit_wall_themes_v4.py` → `src/irswitch/web/themes-v4/pit_wall_{dark,light}/`.

Packy **jsou** v produkčním V4 rendereru (ne „isolated from runtime“).

## Sdílený kontrakt

- Overlay canvas **1920×1080**, bez OBS zoom. Detaily: [overlay_v4_layout_sizing_motion_spec.md](overlay_v4_layout_sizing_motion_spec.md).
- Žádný plný bitmap background — průhledné vrstvy nad OBS scénou. Text renderuje HTML.
- Autorita vizuálních stavů: `accents/event-visual-map.json` (ne markdown tabulka).
- Tokeny: `theme-tokens.json`. Motion intent: `motion/manifest.json`. CSS je fallback když chybí WebM.
- OBS Browser Source: 1920×1080, transparent, margin 0.

## Dark vs Light (delta)

| | Dark | Light |
| --- | --- | --- |
| Prefix assetů | `pw-` | `pl-` |
| ENTER motion | ~360 ms wipe + rail | ~340 ms 24px slide + blur |
| Icon box | Dark `theme-tokens.json` | Light `theme-tokens.json` |
| Runtime id | `pit_wall_dark` | `pit_wall_light` |

## Struktura packu

`frames/`, `icons/`, `accents/`, `motion/`, `textures/`, `manifest.json`, `theme-tokens.json`.
`references/` může držet HTML examples — ne druhou kopii tohoto dokumentu.

## Golden

[GOLDEN_V4.md](../../../../src/irswitch/web/overlay/GOLDEN_V4.md) — theme query `pit_wall_dark` / `pit_wall_light`.
