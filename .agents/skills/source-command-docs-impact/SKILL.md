---
name: "source-command-docs-impact"
description: "Migrated source command `docs-impact`"
---

# source-command-docs-impact

Use this skill when the user asks to run the migrated source command `docs-impact`.

## Command Template

# Docs impact (update required docs)

Vyhodnoť dopad změn na dokumentaci a udělej minimální update relevantních `.md` souborů.

## Postup
1) Z diffu určete typ změn:
   - runtime chování / config / API / build / release / CI / docs-only
2) Podle `docs-map.mdc` vypiš, které docs jsou relevantní.
   **Vždy** zvaž `docs/dokumentace/domeny/*.md` (mapa `src/irswitch/` → stránka). In-flight PR → `docs/dokumentace/inflight/`.
   Skill: `.cursor/skills/dokumentace/SKILL.md`.
3) Udělej update:
   - krátce, přesně, copy-paste-friendly snippety
   - když se docs nemění: explicitně napiš „Docs: no change (reason …)“

## Výstup
- **Updated docs**: seznam souborů
- **Pending docs**: seznam souborů + co doplnit
- **Notes**: proč
