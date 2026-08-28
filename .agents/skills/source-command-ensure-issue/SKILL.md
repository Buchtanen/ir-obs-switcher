---
name: "source-command-ensure-issue"
description: "Migrated source command `ensure-issue`"
---

# source-command-ensure-issue

Use this skill when the user asks to run the migrated source command `ensure-issue`.

## Command Template

# Ensure Issue (issue-driven dev)

Zajisti, že aktuální práce má GitHub issue, aby bylo kam psát dev diary.

## Pravidla
- Pokud issue neexistuje, vytvoř ho.
- Použij GitHub MCP (ne ruční web).
- Issue musí mít: Context, AC, Test plan, Docs impact, Config impact.

## Postup
1) Zjisti aktuální branch (git).
2) Pokus se najít existující issue:
   - pokud branch obsahuje `#123` / `issue-123` / `123-...`, hledej to číslo
   - jinak hledej branch name jako string v issue title/body
3) Pokud nic nenajdeš, vytvoř nové issue:
   - title: stručně + suffix `([branch: <branch>])`
   - body: šablona níže
   - (volitelně) assignee: aktuální user (MCP `get_me`)
4) Vypiš výsledek: číslo issue + odkaz.

## Issue body template
```markdown
## Context
<why, what problem>

## Acceptance criteria
- [ ] AC1 ...
- [ ] AC2 ...

## Test plan
- [ ] Unit: ...
- [ ] Integration/E2E: ...
- [ ] Manual verification: ...

## Docs impact
- [ ] README.md
- [ ] CONFIG.md + config/config.example.ini
- [ ] API.md
- [ ] BUILD_AND_DEPLOY.md
- [ ] VR_SUPPORT.md / RACELAB_VR_SETUP.md
- [ ] .cursor/README.md (if rules/skills/commands change)
- [ ] Other: ...

## Config impact (if any)
Changed keys:
- `<section>.<key>`: <what changed>
Migration:
- <how existing users update>
```
