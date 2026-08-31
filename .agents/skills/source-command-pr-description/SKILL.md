---
name: "source-command-pr-description"
description: "Migrated source command `pr-description`"
---

# source-command-pr-description

Use this skill when the user asks to run the migrated source command `pr-description`.

## Command Template

# PR description (AC + test plan + docs impact)

Vygeneruj PR popis podle našeho PR policy (AC + test plan + docs impact + config impact).

## Požadavky
- Stručné, review-ready.
- Připomenout semver label (přesně jeden).
- Pokud behavior change bez testů: explicitní TDD-exception.

## Template
Použij a vyplň podle aktuálních změn:

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
- [ ] docs/dokumentace/ (domeny/*.md and/or inflight/; or “no change” + reason)
- [ ] Other: ...

## Config impact (if any)
Changed keys:
- `<section>.<key>`: <what changed>
Migration:
- <how existing users update>

## Release policy
- [ ] PR has exactly one `semver:*` label
```
