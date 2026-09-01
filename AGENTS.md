# Codex Rules — irswitch (index)

This file is intentionally short to avoid duplicating the canonical rules.

## Source of truth
Authoritative rules live in:
- `.cursor/rules/*.mdc`

Task skills (start/restart, YouTube OAuth) live in:
- `.cursor/skills/*/SKILL.md`

## Core expectations (summary)
- Stability > elegance; determinism > cleverness.
- External systems (iRacing/OBS/network) are unreliable: **never crash the main loop**.
- Respect layer boundaries: `iracing/` extract, `obs/` client, `logic/` scenes, `events/`/`overlay/`/`commentary/`/`race/` peers, `server/` glue — see `.cursor/rules/py-architecture-layers.mdc`.
- Async-first: no blocking in async loops; background tasks must be owned/cancellable; cooldowns are time-based (monotonic).
- Evidence required for behavior changes: tests or explicit TDD-exception + verification plan.
- Docs/config are part of the contract; update relevant docs when behavior changes.
- No new dependencies unless explicitly requested + reviewed.
