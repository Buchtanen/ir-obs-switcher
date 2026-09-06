# Overlay (`src/irswitch/overlay/`)

HUD envelope, tape, overlay HTTP/WS. Peer consumer accepted eventů (N12 `overlay/consumer.py`). Nepřepíná scény. HUD copy žije v `overlay/i18n.py`, ne v commentary graphu.

## V4

Default v `config.example.ini`: `v4_assets` / `v4_renderer` zapnuté. Kontrakt canvas: [overlay_v4_layout_sizing_motion_spec.md](../../../assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec.md). Pit Wall: [PIT_WALL.md](../../../assets/overlay/themes/docs/PIT_WALL.md). Golden: [GOLDEN_V4.md](../../../src/irswitch/web/overlay/GOLDEN_V4.md).

V3 raster v `web/themes/` je fallback, ne aktuální layout pravda.

## Key files

`runtime.py`, `bus.py`, `http.py`, `consumer.py`, `tape.py`, `display_v4.py`, `i18n.py`. JS: `web/overlay/js/display-v4.js` (HUD cluster — jeden agent, sekvenčně).

## Tests

`tests/test_overlay_*.py`, `tests/test_golden_v4_fixtures.py`. Skill `overlay-hud-copy`, `overlay-tape-triage`.

## Related

[events](events.md), [web](web.md). SoF overlay karty **nejsou** — viz [EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md](../../EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md).
