---
name: "source-command-flow"
description: "Migrated source command `flow`"
---

# source-command-flow

Use this skill when the user asks to run the migrated source command `flow`. Canonical: `.cursor/commands/flow.md`. Hot-fix without PR: `/hotfix`.

## Command Template

# Flow: issue → dev diary → docs → QA → PR

Proveď kompletní workflow pro aktuální změny v repu (bez zbytečných refactorů).

Hot-fix bez PR → `/hotfix` (repro, test, restart). Tento command je na issue → QA → PR popis.

## Pravidla
- Bez nových závislostí (instalace jen po explicitním souhlasu).
- Pokud je behavior change bez testů: explicitní TDD-exception + alternativní verifikace.
- Docs jsou součást kontraktu: pokud se mění chování/config/CI, docs musí být aktualizované.

## Kroky
1) **Issue**
   - Použij subagenta `/issue-steward`
2) **Dev diary** — nezdvojovat dnešní záznam
3) **Docs impact** — subagent `/docs-keeper`
4) **QA** — `/verifier`; overlay JS: `?v=` lockstep (`/qa`)
5) **PR popis** — přesně jeden `semver:*` label
6) Po merge na master (když se má jet na tomhle stroji) — `/restart-service`

## Výstup
- issue, dev diary, docs, qa PASS/BAD, pr text, restart optional
---
