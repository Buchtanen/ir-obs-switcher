# Studio: native settings

Branch: `feat/studio-settings`, based on `feat/studio-shell` (PR #367).
The next PR targets `feat/studio-shell` until the shell merges, then `master`.
Work item: [#368](https://github.com/Buchtanen/ir-obs-switcher/issues/368).
Implementation complete; independent verifier GREEN.

## Acceptance criteria

- [x] `/studio/#/settings` loads existing `GET /api/config` once on demand, without polling.
- [x] Only nonsecret schema fields with editable `overlay` values appear; redacted switcher metadata stays hidden.
- [x] Bool, int, float, string and choice fields support validation, section filters and search; optional fields support inherited values.
- [x] A summary lists changed fields, with revert controls; Studio navigation preserves drafts and reload/external leave triggers a browser warning.
- [x] Saving sends only changed values through `PUT /api/config` with `X-Requested-With: irswitch`; edits are disabled during saving.
- [x] The result displays server `applied_live` and `needs_restart` lists and reads back canonical server values.
- [x] Errors retain the draft. Timeout or uncertain save outcome blocks repeat saving until an explicit reread reconciles server state.
- [x] Tests, typecheck, build, dependency audit and independent verification pass.

## Test plan

- Unit: schema filtering, typed/optional inputs, changed-only payloads, validation and secret exclusion.
- Component/browser: section/search controls, draft survival across hash navigation, revert, leave warning, saving lock, live/restart feedback and canonical reread.
- Failure paths: rejected writes, failed reads and timeout/uncertain writes retain drafts and block unsafe repeat attempts until reread.
- Regression: existing Studio overview/diagnostics and legacy settings stay reachable.
- Build: run the frontend checks in [BUILD_AND_DEPLOY.md](../BUILD_AND_DEPLOY.md#studio-frontend); commit regenerated assets and verify drift checks.

Controlled API fixtures prove frontend behavior, not live OBS/iRacing integration.

## Evidence — 2026-09-27

- RED: new settings test file failed because the model module did not exist.
- GREEN: `pnpm test` 15 passed; `pnpm build` (TypeScript + Vite) and `pnpm audit` passed.
- Independent Python regression: 35 passed across overlay config, config reload, Studio, admin API/health.
  Parent also ran overlay API coverage with Studio/config/reload (30 passed in that selection).
- Real Python `schema_as_dicts()` and `overlay_values(OverlaySettings())` accepted by the frontend:
  76 fields, no spurious pristine changes.
- `qa/settings-browser.cjs`: passed on Chrome headless with controlled GET/PUT fixtures;
  initial failure/retry, validation, search/sections, inherited values, changed-only payload and CSRF,
  saving lock, live/restart result, failed readback, HTTP 403 rejection, uncertain HTTP 400,
  draft reconciliation, revert/cancel, beforeunload registration and 390px layout.
- Previous shell browser regression passed; no page errors. Screenshots visually inspected.
- HTTP 400 is intentionally uncertain: existing backend can fail while rereading after a write.
  Only HTTP 403 is a confirmed pre-write rejection. No automatic write retries.
- Pending restart keys remain visible during the mounted Studio session. They are not a durable
  server restart ledger, and the UI does not claim that a later process restart has been observed.
- Backend/config/package contracts are unchanged. Real production writes, EXE execution and
  OBS/iRacing integrations were not exercised.

### Optional browser QA

Start an isolated server serving the built shell. The QA intercepts every `/api/config`
request and does not modify the server's configuration. An existing Playwright runtime
and Chrome are supplied externally; no test dependency is added to the package:

```powershell
$env:STUDIO_PLAYWRIGHT_MODULE = '<absolute path to installed playwright>'
$env:STUDIO_CHROME_PATH = '<absolute path to chrome.exe>'
$env:STUDIO_BASE_URL = 'http://127.0.0.1:17329'
node frontend/studio/qa/settings-browser.cjs
```

## Documentation and configuration impact

Updated `README.md`, `API.md` and [studio-implementation.md](studio-implementation.md).
No new dependencies, backend endpoints, schema keys, defaults or INI migrations.
`CONFIG.md` and `config/config.example.ini`: no change because the editor exposes
the existing supported configuration contract. Build/CI and release policies remain
unchanged, so their documentation needs no update. Cursor rules/skills/agents remain unchanged.

## Scope

This slice edits existing overlay configuration fields. OBS/switcher secrets and
native switcher controls remain outside its schema-driven editor. Further Studio
modules follow the original implementation roadmap.
