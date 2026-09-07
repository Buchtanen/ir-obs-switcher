# v2 narrative runtime — implementation handover

**Updated:** 2026-09-07
**Phase:** #237 implementation — coherent batch/order checkpoint GREEN, pending push; next is bounded mailbox admission
**Authoritative issues:** [#234](https://github.com/Buchtanen/ir-obs-switcher/issues/234), completed [#235](https://github.com/Buchtanen/ir-obs-switcher/issues/235) and [#236](https://github.com/Buchtanen/ir-obs-switcher/issues/236), active [#237](https://github.com/Buchtanen/ir-obs-switcher/issues/237)

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
- Final #236 implementation SHA: `4493615cce6b92842f7e5a0741c5bb8df71e5435` (`feat: complete v2 primitive contracts (#236)`)
- Green CI: [first checkpoint run 34148330942](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34148330942), [final acceptance run 34149625428](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34149625428)
- First #236 [dev diary checkpoint](https://github.com/Buchtanen/ir-obs-switcher/issues/236#issuecomment-5574070160)
- Final #236 [dated dev diary](https://github.com/Buchtanen/ir-obs-switcher/issues/236#issuecomment-5566224409); every checklist item is complete and the issue is closed.
- #236 closing metadata SHA: `935fb02eec07dccd94113f3cba0b0312edafff2d`
- First #237 implementation SHA: `c7a6709160b29c483283fdaac0002daeb9eff56b` (`feat: add narrative event admission contracts (#237)`).
- CI run [34151258760](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34151258760) correctly failed the first cross-platform acceptance attempt: raw packaged JSON bytes hash differently after Windows CRLF checkout materialization.
- Portability-fix SHA: `7fdfb832a64add97f062e3998912ee91a80a87e0` (`fix: canonicalize narrative taxonomy hash (#237)`); corrective [CI run 34151680014](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34151680014) is green.
- First #237 [dated dev diary](https://github.com/Buchtanen/ir-obs-switcher/issues/237#issuecomment-5566224531).
- First #237 acceptance-metadata SHA: `eca280b` (`docs: record narrative admission checkpoint (#237)`).
- Expected working tree before the coherent-batch push: only the files listed in the ownership section are dirty.
- Runtime behavior edits so far: dependency-neutral v2 primitives, a stateless accepted-V4-to-NarrativeEvent adapter and immutable coherent context batching; no live producer or actor wiring yet.

Do not use `/home/richa/Dokumenty/ChatGPT/iROBSwitcher` for this work: it is a separate dirty checkout on another branch. Always verify the identity commands below before editing.

## Accepted state

- Independent design-freeze repair is complete: 11/11 machine builders pass.
- Baseline evidence: 1,364 pytest tests passed; 12 branch Python files pass Ruff and Black; Mypy passes 174 source files; 33 JSON files parse and seven Draft 2020-12 schemas validate.
- Issue #235 contains the published evidence at commit `b0cab18`; human acceptance was given on 2026-09-07.
- The control-plane evidence and green CI are recorded in the [closing dev diary](https://github.com/Buchtanen/ir-obs-switcher/issues/235#issuecomment-5573626335); #235 is closed as completed.
- The Codex-discoverable `.agents/skills/source-command-handover/` wrapper delegates to the canonical command/rule instead of duplicating their instructions.
- Frozen architecture, DTO, catalog, detector, realization, transport and F01–F44 contracts live under `docs/v2.0.0/`.

## Current checkpoint ownership

- Editing owner: current root agent until the coherent-batch checkpoint is pushed, green in CI and recorded.
- Dirty scope: `src/irswitch/contracts/{__init__,context}.py`, `src/irswitch/events/narrative.py`, `tests/test_narrative_context_batch.py` and this handover record.
- Completed #237 scope: the accepted-event admission scope above plus immutable coherent ApplyContextBatch snapshots, fact/view identity checks, lossless 64-event partitioning, exact external ordinal ranges and deterministic event/revision dedupe.
- TDD phase: `GREEN` — the batch slice began with an import-collection RED for missing ApplyContextBatch.
- Verification: 16 new focused tests and 90 combined contract tests pass; affected Ruff, Ruff format, Black and Mypy pass; full regression passes with 1,454 tests outside the socket-restricted sandbox.
- V4 boundary evidence: adapter tests prove the input EventEnvelope dictionary is unchanged; visual-only/compatibility identifiers and empty fact evidence fail closed.
- Portability fix: runtime `taxonomyHash` is canonical-JSON identity `sha256:7420930a...d7d52`; raw artifact hash `cab0aaf8...fd8db2b` remains packaging evidence only.
- Config impact: none.
- API impact: none; the existing V4 envelope/overlay wire remains unchanged and the adapter is not live-wired yet.

## Exact next implementation slice

After the coherent-batch checkpoint is pushed and CI is green:

1. Record the checkpoint SHA/CI evidence in the existing dated #237 diary.
2. Add a focused RED for the 56/7/1 single NarrativeMailbox admission, coalescing, eviction, recovery and shutdown ordering rules.
3. Implement that mailbox without creating a second worker-result queue; preserve V4 overlay wire and defer timeline ownership to #243/#244.

## Resume commands

```bash
cd /home/richa/Dokumenty/ChatGPT/iROBSwitcher-story-flow-spec
pwd
git status --short --branch
git rev-parse HEAD
git rev-parse @{upstream}
```

Expected before resuming #237: correct worktree and branch, local HEAD/upstream relationship understood, #235/#236 closed, and dirty files matching the ownership section. Any mismatch is a blocker until its ownership is understood.

## Known risks

- A pushed `codex/**` branch previously skipped CI; this checkpoint adds it to the CI trigger.
- Freeze builders were manual-only; this checkpoint adds an explicit CI job while branch-only artifacts exist.
- Local git hooks are intentionally not installed: linked worktrees share the repository hook directory and the current installer assumes `.git` is a directory. Installing it from this worktree would affect unrelated dirty branches. CI plus explicit `/qa` remains the safe gate until a separately reviewed worktree-aware hook policy exists.
- Multiple worktrees exist, so path verification is mandatory.
- Quota exhaustion does not automatically transfer ownership. Resume from this file plus the latest issue diary.
