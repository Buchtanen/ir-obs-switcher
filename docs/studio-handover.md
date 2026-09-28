# System telemetry clock rows — 2026-09-28 (#385)

- Checkout `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`, branch `feat/studio-telemetry-clocks`, remote `https://github.com/Buchtanen/ir-obs-switcher.git`, target `feat/studio-integration`. Last pushed base/recovery `46f9669d69b93351bb453741bc708b560bc5ba79`. User authorizes accumulated integration, not master merge; cumulative #371 stays draft.
- Issue [#385](https://github.com/Buchtanen/ir-obs-switcher/issues/385); [same-day diary](https://github.com/Buchtanen/ir-obs-switcher/issues/385#issuecomment-5862652182). Immutable implementation/merge SHAs follow there.
- User asks exactly CPU and GPU rows with utilization, temperature, clock columns. Added nullable admin sysinfo detail cpuFrequencyGHz and gpuClockMHz from existing sampled bus state; no extra polling/dependency/config or HUD changes. Card caption identifies whole-PC readings; missing/nonfinite numeric cells show em dash and stale card identifies last-known values.
- TDD RED then GREEN on API projection/units/missing values; parent15Python/31frontend PASS, typecheck/build/Ruff/Black/mypy/diff PASS; independent verifier26Python/typecheck/diff GREEN. TDD-exception: frontend pure visual wiring. Alternative verification: browser rows/units/missing/stale and narrow layout. Risk: wrong units or clipped cells; mitigated with API unit tests and browser inspection.
- Package smoke `scripts/qa_studio_package.py dist/studio-clocks/irswitchd.exe` PASS, artifact `build/studio-package-jhyui5iu`. After GREEN, verified inactive simulator/stream and replaced only previous known service with this EXE. Original cwd/config retained, SHA unchanged; served Studio assets match source bytes.
- Browser: disposable absent-provider shows two rows with em dashes; stopped preview yields unknown indicator and last-known caption. At390px empty-value table fits311px within345px card with no page overflow. Actual configured service displays numerical percentage/temperature/CPU GHz/GPU MHz in correct columns. A subsequent live numeric390px attempt timed out in viewport tooling, so no claim for that separate attempt; original viewport restored and user's current overview refreshed. Preview stopped. Live service preserved.
- Parent owns source/tests/generated assets/this checkpoint; docs-keeper owns API.md and implementation doc. No user files or primary checkout edits. No known source blockers.
- Next: commit/push checkpoint; stage PR with semver:minor to integration; full CI gate; authorized merge and local fast-forward; update same issue diary and cumulative draft #371. Keep umbrella #370 open for physical-provider acceptance. Do not merge master.

## Owned files at checkpoint

- `API.md`
- `docs/studio-implementation.md`
- `frontend/studio/src/StatusBoard.tsx`
- `frontend/studio/src/status-board.css`
- `src/irswitch/server/admin.py`
- `src/irswitch/web/studio/assets/index-CrRi0psi.js`
- `src/irswitch/web/studio/assets/index-LvFUX6ze.css`
- `src/irswitch/web/studio/index.html`
- `tests/test_admin_api.py`
- `.pytest-telemetry-verifier/`
- `src/irswitch/web/studio/assets/index-BNF20SJF.js`
- `src/irswitch/web/studio/assets/index-DLFLpj9J.css`
- `docs/studio-handover.md`

# Companion applications and graphical branding — 2026-09-28 (#383)

- Checkout `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`, branch `feat/studio-companion-readiness`, remote `https://github.com/Buchtanen/ir-obs-switcher.git`; integration target `feat/studio-integration`. Last pushed base/recovery SHA `0eab1da617f3cde1de271347ce79153fde032958`. User authorizes integration of stages; cumulative draft #371 remains unmerged to master.
- Issue [#383](https://github.com/Buchtanen/ir-obs-switcher/issues/383), [same-day diary](https://github.com/Buchtanen/ir-obs-switcher/issues/383#issuecomment-5862354474). Final immutable implementation/merge SHAs follow in that diary.
- Existing graphical favicon is now used for Studio branding and explicit page icon. One off-loop process scan detects iRacing UI and six exact companion main executables. No process inventory/path/PID is exposed. User confirmed MAIRA executable and individual optionality. Companion presence is advisory, never a device/connection/functionality guarantee or a change to switcher health/control.
- Six live FieldSpec booleans in `[companion_apps]` control required status (default true for the requested prerequisites); persisted through existing config API, stored separately from overlay settings in AppConfig. Missing optional applications do not degrade summary; stale/unknown/incomplete evidence never claims readiness. No required applications is neutral. Config absence requires no migration; configured INI remains unchanged until explicitly saved.
- TDD RED then GREEN; independent source and package-QA-delta verifier GREEN. Parent65 targeted Python tests,31 frontend tests, typecheck/build/Ruff/Black/mypy7files/diff PASS. Independent44Python/31frontend PASS. Logo uses a TDD exception for visual wiring, verified through browser load and exact packaged/served bytes.
- Package smoke `scripts/qa_studio_package.py dist/studio-companions/irswitchd.exe` PASS; evidence `build/studio-package-wpfoo4c6`. Corrected a CRLF-only false failure by comparing HTML bytes, and added favicon byte verification. Browser on disposable config confirms six process detections, graphic load, settings deep link, saved DRE optional and immediate five-required summary.
- Actual configured service replaced only after source/package GREEN and confirming inactive simulator/stream; new EXE `dist/studio-companions/irswitchd.exe`, original primary cwd/config. Health/API and browser confirm six detections plus loaded logo, all served Studio assets and logo match source bytes, config SHA unchanged. No companion launched/stopped; no physical device/VR connectivity tested. Disposable preview stopped, live Studio preserved. No HUD assets/cache change.
- Known limit: one-second scan budget is cooperative between OS process items. No new dependencies. Primary checkout/user recordings untouched. Parent owns implementation/tests/generated assets/QA script/this handover; docs-keeper owns API.md, CONFIG.md, example INI, implementation doc. Ignored test/package artifacts are not part of commit.
- Next: commit/push verified checkpoint, stage PR with semver:minor to integration, wait full CI, merge under standing authorization, fast-forward local integration, update same issue diary and cumulative draft #371. Keep broader acceptance issue #370 open; do not merge master.

## Owned files at checkpoint

- `API.md`
- `CONFIG.md`
- `config/config.example.ini`
- `docs/studio-implementation.md`
- `frontend/studio/index.html`
- `frontend/studio/src/Settings.tsx`
- `frontend/studio/src/StatusBoard.tsx`
- `frontend/studio/src/main.tsx`
- `frontend/studio/src/poll.test.ts`
- `frontend/studio/src/poll.ts`
- `frontend/studio/src/status-board.css`
- `frontend/studio/src/style.css`
- `frontend/studio/vite.config.ts`
- `scripts/qa_studio_package.py`
- `src/irswitch/config.py`
- `src/irswitch/config_reload.py`
- `src/irswitch/overlay/http.py`
- `src/irswitch/overlay/schema.py`
- `src/irswitch/server/admin.py`
- `src/irswitch/system/iracing_ui.py`
- `src/irswitch/web/studio/assets/index-DJb0sbO3.css`
- `src/irswitch/web/studio/assets/index-XDJJL3si.js`
- `src/irswitch/web/studio/index.html`
- `tests/test_iracing_ui_presence.py`
- `frontend/studio/src/companion-model.test.ts`
- `frontend/studio/src/companion-model.ts`
- `src/irswitch/system/companion_apps.py`
- `src/irswitch/web/studio/assets/index-CrRi0psi.js`
- `src/irswitch/web/studio/assets/index-LvFUX6ze.css`
- `tests/test_companion_apps.py`
- `docs/studio-handover.md`

# iRacing UI informational waiting status — 2026-09-28 (#381)

- Checkout `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`, branch `feat/studio-iracing-ui-status`, remote `https://github.com/Buchtanen/ir-obs-switcher.git`; target `feat/studio-integration`. Base/recovery SHA `cbb76d989bc2213e021e8359b60a55ed518b37a9`. User authorizes stage integration; cumulative draft PR #371 must remain unmerged to master.
- Issue [#381](https://github.com/Buchtanen/ir-obs-switcher/issues/381), [diary](https://github.com/Buchtanen/ir-obs-switcher/issues/381#issuecomment-5862191645). Final immutable implementation and merge SHAs follow in the diary.
- Exact `iRacingUI.exe` presence adds nullable `iracingUi.running` to admin status. Enumeration runs off the event loop, uses the existing optional psutil dependency and returns unknown on failure/incomplete readings. The one-second scan budget is cooperative between process items, not a hard OS-call timeout.
- Studio shows amber iRacing UI / waiting for simulator session only with fresh UI presence and explicitly disconnected SDK. Connected SDK remains green; stale/unknown SDK remains unknown. The launcher does not affect switcher health/decisions, commentary or overlays.
- TDD RED then GREEN; independent verifier GREEN. Targeted Python25PASS, frontend29PASS, typecheck/build/mypy/Ruff/Black/diff checks PASS. Physical simulator transition is covered by model tests but has not been exercised with a running simulator.
- EXE `dist/studio-iracing-ui/irswitchd.exe` and `scripts/qa_studio_package.py` PASS; evidence `build/studio-package-v1z179jg` (exact assets, legacy routes, disposable revisions/config and next-startup activation/rollback). Actual configured service updated after GREEN. Browser confirms amber indicator in header/card and waiting text; all three served Studio resources match source bytes, configuration SHA unchanged. No new dependency, config edit, overlay HUD change or simulator/OBS action.
- Parent owns detector/admin/frontend/tests/generated assets and this handover; docs-keeper owns API.md and docs/studio-implementation.md. Prior JS index-BCohWCp2 removed; new JS index-XDJJL3si, CSS index-DJb0sbO3 retained. Primary checkout/user recordings untouched.
- Next: commit/push checkpoint, stage PR to integration with semver:minor, wait full CI, merge under existing authorization, fast-forward local integration and update this issue diary plus cumulative PR #371. Keep umbrella #370 open for broader physical-provider acceptance. Preserve the configured service and live Studio tab.

# Final narrow-layout correction — 2026-09-27 (#379)

- Same checkout/branch/remote/issue below. Last pushed implementation `767b65da64be8cb508d7b571841cc53d9de1bb85`; stage PR [#380](https://github.com/Buchtanen/ir-obs-switcher/pull/380) to integration. Existing diary remains authoritative for final merge SHA.
- Active browser viewport test resolved the earlier hidden-tab limitation: 390px overview/scenarios have no horizontal page overflow. Found and corrected graph toolbar character wrapping with two CSS declarations (`flex-wrap:wrap`, `white-space:nowrap`). Verified readable34px-high buttons in multiple rows; reset viewport afterwards.
- Independent verifier GREEN for CSS delta; typecheck/build/diff checks PASS. No model/backend changes since28test GREEN. Full CI of767b65d already passed Python3.12/3.13 and all static/frontend/security checks; Python3.11 still running at this checkpoint.
- Parent owns this checkpoint: `frontend/studio/src/catalog.css`, regenerated `src/irswitch/web/studio/index.html` and JS/CSS assets, `docs/studio-implementation.md`, this handover. Generated final assets `index-BCohWCp2.js`, `index-DJb0sbO3.css`; priorCHnMR4l_/BPYzLOnB assets removed. Primary checkout/config untouched.
- Packaging: previously verified EXE behavior still applies; rebuilt `dist/studio-status-final/irswitchd.exe` includes the final toolbar CSS. Next: verify final asset bytes after single-instance service handoff from `dist/studio-status/irswitchd.exe`, push this CSS/evidence checkpoint, wait for relevant CI, authorized integration merge and update same #379 diary/PR#371. Do not merge master. Cleanup disposable Vite17329; preserve configured service17321.

# Studio status lights and complete defined paths — 2026-09-27 (#379)

- Checkout `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`, branch `feat/studio-status-paths`, remote `https://github.com/Buchtanen/ir-obs-switcher.git`; target `feat/studio-integration`. User authorized accumulating every stage there. Cumulative draft PR #371 remains unmerged to master.
- Issue [#379](https://github.com/Buchtanen/ir-obs-switcher/issues/379); [same-day diary](https://github.com/Buchtanen/ir-obs-switcher/issues/379#issuecomment-5857747334). Last pushed base/recovery SHA `561b744fd07acb4cd4375e7d0dc707392f52e821`; immutable implementation SHA follows in that diary after this checkpoint is pushed.
- Scope: denser overview with component facts and glowing status indicators, safe unknown/off/stale semantics, scenario predecessor/successor highlighting including all reachable branches, visible directional arrows, keyboard/list selection, fit graph/path and client-only drag layout. No backend/config/dependency changes. Catalog paths are possibilities, not evaluated guards or live execution.
- TDD GREEN. Independent verifier GREEN after repairing inherited-property lookups and adding regression coverage. `pnpm test`28PASS; typecheck/build/diff checks PASS; `pytest tests/test_studio.py -q --basetemp=.pytest-studio-status-379`3PASS. Backend full suite not repeated for this frontend delta; previous full CI evidence remains separately scoped.
- CUA browser checks: real API overview; graph click/Enter/Space, branch highlighting, search expands selected path, story filter clears selection, zoom retained across polling, dragging without selecting and subsequent click, reset layout. Long links route through default grid gaps. Controlled fresh/503/recovery status fixture confirms7unknown/0green on stale, retained values explicitly last-known, safe literal `__proto__` status/key. New mobile-size verification remains unperformed because hidden IAB viewport override did not apply; override reset.
- New EXE build + `scripts/qa_studio_package.py dist/studio-status/irswitchd.exe` PASS (`build/studio-package-id3p9ats`): exact current assets, legacy routes, disposable config/store, three isolated startups, selection/activation/rollback, custom replay. Final generated resources: `index-CHnMR4l_.js`, `index-BPYzLOnB.css`.
- After GREEN, replaced only the known previous service process with the verified `dist/studio-status/irswitchd.exe`, using existing primary configuration and working directory. Single-listener handoff checked; no config edits. Config SHA unchanged. Actual service health/API and live Studio show connected OBS, disconnected simulator, API running, version1.3.0; expected overall degraded while simulator absent. Served HTML references both new resource hashes. Live overview tab refreshed and confirmed new component cards/LEDs. No overlay HUD assets changed/cache bump needed.
- Parent owns frontend/generated assets/this handover; docs-keeper owns README and the other3 docs files. Only task-owned files below are dirty; ignored package/QA artifacts are not committed. Primary checkout and user recordings remain untouched.
- Next: commit/push this verified checkpoint, open stage PR to integration with exactly `semver:minor`, merge under existing authorization, fast-forward local integration, update same issue diary and cumulative PR #371 with final SHAs. Keep umbrella #370 open for remaining physical simulator/TTS/OAuth acceptance; do not merge master. Stop disposable preview/fixture processes after verification, preserve actual service.

## Files owned at this checkpoint

- `README.md`
- `docs/dokumentace/inflight/README.md`
- `docs/studio-authoring.md`
- `docs/studio-implementation.md`
- `frontend/studio/src/Catalog.tsx`
- `frontend/studio/src/StatusBoard.tsx`
- `frontend/studio/src/StoryGraph.tsx`
- `frontend/studio/src/catalog.css`
- `frontend/studio/src/graph-model.ts`
- `frontend/studio/src/graph-model.test.ts`
- `frontend/studio/src/main.tsx`
- `frontend/studio/src/poll.ts`
- `frontend/studio/src/status-board.css`
- `frontend/studio/src/status-model.ts`
- `frontend/studio/src/status-model.test.ts`
- `src/irswitch/web/studio/index.html`
- `src/irswitch/web/studio/assets/index-3ptC8BvU.js (deleted)`
- `src/irswitch/web/studio/assets/index-CNCWPKvB.css (deleted)`
- `src/irswitch/web/studio/assets/index-BPYzLOnB.css (generated)`
- `src/irswitch/web/studio/assets/index-CHnMR4l_.js (generated)`
- `docs/studio-handover.md`

# Configured-service Studio verification — 2026-09-27 (#377)

- Checkout/remote as below. Branch `feat/studio-live-integration`, base/target `feat/studio-integration`; last pushed implementation/recovery SHA `61759aea889518239c7002d04bdaa685e42645a0`. Cumulative PR #371 remains unmerged to master.
- Issue #377; diary https://github.com/Buchtanen/ir-obs-switcher/issues/377#issuecomment-5856375328. User authorized starting the real service and verifying the missing OBS state.
- Root cause: previous isolated `create_app()` preview had no switcher runtime; the configured service was not running. Started the verified integration executable with the existing configuration. No source/config edits, credentials changes, dependencies or overlay cache changes were required.
- Parent verified real OBS read access before startup, then native Studio overview on the running service origin: connected OBS, actual current scene and autoswitch state, correctly disconnected simulator. Streaming/recording were inactive; no test scene/audio/broadcast action was issued. User-facing live Studio tab remains open.
- Independent verifier scoped GREEN: two bounded health/admin/status samples agree, health timestamp advances, responses succeed with version1.3.0; served HTML/JS/CSS exactly match integration Git assets. App/source/assets diff against61759ae is empty. Browser evidence is from the actual configured service, not intercepted fixtures.
- Limitations: no running simulator session; no real TTS write, scene-switch action or completed external OAuth flow verified. Correctly displayed absence is not active-provider acceptance. Do not claim full physical integration from this OBS read gate.
- Docs-keeper owns README, docs/studio-operations.md, docs/studio-roadmap.md, docs/studio-parity.md; parent owns this handover. Only these5 docs files are dirty at checkpoint; no user files absorbed.
- TDD exception: operational startup + documentation only, verified with real provider reads/UI and unchanged application tree; earlier full2680test Python3.11/3.12/3.13 CI remains applicable.
- Next: commit/push docs evidence, stage PR to integration, authorized merge, update existing issue diaries with exact immutable SHA. Preserve current runtime; do not start a second service or isolated preview as a substitute. Full operator/simulator/audio acceptance requires the corresponding available providers and explicit test scope.

# Full-suite CI isolation correction — 2026-09-27

- Checkout/remote unchanged below; branch `feat/studio-ci-isolation`, PR target integration. Last pushed integration/recovery SHA `eff6944f30bfe910e5c1b3a4ccca1259566829e2`; issues #373/#370 reopened until full CI acceptance.
- Full authoring CI ran 2680 tests: 2677 passed, three failures outside the earlier targeted selection. Initialization test cancelled after fixed100ms before cold off-loop catalog initialization completed; absent-provider test inherited another test's global provider; helper import incorrectly assumed a `tests` namespace package.
- Fix changes tests only: wait for mocked HTTP site readiness with a bounded deadline and guaranteed cancellation; isolate the single-instance probe; explicitly monkeypatch the absent provider; use the configured pytest tests import path. Production modules/assets are unchanged from verified `8cb806f`.
- Owner parent: `tests/test_main.py`, `tests/test_studio_catalog.py`, this handover. Independent verifier GREEN with12/12 targeted tests, Ruff/Black/diff checks.
- Whole local suite now2678PASS; only two existing symlink-escape tests fail at setup with host WinError1314 (symlink privilege missing even outside sandbox). Those two passed in the preceding GitHub run. Do not weaken/skip them; final GitHub matrix is the acceptance gate.
- Next: push this test-only correction, PR to integration, wait for complete GitHub Python3.11/3.12/3.13 matrix, then merge and close the existing issues/diaries. Existing EXE/wheel/Chrome evidence remains valid because application and assets did not change. No additional package build needed.

# Final integration state — 2026-09-27

- Checkout `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work`, branch/upstream `feat/studio-integration` / `origin/feat/studio-integration`, remote `https://github.com/Buchtanen/ir-obs-switcher.git`.
- Last pushed implementation `8cb806f5ca8dba1bbe4be7e2230ca8f7f9b3cc52`; merged stage PR #375 into integration at `a9759dcce5b004e74d49e6b3783d77caed3711e2`. Integration tree equals the verified implementation tree.
- P0–P6 agreed implementation complete. Issues #373/#370 final immutable evidence is in their existing linked diaries below. Cumulative draft PR https://github.com/Buchtanen/ir-obs-switcher/pull/371 updated for complete scope; master remains unmerged.
- TDD GREEN, unchanged implementation after independent verification and final EXE/wheel/Chrome gates below. GitHub authoring CI additionally passed frontend, Ruff, Black, mypy, Bandit and Safety; full Python matrix was still running when this documentation checkpoint was written. Do not infer final CI completion from local GREEN.
- Working tree at checkpoint: only this parent-owned handover update; committed/pushed immediately. TDD exception: documentation-only final Git state; verified exact stage/integration tree equality and clean status before this edit. No new behavior or tests required.
- Next action is final cumulative PR review and explicitly authorized master merge/deployment, not another implementation stage. No physical OBS/TTS/OAuth execution or production service restart performed. Local preview at http://127.0.0.1:17329/studio/#/scenarios uses disposable definition storage and no runtime provider.
- Recovery: verify cwd, status, HEAD/upstream and latest #370 diary before editing. Preserve parent checkout/user recordings. Prior implementation checkpoint below lists every owned file and verification evidence.

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

