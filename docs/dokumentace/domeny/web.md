# Web UI (`src/irswitch/web/`)

Statika servírovaná aiohttp. Chování dat je v server/overlay/commentary; tady HTML/CSS/JS.

## Povrchy

| Cesta | Účel |
| --- | --- |
| `web/admin/` | Operator admin (status, extensions, features, activity) |
| GR/VR | HTML skládá `server/dashboards.py` (+ `assets/`) |
| `web/overlay/` | Browser Source HUD 1920×1080 |
| `web/commentary/` | Ruční TTS test |
| `web/config/` | Overlay config UI (`/config`) |
| `web/debug/`, `web/demo/` | Debug emit, V4 demo stage |
| `web/themes/` | V3 theme CSS + ASSETS.md |
| `web/themes-v4/` | `manifest.json`, `event_catalog.json` |

## Overlay JS

- `overlay.js` — WS client, snapshot
- `display.js` — V3 karty
- `display-v4.js` — V4 envelopes + manifest
- `timing-format.js` — `m:ss.fff`
- `demo.js` / `demo-v4.js` — cyclic dry test

Tři V3 themes (`cyber_racing`, `stealth_graphite`, `night_attack`) — stejná geometrie. PNG/WebM v `assets/overlay/themes/`. Chybějící asset = CSS fallback.

Admin spec: `docs/admin_dashboard_spec.md`. Theme grafika: `web/themes/ASSETS.md`.

Změna UI: ověř v prohlížeči (user rule) — `/admin`, `/overlay`, `/gr-status` podle dopadu.

## In-flight

#181 N9 overlay cover je **vyříznuté** z narrative epic. HUD cover nedělej v rámci observers PR.
