# Overlay theme packs (future)

These directories hold **implementation-ready graphic packs** for upcoming
overlay themes. They are intentionally isolated from production runtime
themes under `src/irswitch/web/themes-v4/`.

| Directory | Display name | Source branch | Status |
|-----------|--------------|---------------|--------|
| `pit_wall_dark/` | Pit Wall Dark | `art/pitwall-theme` | V4 art pack complete (35 states); not wired into app yet |
| `pit_wall_light/` | Pit Wall Light | `art/light-minimal-theme` | V4 art pack complete (35 states); not wired into app yet |

Each pack includes:

- SVG masters (`frames/`, `icons/`, `accents/`, `textures/`)
- `manifest.json` + `theme-tokens.json`
- `references/docs/` (IMPLEMENTATION, motion, naming, OBS)
- HTML/CSS composition examples
- `packages/*.zip` export archives + `archive-index.json`

Shared implementation contract for upcoming renderer work (from PR #115):

- `docs/overlay_v4_layout_sizing_motion_spec.md` — layout / sizing / motion contract
- `docs/overlay_v4_layout_sizing_motion_spec_review.md` — CDP review notes
- `docs/V4_RENDERER_SIZING_SPEC_REVIEW.md` — renderer sizing review (root cause)

Start with each pack's `README.md` and `references/docs/IMPLEMENTATION.md`, plus
the shared layout/sizing/motion spec above.

The authoritative renderer inputs in each pack are:

- `accents/event-visual-map.json` - 35 V4 state definitions, 35 event routes,
  template layer registries, tone/rail selection and explicit battle-zone aliases;
- `theme-tokens.json` - native geometry, icon box and SYSINFO runtime grid;
- `motion/manifest.json` - motion intent and CSS/WebM delivery status.

Do **not** place theme files directly under `assets/overlay/` — always use a
namespaced directory under `assets/overlay/themes/<theme_id>/`.
