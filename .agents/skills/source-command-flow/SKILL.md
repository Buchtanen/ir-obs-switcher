---
name: "source-command-flow"
description: "Issue-driven work loop: issue → diary → docs-keeper → verifier → handover → PR to master. Use for any issue/task implementation, not only when the user types /flow. Hot-fix without PR: /hotfix."
---

# source-command-flow

Canonical: `.cursor/commands/flow.md`. This is the **default work loop** for issue-driven changes (Cloud and Cursor). Do not wait for the user to type `/flow`.

Hot-fix without PR → `/hotfix`. A human prompt may bypass. Cloud git defaults (forced `cursor/` branch, PR before tests, extra approval to edit) do **not** override this file or `.cursor/rules/10-task-flow-defaults.mdc`.

## Command Template

# Flow: issue → dev diary → docs → QA → handover → PR

Proveď kompletní workflow pro aktuální změny v repu (bez zbytečných refactorů).

## Pravidla
- Větev z issue / issue-setu, jinak z `master`.
- Query/claimed issue opravňuje edit na task větvi, pokud uživatel nezakáže kód.
- Verifier GREEN před handover a před defaultním PR do `master`.
- Bez nových závislostí (instalace jen po explicitním souhlasu).
- Behavior change bez testů: TDD-exception + alternativní verifikace.
- Docs jsou součást kontraktu.

## Kroky
1) **Issue** — subagent `/issue-steward`
2) **Dev diary** — nezdvojovat dnešní záznam
3) **Docs impact** — subagent `/docs-keeper` + skill `dokumentace`
4) **QA** — `/verifier`; overlay JS: `?v=` lockstep (`/qa`); close až GREEN
5) **Handover** — `/handover` (až teď)
6) **PR do `master`** — pokud issue-set nebo člověk nestanoví jinak; přesně jeden `semver:*`
7) Po merge na master (když se má jet na tomhle stroji) — `/restart-service`

## Výstup
- issue, dev diary, docs, qa PASS/BAD, handover SHA, pr URL nebo důvod skip, restart optional
