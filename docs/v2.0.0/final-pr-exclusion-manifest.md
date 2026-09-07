# v2.0.0 final-PR exclusion manifest

**Status:** mandatory release check owned by issues #279 and #282

The v2 branch intentionally contains planning evidence and may temporarily contain a comparison harness. The atomic breaking PR to `master` must not include either. This manifest is itself branch-only and is deleted before that PR.

## Planning paths absent from final diff

- `docs/commentary_narrative_runtime_spec.md`
- `docs/v2.0.0/README.md`
- `docs/v2.0.0/design-freeze-audit.md`
- `docs/v2.0.0/event-beat-disposition.md`
- `docs/v2.0.0/public-contracts.md`
- `docs/v2.0.0/actor-transition-contract.md`
- `docs/v2.0.0/schema-contracts.md`
- `docs/v2.0.0/fact-feature-registry.md`
- `docs/v2.0.0/detector-catalog-freeze.md`
- `docs/v2.0.0/realization-verifier-contract.md`
- `docs/v2.0.0/qwen-transport-contract.md`
- `docs/v2.0.0/vertical-slice-fixtures.md`
- `docs/v2.0.0/final-pr-exclusion-manifest.md`
- temporary v2 planning links added to root `README.md` and `COMMENTARY_ENGINE.md`

Their decisions survive only in implementation, tests/fixtures, migration/release notes and updated current-behavior docs.

## Temporary branch mechanisms absent from final build

- legacy-vs-v2 shadow/comparison adapters, duplicate fanout subscriptions and temporary replay translators;
- per-family or global runtime selectors such as `graph_runtime_mode`, legacy/shadow feature flags or dual-write switches;
- sequence-graph v1 compatibility loader and `/api/commentary/assignments` route;
- retry/repair/same-beat fallback controls including `llm_max_attempts`;
- prepared utterance waiter/queue and any second worker-result inbox;
- CS commentary catalog/routing. General overlay localization remains unaffected.

Existing modules may be deleted, replaced or retained for non-runtime migration tooling only if import/reachability tests prove none of these mechanisms is callable in the packaged v2 service. File name alone is not sufficient evidence.

## Required final behavior docs

Unlike the planning files, these updates are mandatory in the final PR:

- `COMMENTARY_ENGINE.md` describing actual v2 behavior only;
- `CONFIG.md` and `config/config.example.ini` with exact keys/defaults/migration;
- `API.md` and `/commentary` operator page for `commentary-runtime/2`;
- release/changelog major-version migration and downgrade procedure;
- build/deploy prerequisites for Ollama/SuperTonic only where the final packaging actually requires them;
- replay/tape/operator runbook and schema/version maintenance rules.

## Mechanical release checks

Before opening the final PR:

1. compare `git diff --name-status master...HEAD` with this list and prove every planning path/link is absent;
2. search packaged/importable code and config schema for `graph_runtime_mode`, `legacy`, `shadow`, `llm_max_attempts`, assignments route and waiter/queue symbols, with every intentional unrelated match reviewed;
3. build the distribution and inspect its file list so removed graph/catalog/planning assets are not bundled accidentally;
4. run architecture/import tests proving one NarrativeRuntime, one mailbox, one FactLedger/StreamTimeline owner and unchanged V4 overlay wire;
5. run full CI, Windows live acceptance and downgrade rollback drill;
6. record the release commit SHA and evidence in #279/#234 before merge.

Closing a branch issue does not waive this manifest. Any intentional exception must be named and justified in #234 before the final PR; a silent exception is a release blocker.
