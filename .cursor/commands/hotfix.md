# Hotfix: reprodukce → minimální diff → test → restart

Rychlá debug smyčka **bez** issue/PR. Až budeš chtít PR, `/flow`.

## Pravidla
- Kód jen po schválení (tady: uživatel už debug/hotfix chtěl).
- Žádný commit/push/PR, dokud to výslovně neřekne.
- Behavior change: test, nebo TDD-exception v reportu.
- Overlay HUD: skill `overlay-hud-copy`. Session/stream názvy: `iracing-session-glossary`.
- Diagnostika session/VOD: skill `overlay-tape-triage` (tape dřív než `irswitch.log`).

## Postup
1) Reprodukce: tape header / minimální pytest / konkrétní log čára. Ne celý BLE dump.
2) Minimální diff (žádný sousední refactor).
3) Relevantní pytest (ne nutně celá suite). Overlay JS v diffu → `/qa` lockstep `?v=`.
4) `/restart-service` (skill `restart-irswitch`: cache bump když se měnil `web/overlay`).
5) Řekni co ověřit v OBS (Refresh cache, Practice vs Quali vs Race).

## Výstup
- **repro**: …
- **diff**: soubory
- **tests**: pass/bad
- **overlay_v**: bumped / skipped
- **obs_check**: 3–5 bodů
- **tdd-exception**: jen když test nešel
---
