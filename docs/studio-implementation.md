# Studio: first implementation slice

Historical shell base: local master `a381307`, branch `feat/studio-shell`.
Work item: [#366](https://github.com/Buchtanen/ir-obs-switcher/issues/366).

## Shared integration workflow — 2026-09-27

At the user's explicit request, all Studio stages accumulate on
`feat/studio-integration`, created from `254d3d4` with the shell and settings
ancestry intact. This supersedes the stacked shell/settings PR workflow.

Future stage branches start from this integration branch and target it in their
PRs. After independent verifier GREEN and handover, merging stage PRs into
`feat/studio-integration` is authorized by the user. Keep the integration branch
as the shared source for the next stage.

One cumulative [draft PR #371](https://github.com/Buchtanen/ir-obs-switcher/pull/371)
to `master` replaces the closed shell PR #367 and settings PR #369. The stage plan
is tracked in [integration issue #370](https://github.com/Buchtanen/ir-obs-switcher/issues/370).
Merge to `master` requires the user's final
explicit approval. The evidence below remains the historical shell verification;
later stages retain their own acceptance criteria and evidence.

## Acceptance criteria

- [x] `/studio` redirects to `/studio/`; the packaged React shell loads there.
- [x] Hash navigation supports direct links and preserves existing dashboards.
- [x] Overview and diagnostics read existing admin APIs without writes to the engine.
- [x] Failed requests mark retained data stale; OBS/iRacing never appear connected without evidence.
- [x] Polling is single-flight, bounded by timeouts, and cleaned up on unmount.
- [x] Future editor modules clearly describe their unavailable capabilities.
- [x] Wheel includes the built shell; frozen-path handling reuses the existing web root.
- [x] Tests, type check, production build and dependency audit pass.

## Test plan

HTTP integration: redirect, HTML/assets, no directory listing, old routes, frozen paths.
Browser: navigation, real and failed responses, stale data, script-shaped activity text,
keyboard navigation and narrow layout. Browser responses may be controlled fixtures;
such evidence is not evidence of an OBS/iRacing integration.
Package: build wheel and inspect included Studio resources.

## Decisions

The implementation follows the proposed React/TypeScript/Vite direction. Runtime
dependencies: React and React DOM only. Build dependencies: Vite, TypeScript and
React type declarations. Versions are pinned and the resolved graph is locked.
No graph library is introduced in this first slice. Dependency audit is required
before completion. The user explicitly approved React + TypeScript + Vite on
2026-09-27. These additions implement the plan requested by the user.

Built frontend resources are versioned in `src/irswitch/web/studio/` so the existing
Python and EXE build paths work without requiring Node on the operator's computer.
CI rebuilds and checks for drift. Hash routing avoids an application-wide fallback.

The first slice is read-only. Existing controls remain reachable through explicit
links; no iframe migration or invented event/episode data. Native migrations and
the catalog graph follow as separate slices.

## Documentation and configuration impact

README: Studio URL and scope. API: additive static paths and unchanged REST/WS.
BUILD_AND_DEPLOY: frontend build, checked-in assets and wheel packaging.
CI: `docs/dokumentace/domeny/testy-ci.md` records frontend checks and asset drift.
Config: no keys/defaults/INI writer changes. No database migration; `CONFIG.md`
and `config/config.example.ini` need no change.
Release: no versioning, tag or release-process change; `RELEASE_POLICY.md` needs
no change. Cursor rules/skills/agents are unchanged; `.cursor/README.md` needs no change.

## Verification evidence

- RED: original HTTP tests failed on `/studio` 404 and missing module; polling tests failed on missing adapter.
- GREEN: 13 Python tests (Studio + admin API/health); five polling/validation tests; TypeScript build.
- Ruff, Black and isolated mypy passed. `pnpm audit` reported no known vulnerabilities, including build dependencies.
- Chrome headless: real local API and absent switcher runtime, hash navigation/reload,
  keyboard skip preserving route, fixture API, script-shaped message escaped as text,
  HTTP 503 stale state with retained data, 390px layout without page overflow, no page errors.
- `pip wheel --no-cache-dir --no-deps --wheel-dir dist .` succeeded; ZIP inspection
  confirmed Studio HTML and both hashed assets. Frozen web root has a regression test.
- Independent verifier: GREEN. EXE execution and real OBS/iRacing integrations were not run;
  existing PyInstaller `--collect-all irswitch` packaging is unchanged and uses the packaged resources.

## Development diary — 2026-09-27

- Inventoried admin status/activity, old dashboards and packaging contracts.
- Created isolated local clone to preserve the user's untracked files and master.
- GitHub MCP resolved publication access; issue #366 tracks the implementation.

## Status cards and defined paths followup

Work item: [#379](https://github.com/Buchtanen/ir-obs-switcher/issues/379), branch
`feat/studio-status-paths`. Compact overview cards display component LEDs with
`good`, `warn`, `bad`, `off` or `unknown` state from existing `/api/admin/status`
facts. Stale readings never appear green. Event-engine flags describe configuration,
not inferred runtime activity. Existing endpoints and configuration stay unchanged.

Scenario path behavior is documented in [studio-authoring.md](studio-authoring.md#defined-path-navigation--issue-379).
Verification evidence for this followup:

- Independent verifier GREEN; 28 frontend tests, typecheck, production build and diff check PASS; three `tests/test_studio.py` tests PASS.
- CUA browser against actual Vite/admin verified click/Enter/Space selection, search preserving a selected path (six nodes/seven edges), pursuit graph (eight nodes/twelve edges), story-filter selection reset and zoom retained across polling.
- Node drag did not select a node; a subsequent click and layout reset worked.
- Controlled fresh→503 stale→recovery responses made all seven components unknown with no green LEDs while retained facts were labelled last known. Literal `__proto__` input was safe.
- Rebuilt EXE package smoke PASS (`build/studio-package-id3p9ats`): current assets, legacy routes and three isolated starts covering next-startup activation/rollback.

Active in-app browser verification at 390px passed for overview and scenarios without horizontal page overflow. A followup CSS correction wraps graph controls onto separate rows while keeping button text intact. The hidden-preview viewport limitation was resolved by testing the active panel; viewport override was reset afterwards. The configured service also displayed the new overview and selected path correctly. No master merge is claimed.

## iRacing UI process status followup

Branch `feat/studio-iracing-ui-status`: additive optional `iracingUi.running`
in `GET /api/admin/status`. Exact case-insensitive `iRacingUI.exe` process lookup
runs read-only in a worker thread. `false` means not found, `null` probe unavailable;
absent field remains unknown for older servers. UI process presence does not equal
SDK session connectivity and never changes switcher health or behavior.

Studio header and overview share one priority: fresh SDK connected → green;
fresh UI running without SDK → amber „iRacing UI / Čeká na session“; stale →
unknown, never green; unavailable probe never claims UI running. No config key,
default, dependency or migration change.

Verification for this addition: independent source verifier GREEN; 25 targeted
Python tests and 29 frontend tests passed, with typecheck, production build,
mypy, Ruff and Black passing. Rebuilt EXE
`dist/studio-iracing-ui/irswitchd.exe` passed `qa_studio_package.py` in
`build/studio-package-v1z179jg`. The configured service was updated without
changing the configuration SHA. Its API reported UI running and SDK disconnected;
the served Studio browser showed matching amber card/header and waiting copy.
The transition into a physical simulator session has not been exercised, so
SDK-connected green remains verified by tests rather than live iRacing.

## Companion readiness and branding followup — #383

Branch `feat/studio-companion-readiness` adds graphical Studio branding/favicon
from `/assets/favicon/favicon-96x96.png` and six configurable companion readiness
preferences. A single worker-thread read-only process-name scan supplies optional
`companionApps` status rows to the existing admin response. `[companion_apps]`
defaults all six `required=true`; settings use the existing FieldSpec writer and
live application. Missing required process warns, missing optional is neutral,
no required apps is neutral; stale/unknown never green. Process presence is not
device/functional readiness. There is no app launch/kill, SDK, health, scene,
commentary or overlay control change.

Verification: independent source and QA-script verifier GREEN; 65 targeted Python
tests and 31 frontend tests passed, plus typecheck, production build, Ruff, Black
and mypy on seven files. Rebuilt EXE passed `qa_studio_package.py` in
`build/studio-package-wpfoo4c6`; the QA compares favicon bytes exactly and the
served assets/logo match packaged bytes. Its raw-HTML check reads bytes so Windows
CRLF normalization is not mistaken for an asset failure.

Disposable-config browser QA changed DRE to optional via native checkbox, saved
through Settings and immediately showed five required apps in the summary; the
preference persisted. The updated running service loaded the branding and
detected the six process statuses. Configuration SHA stayed unchanged during
the live read check. This verifies process presence/reporting and UI preference
behavior only, not companion device function or VR connection. A separate preview
was stopped after QA. Remote CI/PR status belongs to the task diary.

## Whole-PC telemetry clocks followup — #385

Branch `feat/studio-telemetry-clocks` adds CPU/GPU two-row table in Studio
Overview, with load (%), temperature (°C) and clock (CPU GHz, GPU MHz) columns.
The existing bus provider supplies nullable `cpuFrequencyGHz` and `gpuClockMHz`
in `extensions.sysinfo.detail`; unavailable values render „—“. Last known numbers
remain labelled on stale responses and the status becomes unknown. This describes
whole-PC telemetry, not isolated iRacing process metrics. No new polling,
configuration, dependency or overlay behavior is introduced.

Verification: backend TDD red→green; 15 targeted Python tests and independent
26 Python tests passed. Parent reports 31 frontend tests, typecheck, build,
Ruff, Black, mypy and diff check GREEN; independent source verifier GREEN.
Rebuilt EXE `dist/studio-clocks/irswitchd.exe` passed package QA in
`build/studio-package-jhyui5iu`. The updated live service served exact assets
with the configured INI SHA unchanged. Browser on the live Overview displayed
CPU/GPU rows with %, °C, GHz and MHz from available telemetry. A disposable
empty-provider view rendered „—“ values; after stopping that preview, stale
state became unknown with a last-known caption. At 390 px, the empty table had
two rows, fit within its card and caused no horizontal overflow.

TDD exception for the frontend: the change was pure visual wiring, so no
frontend RED test was added; browser checks of rows, units, unknown/stale states
and the 390 px empty layout served as the alternative verification. The material
risks were clipping and wrong units; API unit tests and browser inspection cover
those paths. A numeric live-telemetry 390 px check was interrupted by a tab
viewport tool timeout and is **not** claimed. The original viewport was restored.
No application code changed after review.

## Subsequent slices

1. Native FieldSpec settings with validation, live/restart and unsaved changes:
   implementation tracked in [studio-settings.md](studio-settings.md) on
   historical branch `feat/studio-settings`; now included in
   `feat/studio-integration`.
2. Native OBS controls and commentary, preserving existing action semantics.
3. Read-only catalog graph and context editing of supported fields.
4. Episode projection and lineage-backed timeline, after provider audit.
5. Versioned definition drafts and isolated replay under a new domain contract.
