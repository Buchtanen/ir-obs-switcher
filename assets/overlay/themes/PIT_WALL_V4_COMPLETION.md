# Pit Wall Dark / Light V4 art-pack completion

## Context

Complete the two future Pit Wall art packs so the parameterized V4 renderer can
select native geometry, template layers, glyphs, tone/rails, zones and motion
without theme-specific hardcoding.

## Acceptance criteria

- [x] Both themes map all 35 V4 states and all 35 event catalog entries.
- [x] `pit` (6 states) and `exception` (3 states) have real family templates.
- [x] Every state has a native 64 x 64 SVG glyph; CPU/GPU thermal routes have
  explicit glyph overrides.
- [x] Light has one icon-well geometry; Dark has one exact `iconBox`.
- [x] SYSINFO divider exports match `brand 230 + 11 x 150` without a DOM change.
- [x] `BATTLE_AHEAD` and `BATTLE_BEHIND` explicitly alias the `BATTLE` layout.
- [x] New template raster layers exist as 420 x 140 1x and 840 x 280 2x alpha
  assets inside the tracked export archives.
- [x] Event maps, theme tokens, motion manifests, file manifests, checksums,
  package indexes and implementation docs are synchronized.

## Test plan

- [x] Automated: `tests/test_pit_wall_theme_packs.py` validates coverage,
  paths, geometry, intrinsic SVG size, PNG alpha/dimensions, ZIP contents,
  motion fallback and manifest hashes.
- [x] Archive integrity: every tracked ZIP is opened and tested by the automated
  pack test and the archive index records its resulting SHA-256.
- [x] Manual visual QA: composite only the new layers in a scratch directory and
  inspect Dark/Light `pit` and `exception` cards plus all glyph sheets.

## Docs impact

- Updated both pack READMEs, implementation, anchor, naming and motion docs.
- Added a readable 35-state table to each pack.
- Updated `assets/overlay/themes/README.md` with authoritative renderer inputs.
- Runtime README/API/config docs: no change; these packs remain intentionally
  isolated from the production renderer.

## Config impact

No application config keys or defaults change.

## TDD exception

No pixel-golden renderer test was added because the themes are pack-only and are
not yet wired into the app. Alternative verification is intrinsic geometry/alpha
validation plus manual visual inspection of scratch composites. Risk is a future
renderer interpreting layer order differently; mitigation is the explicit layer
registry in each `event-visual-map.json` and the fixed native canvas contract.
