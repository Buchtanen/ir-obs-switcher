---
name: "source-command-dev-diary"
description: "Migrated source command `dev-diary`"
---

# source-command-dev-diary

Use this skill when the user asks to run the migrated source command `dev-diary`.

## Command Template

# Dev diary (issue comment)

Přidej dev diary komentář do issue pro aktuální práci.

## Postup
1) Pokud nemáš číslo issue, nejdřív spusť `/ensure-issue` a vezmi issue_number.
2) Deduplikace (aby nevznikaly 2 stejné diary záznamy):
   - načti posledních 5–10 komentářů přes GitHub MCP (`issue_read` s `method: get_comments`)
   - pokud už existuje dnešní komentář od tebe s hlavičkou `## Dev diary – YYYY-MM-DD`, **nový nepřidávej** a jen vrať link na existující
3) Pokud deduplikace nenašla dnešní záznam, přidej komentář přes GitHub MCP (`add_issue_comment`).

## Šablona
Použij dnešní datum a vyplň konkrétně (žádné vágní „updated stuff“).

```markdown
## Dev diary – YYYY-MM-DD
What changed:
- ...

Why:
- ...

Evidence:
- Tests: ...
- Manual: ...

Docs:
- Updated: ...
- Pending: ...

Next:
- ...

Risks:
- ...
```
