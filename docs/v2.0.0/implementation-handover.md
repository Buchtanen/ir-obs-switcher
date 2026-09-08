# v2 narrative runtime — implementation handover

**Updated:** 2026-09-08
**Phase:** #240 closed; next implementation package is #242
**Authoritative issues:** [#234](https://github.com/Buchtanen/ir-obs-switcher/issues/234), completed [#235](https://github.com/Buchtanen/ir-obs-switcher/issues/235), [#236](https://github.com/Buchtanen/ir-obs-switcher/issues/236), [#237](https://github.com/Buchtanen/ir-obs-switcher/issues/237), [#238](https://github.com/Buchtanen/ir-obs-switcher/issues/238), [#239](https://github.com/Buchtanen/ir-obs-switcher/issues/239) and [#240](https://github.com/Buchtanen/ir-obs-switcher/issues/240), next [#242](https://github.com/Buchtanen/ir-obs-switcher/issues/242)

This is the branch-local recovery record. GitHub issue comments remain authoritative for accepted work and immutable pushed SHAs. Update this file before a meaningful push, ownership transfer, long pause or agent replacement. This planning file is removed by the final-PR exclusion gate.

## Resume identity

- Repository: `Buchtanen/ir-obs-switcher`
- Worktree: `/workspace` for this cloud-agent continuation; the original linked worktree remains `/home/richa/Dokumenty/ChatGPT/iROBSwitcher-story-flow-spec`
- Branch: `codex/commentary-story-flow-spec`
- Upstream: `origin/codex/commentary-story-flow-spec`
- First #240 async-writer SHA: `23abfdefdde8db2f037311b6345b5af03c658e58` (`feat: add async narrative tape writer and rotation (#240)`)
- First #240 file-session SHA: `ec3da3eb0b6bfb7901637919290a987fd802cf40` (`feat: add narrative tape NDJSON file session (#240)`)
- First #240 queue SHA: `246fbee52a6e11f9fd949f407dca079344c0ee85` (`feat: add bounded narrative tape record queue (#240)`)
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
- Recovery-evidence SHA: `3ce1535c06e542f88ccdd3fc58346c2e57e93318` (`fix: preserve bounded mailbox recovery evidence (#237)`). CI run [34157119475](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34157119475) correctly failed the frozen-contract job because the dependent F01–F44 fixture bundle still named the prior actor-model hash.
- Cross-artifact correction SHA: `4e8a1f7dfdb48f1c79f11c2e6108afcc7780ce99` (`docs: refresh recovery contract evidence (#237)`); corrective [CI run 34157345490](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34157345490) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- The public #237 checklist now records the explicit implementation boundary: #237 owns deterministic admission/order/deduplication and the bounded mailbox primitive; #284 owns live actor wiring, reducer-state replay and integrated loop liveness.
- #237 closing-metadata SHA: `a174c82d631aafb0009950b34e98fdfae8a0ce61` (`docs: close narrative admission checkpoint (#237)`); final [CI run 34157790048](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34157790048) is green and #237 is closed as completed.
- First #238 parser SHA: `ccd88f707c7641c8845161e2991911e0fcd750d9` (`feat: add strict v2 config candidate parser (#238)`); [CI run 34158763067](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34158763067) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #238 ConfigLedger SHA: `f06f38392bd8af68afec5cb37a7978711a2f1291` (`feat: add immutable v2 config ledger (#238)`); [CI run 34159447155](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34159447155) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #238 detector/tuning/path SHA: `d35e0d65c72e9f9492bfe26ed783fd9289a55b57` (`feat: enforce v2 detector config safety (#238)`); [CI run 34160114565](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34160114565) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #238 fail-soft load SHA: `349ee51587cadc909dbdad19b4da6a8d2a08ae2f` (`feat: load v2 commentary config fail-soft (#238)`); [CI run 34161392389](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34161392389) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #238 persistent reload-owner SHA: `64b75f03dafc4bea2d6c9c194a43afc10617981d` (`feat: own v2 config reload generations (#238)`); [CI run 34162015998](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34162015998) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #238 public-control/migration SHA: `fe72658f104180d2b02158ec426853075ccb76b5` (`refactor: remove legacy commentary config controls (#238)`); [CI run 34162505534](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34162505534) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #238 closing-metadata SHA: `6278c3419b40763aae7c127dac020539f7b4934c` (`docs: close v2 config checkpoint (#238)`); final [CI run 34162894430](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34162894430) is green and #238 is closed as completed.
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

- Editing owner: current cloud agent closing #240. Next owner starts #242 replay reader on this same branch.
- Dirty scope: this closing handover plus the Wave A index mirror.
- Completed #237 scope: accepted-event and coherent-batch contracts; factory/discriminator coverage for all 17 command kinds; one ordered 56/7/1 `NarrativeMailbox`; atomic admission sequence assignment; exact ordinary/protected classification and permitted coalescing; deterministic ordinary eviction; atomic config/tape-health plus protected-context admission; visible recovery placement/refresh; idempotent shutdown ownership of the emergency cell; complete immutable evicted-command evidence; and bounded chained safety-effect commitment.
- Deferred by explicit ownership, not incomplete #237 work: live EventSubscription replacement and producer wiring, reducer-sequence assignment/state replay, async actor effects, integrated loop liveness and shutdown execution belong to #284 after its dependencies.
- Completed #238 scope: packaged copies of the frozen config and detector registries back a pure immutable desired-candidate parser. It enforces the fully defaulted 50-key static map, exported detector override types/ranges, strict INI scalar grammar, normalized strings/sets, local/LAN literal URL policy, root-path rejection, cross-field goldens, unknown-key rejection and all frozen v1 legacy matching without installing a partial candidate. Snapshot hashes include real normalized sensitive values while replay export uses markers.
- Completed #238 ledger scope: lock-owned `ConfigLedger` preserves complete immutable desired/effective snapshots, installs only whole valid candidates, monotonically assigns desired generations and apply sequence, recomputes sorted pending changes from the whole desired/effective maps, applies only exact named-boundary patches and emits no no-op record. Component preflights are generation-tagged; stale completions cannot make an old backend available. Invalid input installs no generation, disables automatic narration in its outcome and preserves the last valid manual component readiness.
- Completed #238 detector safety scope: all directional detector parameter overrides are composed over catalog defaults and checked against the eight frozen cross-field relations. Required-tuning detectors can be enabled only in calibration with detector-tuning tape, explicit allowlist, input windows and successful writable-recorder preflight. URL validation uses exact loopback/RFC1918/link-local/IPv6-ULA networks rather than Python's broader `is_private`; default and explicit output paths reject root, unwritable parents and existing relative symlinks escaping the working parent.
- Completed #238 load scope: every `AppConfig.from_file` call, including `POST /config/reload`, produces a strict immutable v2 commentary candidate. Invalid or legacy commentary sections emit value-free diagnostics, do not abort other application-domain loading and leave the legacy commentary runtime disabled. Valid v2 values remain isolated from `OverlaySettings.commentary`, so this checkpoint cannot activate the future `NarrativeRuntime` or reinterpret a v1 key.
- Completed #238 reload-owner scope: one process-lifetime `CommentaryConfigCoordinator` owns `ConfigLedger` from application startup across reloads. Generation zero bootstraps from the valid startup candidate or disabled frozen defaults; each valid reload installs one generation and immediately applies only the `command` boundary. Invalid input creates no generation, sets automatic requested state false, preserves last-valid desired/effective maps and current manual TTS readiness. `POST /config/reload` projects hashes, generation, apply sequence, value-free sorted pending changes, fixed `speech_language=en`, diagnostics and generation-tagged preflight requests without constructing resources or activating NarrativeRuntime.
- Completed #238 public-control scope: the schema-driven GET/PUT config surface, flattened overlay value projection and generic live-key whitelist contain no `commentary.*` key. Attempts to write legacy commentary or graph-runtime keys fail as unknown rather than persisting an unusable selector. The legacy manual-test page no longer offers a config save action; direct INI reload remains the sole current v2 entry and preserves frozen migration diagnostics. A runtime test derives all 13 migration rows from the packaged contract and exercises 16 exact/prefix/group/section representatives.
- #239 schema scope is complete: the manifest uses exact redaction-safe effective-config projection entries and bounded exact detector parameter snapshots. The record-kind discriminator is closed to the frozen 16 kinds. All 16 TapeRecord payloads are exact named DTOs, including CoverageBucket and RedactionPolicy.
- First #239 framing SHA: `ca02e8937f14ce6aad8e01960fff489421adaed4` (`feat: close narrative tape framing schemas (#239)`); [CI run 34163837729](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34163837729) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs. Its evidence is appended to the existing dated #239 dev diary.
- #239 ordered/config SHA: `111c4a6ff6cb4b2a3a87c94a4e228bec9dd486ea` (`feat: enforce narrative tape ordering (#239)`); [CI run 34164288062](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34164288062) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs. Only actor-produced record families may carry non-null reducer order; detector/event/narrative/opportunity/director records require `tapeChannel`; `config_applied` has an exact replay-safe payload whose redacted entries cannot retain a value.
- #239 loss/trailer DTO SHA: `7b98840653c01c8d79a844c9fcd6d3214c1049bd` (`feat: define narrative tape loss framing (#239)`); [CI run 34167346863](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34167346863) is green across frozen contracts, Python 3.11–3.13, lint, format, type and security jobs.
- #239 loss/trailer golden SHA: `bfb4187637cb81d50113ce321f94e6b50ac6cc0d` (`feat: add narrative tape loss goldens (#239)`); [CI run 34167795931](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34167795931) is green across 14/14 checks.
- #239 remaining-payload SHA: `7484487afa3c0da1fa87a9828dcbac8f5069fcde` (`feat: close remaining narrative tape payloads (#239)`); [CI run 34168334293](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34168334293) is green across 14/14 checks (frozen contracts, Python 3.11–3.13, lint, format, type, security). Runtime `taxonomyHash` is `sha256:720769b0a1dfb234c69529eab9e1818e37944eead1de6e41499e6cbb56baa26b`.
- #239 coverage/redaction SHA: `eb0f1670f601abba56c37852c664901233029eaf` (`feat: derive coverage buckets and tape redaction policy (#239)`); [CI run 34170887655](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34170887655) is green across 14/14 checks. DTO builder 50 definitions, 24 valid + 23 invalid goldens; local pytest **1537** passed.
- First #240 async-writer SHA: `23abfdefdde8db2f037311b6345b5af03c658e58` (`feat: add async narrative tape writer and rotation (#240)`). Local pytest: queue+writer+schema **35** passed. Final [CI run 34174315223](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34174315223) is green across 14/14 checks on HEAD `d079ff7`.
- First #240 file-session SHA: `ec3da3eb0b6bfb7901637919290a987fd802cf40` (`feat: add narrative tape NDJSON file session (#240)`). Local pytest: `tests/test_narrative_tape_writer.py` **8** passed; queue+writer+schema **28** passed.
- First #240 queue SHA: `246fbee52a6e11f9fd949f407dca079344c0ee85` (`feat: add bounded narrative tape record queue (#240)`). Handover SHA `67cbe196ed7ca23eb0289e0790539b930a1c1693`. Local pytest: `tests/test_narrative_tape_queue.py` **10** passed. [CI run 34173579819](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34173579819) is green across 14/14 checks.
- #239 nested-row SHA: `1b73fcff5df6f6f6e511e504f78339dc6dc0f636` (`feat: type feature-frame and observation rows (#239)`); [CI run 34169039942](https://github.com/Buchtanen/ir-obs-switcher/actions/runs/34169039942) is green across 14/14 checks. DTO builder 48 definitions, 24 valid + 21 invalid goldens; local pytest **1536** passed.
- Docs-only SHA `71a6f97` failed Python 3.12 on unrelated wall-clock flake `test_full_queue_500_batch_publication_meets_n12_deadline` (66ms > 50ms) after 14/14 green parent `7484487`; the nested-row SHA recovered CI without changing that test.
- V4 boundary evidence: adapter tests prove the input EventEnvelope dictionary is unchanged; visual-only/compatibility identifiers and empty fact evidence fail closed.
- Portability fix: runtime `taxonomyHash` remains canonical-JSON identity of the packaged freeze registry, not raw checkout bytes. The hash moved because the schema-version table grew; Windows CRLF lesson from #237 still applies.
- Config impact: the strict v2 commentary load path is active. `config/config.example.ini` now uses only frozen v2 sections/keys; legacy commentary settings diagnose and cannot activate legacy execution. Other application config remains loadable when commentary is invalid.
- API impact: additive `commentary_config` projection on the existing `POST /config/reload` success response. Invalid commentary returns `installed=false` and diagnostics while the endpoint remains successful for unrelated config. Frozen `/api/v2/commentary/*` routes remain deferred to #273.
- Docs impact: branch-only schema-contract prose now states that `payloadSchemaVersion` is a schema-version token, not a generic ID. No public CONFIG/API/README change; TapeWriter/NarrativeRuntime remain inactive.

## Exact next implementation slice

1. #239 is closed in its own scope: versioned records and manifest sufficient to persist and later replay detector, story, LLM and speech decisions.
2. #240 first slice (this checkpoint): in-memory `TapeRecordQueue` in `src/irswitch/commentary/tape_queue.py` with exact sample-then-normal eviction, FIFO within class, registry-bounded `TapeLossAccumulator`, out-of-queue `CaptureHealthLatch`, config-barrier `config_transition_lost`, and `drop-notice/2` flush. Evidence: `tests/test_narrative_tape_queue.py` (F27 queue/loss/notice subset). No disk I/O, no async writer task, no NarrativeRuntime/DetectorBank import, no V4 overlay tape mixing.
3. #240 file-session slice: `TapeFileSession` in `src/irswitch/commentary/tape_writer.py` writes one NDJSON file (manifest, body, trailer), enforces `(processInstanceId, streamEpoch-or-null)`, hashes exact UTF-8 pre-trailer bytes, fail-softs disk errors, writes pending loss as `drop_notice` on close, and requires a new file on re-enable. Evidence: `tests/test_narrative_tape_writer.py`.
4. #240 writer slice: `NarrativeTapeWriter` owns a named cancellable `narrative_tape_writer` task. `submit()` only admits to the queue. Disk I/O, size rotation, stdlib gzip, `keep_files` retention and close live in the task / `aclose`. Shutdown waits at most `shutdown_flush_timeout_s`, then `drain_lost(tape_flush_timeout)` and never raises into the caller. Composition builds `TAPE_HEALTH_CHANGED(unavailable)` from the latch via `tape_health_command` in `src/irswitch/commentary/tape_safety.py`; the writer still does not import NarrativeRuntime or DetectorBank.
5. #240 is closed in its own scope: non-blocking submit, NDJSON identity, rotation/gzip/retention, fail-soft disk, bounded shutdown and composition-owned health-command helper. #242 owns reading/aggregating the funnel from a written tape.
6. Do not activate NarrativeRuntime. Do not start #241 unless the next owner claims it; #242 is the direct tape-reader successor.

## Resume commands

```bash
cd /home/richa/Dokumenty/ChatGPT/iROBSwitcher-story-flow-spec
pwd
git status --short --branch
git rev-parse HEAD
git rev-parse @{upstream}
```

Expected before resuming: correct worktree and branch, local HEAD/upstream relationship understood, #235–#238 closed, #239 open, and dirty files matching the ownership section. Any mismatch is a blocker until its ownership is understood.

## Known risks

- A pushed `codex/**` branch previously skipped CI; this checkpoint adds it to the CI trigger.
- Freeze builders were manual-only; this checkpoint adds an explicit CI job while branch-only artifacts exist.
- Local git hooks are intentionally not installed: linked worktrees share the repository hook directory and the current installer assumes `.git` is a directory. Installing it from this worktree would affect unrelated dirty branches. CI plus explicit `/qa` remains the safe gate until a separately reviewed worktree-aware hook policy exists.
- Multiple worktrees exist, so path verification is mandatory.
- Quota exhaustion does not automatically transfer ownership. Resume from this file plus the latest issue diary.
- Mailbox foundation alone is not live actor acceptance: actor reduction still owns reducer-sequence replay equivalence, shutdown terminal-callback handling and health/tape counter effects in #284.
- The two independent audit agents exhausted their own quota after the lifecycle checkpoint. Continuity remained intact through this handover, the existing issue diary, local TDD evidence and reproducible machine builders; rerun independent review when capacity returns, but do not discard the verified working state.
- The packaged `config-contract.json` and `detector-catalog.json` are runtime validation inputs and must remain byte-semantic JSON equivalents of their branch-only frozen machine sources; the focused test enforces this until the final-PR generation/copy path is formalized.
