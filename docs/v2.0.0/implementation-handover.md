# v2 narrative runtime — implementation handover

**Updated:** 2026-09-07
**Phase:** design freeze accepted; control-plane checkpoint in progress
**Authoritative issues:** [#234](https://github.com/Buchtanen/ir-obs-switcher/issues/234), [#235](https://github.com/Buchtanen/ir-obs-switcher/issues/235), next [#236](https://github.com/Buchtanen/ir-obs-switcher/issues/236)

This is the branch-local recovery record. GitHub issue comments remain authoritative for accepted work and immutable pushed SHAs. Update this file before a meaningful push, ownership transfer, long pause or agent replacement. This planning file is removed by the final-PR exclusion gate.

## Resume identity

- Repository: `Buchtanen/ir-obs-switcher`
- Worktree: `/home/richa/Dokumenty/ChatGPT/iROBSwitcher-story-flow-spec`
- Branch: `codex/commentary-story-flow-spec`
- Upstream: `origin/codex/commentary-story-flow-spec`
- Last pushed design-freeze SHA: `b0cab18cba23c3acc96aecad7ac527793d22d4b0`
- Working tree at handover creation: clean before the control-plane edits described in this checkpoint
- Runtime behavior edits so far: none

Do not use `/home/richa/Dokumenty/ChatGPT/iROBSwitcher` for this work: it is a separate dirty checkout on another branch. Always verify the identity commands below before editing.

## Accepted state

- Independent design-freeze repair is complete: 11/11 machine builders pass.
- Baseline evidence: 1,364 pytest tests passed; 12 branch Python files pass Ruff and Black; Mypy passes 174 source files; 33 JSON files parse and seven Draft 2020-12 schemas validate.
- Issue #235 contains the published evidence at commit `b0cab18`; human acceptance was given on 2026-09-07.
- Frozen architecture, DTO, catalog, detector, realization, transport and F01–F44 contracts live under `docs/v2.0.0/`.

## Current checkpoint ownership

- Editing owner: the active parent agent only.
- Files in scope: CI trigger/freeze gate, Codex verifier, handover rule/command/skill and this record.
- Other agents: read-only verification only until this checkpoint is committed and pushed.
- TDD phase: `N/A` — process/CI/docs-only change.
- TDD exception: no product behavior changes; verification is workflow syntax, all 11 builders and scoped static checks.

## Exact next implementation slice

After this control-plane checkpoint is green, pushed, recorded in the issue diary and #235 is closed:

1. Start issue #236; do not skip its dependency gate.
2. Enter `RED` by adding focused tests for canonical ID parsing/serialization, version validation, units, clock semantics and deterministic JSON hashing.
3. Implement the smallest immutable primitives needed to turn those tests green; expected ownership is a new `src/irswitch/contracts/` package plus its focused tests.
4. Promote byte-equivalent registry/schema artifacts only as required by #236 and verify hashes against `docs/v2.0.0/machine/`.
5. Run focused pytest, affected Ruff/Black/Mypy, all 11 freeze builders, then update this record and #236 dev diary before push.

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
