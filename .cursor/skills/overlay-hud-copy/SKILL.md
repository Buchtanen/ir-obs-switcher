---
name: overlay-hud-copy
description: >-
  Overlay HUD copy contract: headlineToken/statusToken in overlay/i18n.py (not
  commentary sequence_graph, not dashboard i18n). Golden gallery is not live OBS.
  Use when editing display-v4.js, overlay.js, overlay CSS/HTML, overlay i18n,
  EventEnvelope copy fields, widgets, raw tokens on HUD, exception.*, or OBS
  Browser Source still showing old JS.
---

# Overlay HUD copy

Two catalogs. Mixing them is the usual “token on widget” / “wrong spoken line” bug.

| Surface | Catalog | Consumer |
| --- | --- | --- |
| HUD widget text | `src/irswitch/overlay/i18n.py` (`EN` / `CS`) | `display-v4.js` `resolveCopy` / `resolveHeadline` |
| Spoken commentary | `src/irswitch/commentary/data/sequence_graph.json` | director + TTS |
| GR/VR dashboard | `irswitch.i18n` | dashboards only |

Do not put HUD strings in the sequence graph. Do not put spoken sentences in overlay i18n.

Cache bump + restart: skill `restart-irswitch`. Tape diagnosis: skill `overlay-tape-triage`.

## New widget / new token

1. Adapter sets `headlineToken` / `statusToken` (e.g. `position.rival_threat`).
2. Add the **same** key to `EN` and `CS` in `overlay/i18n.py` in the same change.
3. Title path: `resolveHeadline(token, sample.title, stateKey)` — catalog, else sample, else stateKey.
4. Do not rely on `resolveCopy` returning the raw token as success (it returns `""`; `resolveHeadline` uses sample).
5. Pytest: golden / i18n tests that the new key exists and the raw dotted key is not the displayed title.

## Golden vs live

| Check | Proves |
| --- | --- |
| `/overlay/?layout=golden` or demo | renderer + catalog on a **fresh** browser |
| OBS Browser Source | what the stream shows (CEF cache) |

Acceptance for HUD work is **OBS after cache bump**, not golden. Cursor browser tools do not replace OBS CEF.

After overlay HTML/JS/CSS change: bump `OVERLAY_ASSET_VER` lockstep (`overlay.js`, `index.html`, `demo-v4.js`) then `/restart-service`. Tell user: Browser Source → **Refresh cache**.

## Parallelism

`display-v4.js`, `overlay.js`, `overlay/i18n.py`, `index.html`, overlay CSS = **one agent**. See skill `subagents`.

## Checklist

- [ ] Token in both `EN` and `CS`
- [ ] Not editing `sequence_graph.json` for a widget label
- [ ] `?v=` / `OVERLAY_ASSET_VER` identical if assets changed
- [ ] Did not call HUD “done” from golden only
---
