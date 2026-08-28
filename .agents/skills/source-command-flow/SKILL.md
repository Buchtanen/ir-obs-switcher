---
name: "source-command-flow"
description: "Migrated source command `flow`"
---

# source-command-flow

Use this skill when the user asks to run the migrated source command `flow`.

## Command Template

# Flow: issue → dev diary → docs → QA → PR

Proveď kompletní workflow pro aktuální změny v repu (bez zbytečných refactorů).

## Pravidla
- Bez nových závislostí (instalace jen po explicitním souhlasu).
- Pokud je behavior change bez testů: explicitní TDD-exception + alternativní verifikace.
- Docs jsou součást kontraktu: pokud se mění chování/config/CI, docs musí být aktualizované.

## Kroky
1) **Issue**
   - Použij subagenta `/issue-steward`:
     - zjisti branch
     - najdi existující issue, nebo vytvoř nové (template: Context/AC/Test plan/Docs impact/Config impact)
     - vrať issue number + odkaz

2) **Dev diary**
   - Přidej dev diary komentář do toho issue (dnešní datum), ale **nezdvojovat**:
     - nejdřív načti posledních 5–10 issue komentářů (`issue_read` → `get_comments`)
     - pokud už existuje dnešní dev diary od tebe, **přeskoč přidání** a jen vrať odkaz
     - jinak přidej nový (What changed / Why / Evidence / Docs / Next / Risks)

3) **Docs impact**
   - Použij subagenta `/docs-keeper`:
     - z diffu odvoď, které docs jsou relevantní (dle `docs-map.mdc`)
     - udělej minimální update (nebo explicitně „Docs: no change (reason …)”)

4) **QA**
   - Použij subagenta `/verifier`:
     - spusť relevantní checky (ruff/black/mypy/pytest nebo repo skripty)
     - dej PASS/BAD report + konkrétní next kroky

5) **PR popis**
   - Vygeneruj PR popis podle našeho template (AC/test plan/docs impact/config impact) a připomeň:
     - přesně jeden `semver:*` label

6) **Po merge na master** (jen když se má služba hned jet z tohoto stroje)
   - `/restart-service` a zkontroluj verzi v `/health`

## Výstup
Na konci vrať:
- issue: číslo + odkaz
- dev diary: stručné shrnutí, co bylo zapsáno
- docs: seznam změněných doc souborů (nebo důvod „no change“)
- qa: PASS/BAD
- pr: hotový text PR popisu
- restart (optional): health + version, pokud se spouštělo `/restart-service`
