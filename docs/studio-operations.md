# Studio: native operations

Branch: `feat/studio-operations`, contributing to `feat/studio-integration`.
Scope: P2 OBS controls, commentary tests, overlay previews and service diagnostics.
P2 frontend/API evidence is recorded below; real integrations and final P6 gates
remain open. Existing pages remain available.

## Current contract

`Operations.tsx` activates reads for the selected module through shared polling
with stale notices and cleanup. OBS reads `/status` and `/oauth/status`;
diagnostics reads `/status`, `/health`, `/metrics`, `/logging/level`; commentary
reads `/api/commentary/runtime` and `/api/commentary/runtime/decisions?limit=50`;
overlay reads `/api/overlay/snapshot` and `/api/overlay/debug/events`.
Raw JSON details expose complete responses alongside selected summaries.

Writes reuse existing API endpoints. POSTs send JSON and
`X-Requested-With: irswitch`, with an 8s timeout and one shared in-flight lock.
Any action error blocks further writes. Explicit reread displays actual state,
then asks the operator to acknowledge that the previous result may remain
unknown before allowing a new manual action. There is no automatic write retry.
Successful HTTP responses display the returned payload and refresh reads; they
do not prove that a lifecycle transition or accepted TTS request completed.

OBS supports autoswitch, RESTART reset, stream metadata reinit and manual override
with nonempty scene and positive integer seconds. OAuth preparation accepts only
an HTTPS `accounts.google.com` authorization URL and exposes an explicit link.
Diagnostics confirms config reload, reset, restart and shutdown before writing.
Runtime logging toggles DEBUG/INFO. Existing VR and golden outputs remain links.

Commentary keeps server manual TTS EN-only under `commentary-runtime/2`, trims
and normalizes text and limits it to 400 characters. Server TTS requires an
explicit confirmation. Browser EN/CS language, voice/rate/stop are local controls. Offline
validation uses editable JSON bindings and a clearly labelled example; it neither
reads live bindings nor starts speech.

Overlay controls embed the clean renderer output, rather than a legacy admin
page. Demo is client rendering, not engine replay. The renderer selector offers explicit V4 or the service configuration default, which may also be V4; it cannot force V3. The scaled preview includes the demo cue. Theme/renderer controls and
reload apply to demo; live preview retains `/overlay/`. Debug injection confirms
publication to the shared live overlay output; it is not isolated simulation.

## Acceptance and test plan

- [ ] Validate all endpoint/body/header contracts and malformed-response paths.
- [ ] Verify no parallel writes or retries after timeout; reread/acknowledgement remains explicit and does not claim certainty.
- [ ] Verify status, metrics and metadata parity against [studio-parity.md](studio-parity.md), including unavailable and stale providers.
- [ ] Verify cancellation/cleanup and expected offline state after restart/shutdown.
- [ ] Verify OAuth host validation, authorization and bounded read behavior.
- [ ] Verify browser/server speech separation, EN server restriction, validation fixture labelling and accepted/refused responses.
- [ ] Verify demo versus live injection separation and preview controls.
- [ ] Resolve or explicitly preserve each source-audit gap in the parity inventory.
- [ ] Run frontend tests/build/audit and relevant Python/API regressions; collect independent verifier evidence.

Use controlled fixtures for lifecycle/audio writes in browser QA. Such fixtures
do not prove real OBS/TTS execution, OAuth completion or packaged EXE behavior.

## Evidence — 2026-09-27

- Frontend: 18 tests and production build passed.
- Chrome fixture QA `operations-browser.cjs`: PASS for override validation/payload,
  shared action lock across navigation, confirmation cancellation, uncertain-result
  reread/acknowledgement, browser CS option, offline binding payload, TTS/debug gating
  and 390px layout without page errors. Operational writes were intercepted.
- Independent verifier: 72 Python API/OAuth/logging/overlay/narrative/Studio tests passed.
- Previous source gaps for CS selection, switcher events, demo cue and reset safe-scene
  warning are resolved in source. Preview scales the 1920×1080 renderer.

These results do not prove real audio/OBS execution, OAuth completion, EXE behavior,
all legacy notifications or P6 retirement. Complete responses remain readable in JSON
with freshness notices; legacy routes remain available.
## Docs/config impact

This inventory and `studio-parity.md` record scope and gaps. User-facing README/API
updates describe the operational contract. No new dependencies, config
keys/defaults, backend endpoints or migration are introduced by this source slice;
`CONFIG.md` and the example INI need no change for these existing actions.
