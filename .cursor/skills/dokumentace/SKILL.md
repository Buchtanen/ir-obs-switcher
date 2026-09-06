---
name: dokumentace
description: Maintain docs/dokumentace after every src/irswitch change, /flow, /docs-impact, PR, or task handover. Domain pages, inflight PRs, lookup-before-grep.
---

# Dokumentace index (`docs/dokumentace/`)

## Dvě povinnosti

1. **Lookup (před kódem):** čti `docs/dokumentace/README.md` → `domeny/<x>.md` dřív, než grepneš `src/`.
2. **Údržba (po změně):** každá úprava `src/irswitch/` (chování, hranice, soubory, config zapojení) musí aktualizovat odpovídající stránku, nebo explicitně `Docs: no change (reason …)` v PR / diary.

Mapa cesta → soubor: `.cursor/rules/docs-map.mdc` (sekce dokumentace).

## Po každém tasku (handover)

Než prohlásíš hotovo:

- [ ] Diff `src/irswitch/<balík>/` → otevři `docs/dokumentace/domeny/<balík>.md`
- [ ] Nový modul / změna toku → `architektura.md` + `mapa-souboru.md` (+ řádek v indexu)
- [ ] Věc jen na otevřeném PR, ne na `master` → `docs/dokumentace/inflight/`, **ne** jako shipped v `domeny/`
- [ ] Kontrakt INI/HTTP pořád v `CONFIG.md` / `API.md` (index jen odkazuje)
- [ ] PR checklist má zaškrtnuté `docs/dokumentace/` nebo reason

Typo v testu, čistě formát, CI bump bez runtime: `Docs: no change (reason …)` stačí — i tak to **napiš**, ať to nevypadá jako zapomenuté.

## Kdo to spouští

- Rule `09-dokumentace-index.mdc` (always)
- `/docs-impact` a subagent `docs-keeper` (krok ve `/flow`)
- `/pr-description` checklist
- Cursor **stop hook** `dokumentace_handover.py` (jen když jsou hooks opt-in)

Nespoléhej na hook: na Windows jsou Cursor hooks defaultně vypnuté. Rule + docs-keeper jsou zdroj pravdy.
