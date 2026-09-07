# v2 narrative runtime — implementation handover

**Updated:** 2026-09-07
**Phase:** #236 implementation — first primitives checkpoint GREEN, pending push
**Authoritative issues:** [#234](https://github.com/Buchtanen/ir-obs-switcher/issues/234), completed [#235](https://github.com/Buchtanen/ir-obs-switcher/issues/235), active [#236](https://github.com/Buchtanen/ir-obs-switcher/issues/236)

This is the branch-local recovery record. GitHub issue comments remain authoritative for accepted work and immutable pushed SHAs. Update this file before a meaningful push, ownership transfer, long pause or agent replacement. This planning file is removed by the final-PR exclusion gate.

## Resume identity

- Repository: `Buchtanen/ir-obs-switcher`
- Worktree: `/home/richa/Dokumenty/ChatGPT/iROBSwitcher-story-flow-spec`
- Branch: `codex/commentary-story-flow-spec`
- Upstream: `origin/codex/commentary-story-flow-spec`
- Last pushed design-freeze SHA: `b0cab18cba23c3acc96aecad7ac527793d22d4b0`
- Control-plane evidence SHA: `2d2f014592d5728f0eebe49afae73424ff44c35d` (`ci: enforce v2 checkpoints and agent handover (#235)`)
- Last pushed handover SHA before #236: `d81b70a85b67a30273abfddbb39cd0b6ad513097`
- Expected working tree before the first #236 commit: the files listed under current checkpoint ownership are dirty; after push it must be clean and synchronized with upstream
- Runtime behavior edits so far: new dependency-neutral v2 primitive contract layer only; it is not yet wired into live producers or commentary

Do not use `/home/richa/Dokumenty/ChatGPT/iROBSwitcher` for this work: it is a separate dirty checkout on another branch. Always verify the identity commands below before editing.

## Accepted state

- Independent design-freeze repair is complete: 11/11 machine builders pass.
- Baseline evidence: 1,364 pytest tests passed; 12 branch Python files pass Ruff and Black; Mypy passes 174 source files; 33 JSON files parse and seven Draft 2020-12 schemas validate.
- Issue #235 contains the published evidence at commit `b0cab18`; human acceptance was given on 2026-09-07.
- The control-plane evidence and green CI are recorded in the [closing dev diary](https://github.com/Buchtanen/ir-obs-switcher/issues/235#issuecomment-5573626335); #235 is closed as completed.
- The Codex-discoverable `.agents/skills/source-command-handover/` wrapper delegates to the canonical command/rule instead of duplicating their instructions.
- Frozen architecture, DTO, catalog, detector, realization, transport and F01–F44 contracts live under `docs/v2.0.0/`.

## Current checkpoint ownership

- Editing owner: current root agent until the #236 primitives checkpoint is pushed and recorded.
- Dirty scope: `pyproject.toml`, `src/irswitch/contracts/**`, `tests/test_contract_primitives.py` and this handover record.
- Completed scope in this checkpoint: validated broadcast/stream epochs, source sequence, correlation/occurrence/lineage IDs, process/stream/session monotonic clocks, scalar-unit/confidence/unknown/stale semantics, closed schema/hash values, canonical JSON hashing and packaged frozen registry/DTO schemas.
- TDD phase: `GREEN` — the focused suite passes after an observed import-failure RED.
- Verification: 60 focused tests pass; affected Ruff, Ruff format, Black and Mypy pass; all 11 freeze builders pass; full regression passes with 1,424 tests outside the socket-restricted sandbox.
- Config impact: packaging metadata only; no commentary configuration key or example change.
- API impact: none; no live/public endpoint is wired in this checkpoint.

## Exact next implementation slice

After the first #236 primitives checkpoint is pushed:

1. Verify local HEAD equals upstream and record the immutable SHA plus CI run in issue #236.
2. Continue #236 with focused RED tests for the bounded serializable `SessionPlan` and shared DTO field adapters that consume these primitives; do not implement timeline ownership from #243/#244 early.
3. Add a wheel-content verification proving both packaged JSON artifacts survive distribution packaging.
4. Re-run focused pytest, affected Ruff/Black/Mypy, all 11 freeze builders and the full regression before deciding whether #236 acceptance is complete.

## Resume commands

```bash
cd /home/richa/Dokumenty/ChatGPT/iROBSwitcher-story-flow-spec
pwd
git status --short --branch
git rev-parse HEAD
git rev-parse @{upstream}
```

Expected before implementation: correct worktree and branch, clean tree, local HEAD equal to upstream, #235 closed, and #236 open. Any mismatch is a blocker until its ownership is understood.

## Known risks

- A pushed `codex/**` branch previously skipped CI; this checkpoint adds it to the CI trigger.
- Freeze builders were manual-only; this checkpoint adds an explicit CI job while branch-only artifacts exist.
- Local git hooks are intentionally not installed: linked worktrees share the repository hook directory and the current installer assumes `.git` is a directory. Installing it from this worktree would affect unrelated dirty branches. CI plus explicit `/qa` remains the safe gate until a separately reviewed worktree-aware hook policy exists.
- Multiple worktrees exist, so path verification is mandatory.
- Quota exhaustion does not automatically transfer ownership. Resume from this file plus the latest issue diary.
