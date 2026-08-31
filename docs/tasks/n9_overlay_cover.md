# N9 — Overlay stream cover + summary (optional)

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §5  
**Depends on:** N8 `StreamStartContext` (or a tiny shared snapshot module extracted first)  
**Branch hint:** `feat/overlay-stream-cover`  
**UI:** verify in browser when implemented (full-bleed + hide)

## Context

Product: overlay **may** show a large graphic cover and a short summary at stream start (track, session, one-liner). This is **not** an OBS scene change. Optional vs N8 TTS.

## Owns / must not touch

- **Owns:** overlay v4 state `stream_cover` (or equivalent), theme slot, CSS/layout, bus payload from snapshot, auto-hide, tests / demo fixture  
- **Must not:** `logic/` OBS state machine, commentary director, EventEngine  

## Acceptance criteria

- [ ] When `overlay.stream_cover=true` and stream-start snapshot exists: full-bleed cover + summary tokens (track, session, optional SoF)  
- [ ] Auto-hide after `stream_cover_s` **or** on `ENTER_CAR` / overlay_mode on-track — document winner (prefer ENTER_CAR else timeout)  
- [ ] Default off; no cover on existing installs  
- [ ] Does not steal battle/timing plates (z-order: cover above HUD until hidden)  
- [ ] i18n EN+CS for summary tokens  
- [ ] Theme can supply art; missing art → CSS fallback, no crash  

## Test plan

- [ ] Unit/protocol: envelope or bus flag shows then hides  
- [ ] Overlay i18n keys exist  
- [ ] Manual: browser overlay demo or `/overlay` — show cover, wait/hide, HUD returns  

## Docs impact

- [ ] Overlay theme docs / `OBS_BROWSER_SOURCE` if a second browser source is required (prefer **same** overlay URL)  
- [ ] `CONFIG.md` + example.ini  
- [ ] Matrix overlay column  

## Config impact

- `overlay.stream_cover` default `false`  
- `overlay.stream_cover_s` default e.g. `12`  
