# Studio recovery checkpoint — integration, 2026-09-27

- Checkout: `C:/Users/richa/Projekty/ir-obs-switcher/.studio-work` (independent clone).
- Branch/upstream: `feat/studio-integration` / `origin/feat/studio-integration`.
- Remote: `https://github.com/Buchtanen/ir-obs-switcher.git`.
- Integration starting point: settings checkpoint `254d3d4b39b5058d4ab91b658e72d3a56890969a`,
  which already contains shell checkpoint `189ca5c15f1c1c1184e8e7de1c52acdc3559bd3e`.
- Issue: [#368](https://github.com/Buchtanen/ir-obs-switcher/issues/368).
- Diary: [2026-09-27](https://github.com/Buchtanen/ir-obs-switcher/issues/368#issuecomment-5851719685).
- User instruction on 2026-09-27 supersedes the previous stacked PR policy: all Studio stages
  accumulate in `feat/studio-integration`. Historical PRs #367 and #369 are superseded by
  one cumulative draft PR from this integration branch to `master`.
- Future stage branches start from integration and target integration. After verifier GREEN,
  merge completed stage work into integration under this explicit user authorization.
  Do not merge the integration branch to `master` without a separate explicit user request.
- Last pushed implementation/evidence SHA: `b6ab66ec539d438622d38678b7bdf26e9ffe3b31`.
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
Verify shell and settings tips are ancestors of integration, the application/test/build tree
matches `254d3d4`, and the remote integration tip matches the local tip after pushing.
The prior GREEN implementation evidence above remains applicable; no behavior changed.

