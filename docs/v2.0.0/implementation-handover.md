# v2 narrative runtime — implementation handover

**Updated:** 2026-09-07
**Phase:** #237 implementation — recovery evidence reconciliation GREEN, pending push
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
- Coherent-batch SHA: `2a6d57e03419a7e8cadfd2153184df6e01403da3` (`feat: add coherent narrative context batches (#237)`); [CI run 34152629347](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34152629347) is green on Python 3.11–3.13.
- Bounded command/mailbox foundation SHA: `325e2020dff3768e70a16137905769f710ae7ff5` (`feat: add bounded narrative mailbox foundation (#237)`); [CI run 34155593258](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34155593258) is green on Python 3.11–3.13.
- Lifecycle/idempotency SHA: `abce38b604cd51d4b22791f5ecf0ebcc9dabf8ac` (`feat: add lifecycle narrative admission (#237)`); [CI run 34156674432](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34156674432) is green on Python 3.11–3.13.
- Expected working tree before the recovery-evidence push: only the files listed in the ownership section are dirty.
- Runtime behavior edits so far: dependency-neutral v2 primitives, the stateless accepted-V4-to-NarrativeEvent adapter, immutable coherent context batching, a 17-kind NarrativeCommand factory/discriminator foundation and the bounded mailbox foundation; no live producer, actor reducer or tape wiring yet.

Do not use `/home/richa/Dokumenty/ChatGPT/iROBSwitcher` for this work: it is a separate dirty checkout on another branch. Always verify the identity commands below before editing.

## Accepted state

- Independent design-freeze repair is complete: 11/11 machine builders pass.
- Baseline evidence: 1,364 pytest tests passed; 12 branch Python files pass Ruff and Black; Mypy passes 174 source files; 33 JSON files parse and seven Draft 2020-12 schemas validate.
- Issue #235 contains the published evidence at commit `b0cab18`; human acceptance was given on 2026-09-07.
- The control-plane evidence and green CI are recorded in the [closing dev diary](https://github.com/Buchtanen/ir-obs-switcher/issues/235#issuecomment-5573626335); #235 is closed as completed.
- The Codex-discoverable `.agents/skills/source-command-handover/` wrapper delegates to the canonical command/rule instead of duplicating their instructions.
- Frozen architecture, DTO, catalog, detector, realization, transport and F01–F44 contracts live under `docs/v2.0.0/`.

## Current checkpoint ownership

- Editing owner: current root agent until the recovery-evidence checkpoint is pushed, green in CI and recorded.
- Dirty scope: `src/irswitch/commentary/mailbox.py`, `tests/test_narrative_context_batch.py`, `docs/v2.0.0/actor-transition-contract.md`, `docs/v2.0.0/machine/{build_actor_transition_model.py,actor-transition-model.json,actor-transition-model.schema.json}` and this handover record.
- Completed #237 scope: the accepted-event and coherent-batch scope above plus factory/discriminator coverage for all 17 command kinds; one ordered 56/7/1 `NarrativeMailbox`; atomic sequence assignment; exact ordinary/protected classification and permitted coalescing; deterministic ordinary eviction; atomic config/tape-health plus protected-context admission; visible recovery placement/refresh; and idempotent shutdown ownership of the emergency cell.
- Current #237 scope: recovery-producing admission results return the complete immutable evicted command, preserving its external ordinal range, context revision and payload for actor/tape evidence. More than 64 distinct protected safety effects are represented by one chained canonical digest commitment plus the latest 63 explicit effects; refresh changes the commitment rather than silently dropping prior evidence.
- TDD phase: `GREEN` — focused RED asserted full evicted context evidence; the existing overflow test was tightened to prove the digest commitment is present and changes on refresh.
- Verification: 37 focused context-batch/command/mailbox/lifecycle/idempotency tests pass; actor-transition machine builder validates 5×17 transition pairs, 13 race traces, 10 overflow scenarios and 10 rejected mutations; affected Ruff, Ruff format, Black and Mypy pass; full regression passes with 1,485 tests.
- V4 boundary evidence: adapter tests prove the input EventEnvelope dictionary is unchanged; visual-only/compatibility identifiers and empty fact evidence fail closed.
- Portability fix: runtime `taxonomyHash` is canonical-JSON identity `sha256:7420930a...d7d52`; raw artifact hash `cab0aaf8...fd8db2b` remains packaging evidence only.
- Config impact: none.
- API impact: none; the existing V4 envelope/overlay wire remains unchanged and the adapter is not live-wired yet.
- Docs impact: the frozen actor-transition contract and its generated machine model now define complete evicted-command evidence and bounded chained safety-effect commitment. No V4/API/config surface changes and the foundation is not live-wired.

## Exact next implementation slice

After the recovery-evidence checkpoint is pushed and CI is green:

1. Record the checkpoint SHA/CI evidence in the existing dated #237 diary.
2. Reconcile #237's implementation-boundary checklist with #284: live EventSubscription replacement, reducer sequence/state replay and integrated actor-loop liveness belong to the dependent NarrativeRuntime actor and cannot be activated before #238/#240/#243/#245/#258/#262/#264/#265/#269.
3. Reconcile and publish the #237/#284 implementation boundary before closing #237: this package owns immutable admission/order/dedupe/mailbox behavior; #284 owns live actor wiring, reducer-state replay and integrated loop liveness after its remaining dependencies.

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
- Mailbox foundation alone is not live actor acceptance: actor reduction still owns reducer-sequence replay equivalence, shutdown terminal-callback handling and health/tape counter effects in #284.
- The two independent audit agents exhausted their own quota after the lifecycle checkpoint. Continuity remained intact through this handover, the existing issue diary, local TDD evidence and reproducible machine builders; rerun independent review when capacity returns, but do not discard the verified working state.
