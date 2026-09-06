---
name: dokumentace
description: Lookup-first project docs. Read and update docs/dokumentace on every src/irswitch, config, API, overlay, or CI change. Agents must find modules here instead of grepping src/.
---

# Dokumentace index (`docs/dokumentace/`)

Agents **do not start in `src/`**. First open `docs/dokumentace/README.md`, then the matching domain page. Grep is a last resort when the index is missing a file — then **add the file to the index** in the same change.

## Dvě povinnosti (není opt-in)

1. **Lookup (před kódem):** `docs/dokumentace/README.md` → `domeny/<balík>.md` → kontrakt (`CONFIG.md` / `API.md`) → teprve kód.
2. **Údržba (po změně):** každá úprava chování, hranic, souborů, config zapojení nebo otevřeného PR musí aktualizovat matching page, nebo explicitně `Docs: no change (reason …)`.

Tichý skip je **defect**. Stejná laťka jako `CONFIG.md` u INI klíče.

## Kdo to drží aktuální

| Role | Povinnost |
| --- | --- |
| Tento skill | Lookup + handover checklist |
| Subagent `docs-keeper` | Po každém `/flow` a `/docs-impact` **udělá** update `docs/dokumentace/` + kontrakty z `docs-map.mdc` |
| Rule `09-dokumentace-index.mdc` | Always-on: čti index, po změně ho oprav |
| `/flow` krok 3 | Neskončí bez docs-keeper výstupu |
| Verifier | `src/irswitch/` diff bez domain page nebo `Docs: no change` = BAD |

Hooks na Windows jsou vypnuté. **Nespoléhej na hook.**

## Po každém tasku

- [ ] Diff `src/irswitch/<balík>/` → `docs/dokumentace/domeny/<balík>.md` (purpose, boundaries, key files, tests)
- [ ] Nový soubor / tok dat → `mapa-souboru.md` + `architektura.md` + řádek v indexu
- [ ] Jen na otevřeném PR → `docs/dokumentace/inflight/`, **ne** jako shipped v `domeny/`
- [ ] INI/HTTP pořád v `CONFIG.md` / `API.md` (index jen odkazuje)
- [ ] Overlay V4 layout → `assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec.md` + `domeny/overlay.md`
- [ ] Pit Wall art → `assets/overlay/themes/docs/PIT_WALL.md`
- [ ] Cursor rules/skills/commands → `.cursor/README.md`
- [ ] PR checklist má `docs/dokumentace/` nebo reason

Typo v testu, čistý format, CI bump bez runtime: `Docs: no change (reason …)` — **napiš to**.

## Lookup (příznak → page)

| Chci | Čti |
| --- | --- |
| OBS scény, debounce, GARAGE vs LOBBY | `domeny/logic.md`, `domeny/iracing.md` |
| iRSDK, sentinely, extract | `domeny/iracing.md` |
| HUD / V4 / tape / WS overlay | `domeny/overlay.md` |
| Eventy, arbitration, fan-out | `domeny/events.md` |
| TTS, graph, director | `domeny/commentary.md` |
| RaceState, observer, gapy | `domeny/race.md` |
| HTTP/WS, `/health`, admin | `domeny/server.md`, `API.md` |
| INI klíče | `domeny/config.md`, `CONFIG.md` |
| Co je otevřené (ne master) | `inflight/README.md` |

Mapa cesta → soubor: `.cursor/rules/docs-map.mdc`.
