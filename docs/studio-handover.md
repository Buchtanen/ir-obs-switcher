# Studio P3–P6 completion checkpoint — 2026-09-27

- Checkout: `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`; independent clone; remote `https://github.com/Buchtanen/ir-obs-switcher.git`.
- Branch `feat/studio-authoring`; target `feat/studio-integration`; cumulative PR #371 to master remains unmerged.
- Current issue #373; diary https://github.com/Buchtanen/ir-obs-switcher/issues/373#issuecomment-5851927305. Umbrella #370; diary https://github.com/Buchtanen/ir-obs-switcher/issues/370#issuecomment-5851826827.
- Last pushed implementation/base SHA `eae70716ac94d62937fa07e3a872e7d974ef0255` (P2 integration merge PR #374, implementation `76ea0f7`). Current checkpoint SHA will be recorded in the same issue diary immediately after push.
- Dependency gates: user approved React/TypeScript/Vite; new stories with validated links, current-run bounded history, activation next startup. No further application dependencies added. PyInstaller is the existing packaging tool installed only in this isolated venv.
- TDD GREEN; independent verifier SOURCE GREEN including final replay highlight/comparison. Relevant 242 Python regressions, subsequent 20 Studio delta tests and final 6 HTTP tests; 20 frontend tests, typecheck/build, all 11 freeze artifact builders, Ruff/Black/diff checks. Later checks overlap earlier ones; counts must not be summed as unique tests.
- Browser: all three Chrome suites PASS; authoring uses a real disposable revision store and checks malformed drafts, conflicts, undo/redo, navigation, save/select, graph, run isolation, timeline reset/highlight, pinned deterministic comparison and narrow layout. Settings/operations writes use fixtures.
- Final package smoke PASS for EXE (`build/studio-package-woboz3m4`) and wheel (`build/studio-package-a7l9dkkl`): three isolated service starts, unchanged INI, current asset/legacy routes, custom story save and pending selection, startup activation and next-startup rollback, custom isolated replay. Wheel checks exact asset filenames/bytes; clean stale `build/lib/irswitch/web/studio` before incremental packaging. Final assets `index-3ptC8BvU.js`, `index-CNCWPKvB.css`.
- Scope: catalog/graph/layout/context FieldSpec links; actual current-run episode transitions with identities and evidence; immutable bounded revisions/validation/atomic conflict-safe persistence; startup-only effective catalog composition; 17 deterministic isolated replay fixtures, timeline and pinned comparison; bounded WS reconnect/invalidation.
- No unresolved source/package blocker. Physical OBS/TTS/OAuth effects were not exercised. Legacy routes intentionally retained; no retirement or production deployment claim. New stories compose supported certified beats/edges, not arbitrary code/guards.
- Isolated current-source preview http://127.0.0.1:17329/studio/ uses `build/studio-preview-revisions.json`, no live runtime/config. QA preview 17330 uses separate `build/studio-qa-revisions.json`. Both are local evidence only. Production port17321 untouched.
- Next exact action: commit/push this verified stage, create stage PR to integration with semver:minor, merge under user's explicit integration authorization, fast-forward local integration, update cumulative PR371 and issue diaries with immutable SHA/PR. Close completed stage/implementation issues. Do not merge master.
- Parent checkout remains `feat/remote-commentary-microplan`, user recordings untouched. Ignored build/dist/.venv/.pytest-studio* are local generated evidence. Current owned changes are listed below and committed as one checkpoint; this handover is parent-owned.

## Owned files at checkpoint

- `API.md` — docs-keeper
- `CONFIG.md` — docs-keeper
- `README.md` — docs-keeper
- `docs/dokumentace/README.md` — docs-keeper
- `docs/dokumentace/inflight/README.md` — docs-keeper
- `docs/event_graph_editor_spec.md` — docs-keeper
- `docs/studio-parity.md` — docs-keeper
- `docs/studio-roadmap.md` — docs-keeper
- `docs/v2.0.0/machine/catalog-loader-contract.json` — docs-keeper
- `frontend/studio/src/Operations.tsx` — parent
- `frontend/studio/src/Settings.tsx` — parent
- `frontend/studio/src/main.tsx` — parent
- `frontend/studio/src/poll.ts` — parent
- `src/irswitch/contracts/resources.py` — parent
- `src/irswitch/contracts/schemas/v2/catalog-loader-contract.json` — parent
- `src/irswitch/events/beat_plan.py` — parent
- `src/irswitch/events/episode_registry.py` — parent
- `src/irswitch/events/episode_retention.py` — parent
- `src/irswitch/events/narrative_runtime.py` — parent
- `src/irswitch/events/opportunity_queue.py` — parent
- `src/irswitch/events/prompt_compiler.py` — parent
- `src/irswitch/main.py` — parent
- `src/irswitch/server/studio.py` — parent
- `src/irswitch/web/studio/assets/index-BtotO0aW.js` — parent
- `src/irswitch/web/studio/assets/index-CEcw_-L8.css` — parent
- `src/irswitch/web/studio/index.html` — parent
- `docs/studio-authoring.md` — docs-keeper
- `docs/studio-definitions.md` — docs-keeper
- `frontend/studio/qa/authoring-browser.cjs` — parent
- `frontend/studio/src/Catalog.tsx` — parent
- `frontend/studio/src/Definitions.tsx` — parent
- `frontend/studio/src/Replay.tsx` — parent
- `frontend/studio/src/catalog.css` — parent
- `frontend/studio/src/socket.test.ts` — parent
- `frontend/studio/src/socket.ts` — parent
- `scripts/qa_studio_package.py` — parent
- `src/irswitch/contracts/runtime_catalog.py` — parent
- `src/irswitch/contracts/schemas/v2/studio-narrative-replay.json` — parent
- `src/irswitch/contracts/schemas/v2/studio-replay-scenarios.json` — parent
- `src/irswitch/contracts/studio_definitions.py` — parent
- `src/irswitch/events/studio_story_projection.py` — parent
- `src/irswitch/server/studio_authoring.py` — parent
- `src/irswitch/server/studio_data.py` — parent
- `src/irswitch/server/studio_replay.py` — parent
- `src/irswitch/web/studio/assets/index-3ptC8BvU.js` — parent
- `src/irswitch/web/studio/assets/index-CNCWPKvB.css` — parent
- `tests/test_studio_authoring_http.py` — parent
- `tests/test_studio_catalog.py` — parent
- `tests/test_studio_definitions.py` — parent

## Earlier checkpoints

# Studio P2 operations checkpoint — 2026-09-27

- Checkout: `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`; remote `https://github.com/Buchtanen/ir-obs-switcher.git`.
- Branch: `feat/studio-operations`, base and PR target `feat/studio-integration`.
- Issue: #372; diary https://github.com/Buchtanen/ir-obs-switcher/issues/372#issuecomment-5851851153; umbrella #370, cumulative draft PR #371.
- Last pushed base SHA: `77421ca64d3dce4ecd6543263850579a0ff54a95`. Implementation SHA follows in issue diary after commit/push.
- TDD GREEN: frontend18 tests/build/typecheck; independent verifier72 backend API/OAuth/logging/overlay/narrative/Studio tests. Chrome fixture-only operations QA PASS including stale retained states, shared lock, acknowledgement, cancellations and mobile layout.
- Verifier findings corrected: renderer selector honestly labels server-config default; stale OBS data unknown/actions disabled; stale decisions block server speech; docs aligned including inflight path map. Independent verifier GREEN with external integration limitations.
- Working tree: parent-owned frontend Operations/api/css/tests/example, QA, main and generated Studio assets; docs-keeper-owned README/API, operations/parity/roadmap/inflight index; parent handover. These changes are checkpointed together; no user files absorbed. Ignored build/.venv/.pytest-studio* are local evidence.
- No production OBS/TTS/lifecycle writes. Isolated preview port17329 has no runtime/config; actual devices and EXE execution remain P6 checks. Existing URLs preserved.
- Next: push this checkpoint, PR to integration and merge under explicit user authorization; then branch `feat/studio-authoring` for P3–P6. See studio-roadmap.md. New stories+validatable links; bounded current-run episode history; activation only next service startup. No new dependencies.
- Do not merge cumulative PR371 into master without separate user request.

## Earlier checkpoint

# Studio recovery checkpoint — integration, 2026-09-27

- Checkout: `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work` (independent clone).
- Branch/upstream: `feat/studio-integration` / `origin/feat/studio-integration`.
- Remote: `https://github.com/Buchtanen/ir-obs-switcher.git`.
- Integration starting point: settings checkpoint `254d3d4b39b5058d4ab91b658e72d3a56890969a`,
  which already contains shell checkpoint `189ca5c15f1c1c1184e8e7de1c52acdc3559bd3e`.
- Integration issue: [#370](https://github.com/Buchtanen/ir-obs-switcher/issues/370).
- Integration diary: [2026-09-27](https://github.com/Buchtanen/ir-obs-switcher/issues/370#issuecomment-5851826827).
- Settings stage: [#368](https://github.com/Buchtanen/ir-obs-switcher/issues/368).
- Cumulative draft: [PR #371](https://github.com/Buchtanen/ir-obs-switcher/pull/371).
- User instruction on 2026-09-27 supersedes the previous stacked PR policy: all Studio stages
  accumulate in `feat/studio-integration`. Historical PRs #367 and #369 are superseded by
  cumulative draft PR #371 from this integration branch to `master`. Both historical
  PRs have been closed without merging to master; their stage commits remain intact.
- Future stage branches start from integration and target integration. After verifier GREEN,
  merge completed stage work into integration under this explicit user authorization.
  Do not merge the integration branch to `master` without a separate explicit user request.
- Last pushed implementation/evidence SHA: `b6ab66ec539d438622d38678b7bdf26e9ffe3b31`.
- Published integration-policy checkpoint: `15dbd76`; this follow-up records PR/issue links.
- TDD phase: GREEN; issue-steward, docs-keeper and independent verifier completed.
- Working tree at this checkpoint: this handover (parent-owned) and integration-policy updates
  to `docs/studio-implementation.md` and `docs/studio-settings.md` (docs-keeper-owned).
  Commit/push follows; implementation files remain identical to the settings checkpoint.
  Ignored `build/` contains browser screenshots and generated schema fixture; `.venv/`,
  `.pytest-studio*/`, `dist/` contain local verification outputs. No user edits were absorbed.
- Parent checkout remains on `feat/remote-commentary-microplan`; recordings are user-owned.
  `.studio-work/` and `.pnpm-store/` are local artifacts from the first Studio slice.

## Completed scope and evidence

Native `/studio/#/settings` uses existing FieldSpec GET and changed-only PUT with CSRF.
Sections/search, typed fields, optional inheritance, validation, change summary, confirmed revert,
dirty navigation retention and unload guard are implemented. Saving locks editing, displays server
live/restart lists and reads canonical values back. Errors preserve drafts. HTTP 400/500, timeout,
malformed acknowledgement or failed readback require explicit reread; only HTTP 403 guarantees
pre-write rejection. Reread updates untouched fields and preserves edits. No config polling.
No new dependencies, backend changes, schema changes or migrations.

- `pnpm test`: 15 passed; build/typecheck and full dependency audit passed.
- Rebuilding after commit produced no generated asset drift.
- Independent Python regression: 35 passed in overlay_config/config_reload/studio/admin_api/admin_health.
  Parent also ran overlay API coverage (30 tests in that selection).
- Real Python schema/default projection accepted: 76 fields with zero pristine changes.
- `frontend/studio/qa/settings-browser.cjs` passed on Chrome with controlled config fixtures:
  save/failed readback, HTTP 403/400, failed reread, reconciliation, initial unavailable/retry,
  filters, inheritance, revert, dirty retention, unload handler and 390px layout.
- Previous shell browser checks passed. Independent verifier GREEN; no outstanding defect.
- Production writes, real OBS/iRacing and EXE execution were not exercised.
- Port 17329 remains an isolated API preview without loaded runtime config; settings correctly
  show unavailable there unless a test fixture or configured preview supplies `/api/config`.
- Evidence and browser QA commands: `docs/studio-settings.md`.

## Next action

Continue on `feat/studio-integration`; keep one cumulative draft PR with `semver:minor`.
Historical stage PRs are retained as closed references, not separate delivery branches.
Next implementation slice: native OBS controls and commentary. Start with API/action inventory
and a separate issue. Preserve backend CSRF/locality, manual override, autoswitch and TTS semantics.
No new frontend scene-decision pipeline. Expected ownership: `frontend/studio/src/` plus tests/docs;
backend changes only where the existing public API requires them. Catalog graph and episode
timeline remain separate slices.

On resume verify cwd, branch, HEAD, upstream, dirty files and latest issue diary before editing.
GitHub MCP is connected. Git fetch/push needs current-host execution and a command-local
safe.directory exception for this sandbox-owned clone. No production service restart is required.

## Integration verification

TDD-exception: this checkpoint only changes Git organization and documentation.
Verified: shell and settings tips are ancestors of integration and the application/test/build tree
matches `254d3d4`. Independent verifier GREEN. Verify local/remote tip equality after this docs push.
The prior GREEN implementation evidence above remains applicable; no behavior changed.

