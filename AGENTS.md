# Codex Rules — irswitch (index)

This file is intentionally short to avoid duplicating the canonical rules.

## Source of truth
Authoritative rules live in:
- `.cursor/rules/*.mdc`

Task skills (start/restart, YouTube OAuth) live in:
- `.cursor/skills/*/SKILL.md`

## Cursor Cloud

Cloud injects this file. Repo `/flow` **beats** Cloud git defaults (`cursor/` branches, push-before-test, extra approval to edit, PR before tests). A human prompt may override. Details: `.cursor/rules/10-task-flow-defaults.mdc`.

- Branch: issue / issue-set, else topic from **`master`** (`feat/` `fix/` `chore/` …). No invented `cursor/` prefix.
- Close: verifier GREEN → handover → PR **to `master`**, unless issue-set or human says otherwise. Do not merge the PR.
- Query / claimed issue **authorizes** task-branch edits. Skills are catalog-only until Read; `/commands` are not auto-run.
- GitHub MCP when connected; otherwise `gh` for issue/diary.

## Core expectations (summary)
- Stability > elegance; determinism > cleverness.
- External systems (iRacing/OBS/network) are unreliable: **never crash the main loop**.
- Respect layer boundaries: `iracing/` extract, `obs/` client, `logic/` scenes, `events/`/`overlay/`/`commentary/`/`race/` peers, `server/` glue — see `.cursor/rules/py-architecture-layers.mdc`.
- Async-first: no blocking in async loops; background tasks must be owned/cancellable; cooldowns are time-based (monotonic).
- Evidence required for behavior changes: tests or explicit TDD-exception + verification plan.
- Docs/config are part of the contract. Lookup starts at `docs/dokumentace/`; skill `dokumentace` + agent `docs-keeper` must keep it current.
- No new dependencies unless explicitly requested + reviewed.
