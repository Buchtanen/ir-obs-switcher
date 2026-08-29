# Overlay theme packs (future)

These directories hold **implementation-ready graphic packs** for upcoming
overlay themes. They are intentionally isolated from production runtime
themes under `src/irswitch/web/themes-v4/`.

| Directory | Display name | Source branch | Status |
|-----------|--------------|---------------|--------|
| `pit_wall_dark/` | Pit Wall Dark | `art/pitwall-theme` | Pack only — not wired into app yet |
| `pit_wall_light/` | Pit Wall Light | `art/light-minimal-theme` | Pack only — not wired into app yet |

Each pack includes:

- SVG masters (`frames/`, `icons/`, `accents/`, `textures/`)
- `manifest.json` + `theme-tokens.json`
- `references/docs/` (IMPLEMENTATION, motion, naming, OBS)
- HTML/CSS composition examples
- `packages/*.zip` export archives + `archive-index.json`

Start with each pack's `README.md` and `references/docs/IMPLEMENTATION.md`.

Do **not** place theme files directly under `assets/overlay/` — always use a
namespaced directory under `assets/overlay/themes/<theme_id>/`.
