# v2 narrative runtime — implementation handover

**Updated:** 2026-09-07
**Phase:** #236 implementation — acceptance candidate GREEN, pending second checkpoint push
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
- First #236 implementation SHA: `be7c915a410fa9e9752e5259f2ad9a04ff3c037c` (`feat: add v2 contract primitives (#236)`)
- Green CI: [run 34148330942](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34148330942)
- First #236 [dev diary checkpoint](https://github.com/Buchtanen/ir-obs-switcher/issues/236#issuecomment-5574070160)
- Expected working tree before the second #236 commit: the second-slice files below are dirty; after push it must be clean and synchronized with upstream
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

- Editing owner: current root agent until the second #236 checkpoint is pushed, green and recorded.
- Dirty scope: `src/irswitch/contracts/{__init__,primitives,resources,session}.py`, `tests/test_contract_primitives.py`, `tests/test_session_plan_contract.py` and this handover record.
- Completed #236 scope: the first primitive/schema checkpoint plus bounded serializable valid/conflict `SessionPlan`, exact unsupported-row overflow, safe packaged-schema resource loading, strict JSON-value hashing and the frozen deterministic planning seed.
- TDD phase: `GREEN` — SessionPlan began with a missing-import RED; strict JSON-key validation began with an assertion RED; both are now green.
- Verification: 74 focused tests pass; affected Ruff, Ruff format, Black and Mypy pass; all 11 freeze builders pass; full regression passes with 1,438 tests outside the socket-restricted sandbox.
- Packaging evidence: a locally built wheel contains both JSON artifacts with frozen SHA-256 values `cab0aaf8...fd8db2b` and `9aaeeb4f...338145`.
- Config impact: packaging metadata only; no commentary configuration key or example change.
- API impact: none; no live/public endpoint is wired in this checkpoint.

## Exact next implementation slice

After the second #236 checkpoint is pushed:

1. Wait for CI and record its immutable SHA/run plus RED/GREEN and wheel evidence in issue #236.
2. Audit every #236 checkbox against the two pushed implementation checkpoints; if CI is green and no gap remains, update the issue/index state and close #236.
3. Re-verify a clean HEAD equal to upstream, then begin dependency-unblocked #237 with a fresh focused RED slice. Do not implement timeline ownership from #243/#244 early.

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
