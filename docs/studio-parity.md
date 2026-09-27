# Studio legacy parity inventory

Source audit: 2026-09-27. This is the P0 acceptance inventory for P2 migration
and P6 retirement checks, not evidence that these functions are implemented in
Studio. All checks below remain open until a corresponding native UI test or
explicit compatibility decision is recorded.

Sources: `server/dashboards.py`, `web/admin/js/admin.js`, `web/config/index.html`,
`web/commentary/index.html`, `web/debug/index.html`, `web/demo/index.html`,
`web/overlay/golden.html`, `overlay/http.py` and `web/overlay/js/overlay.js` under
`src/irswitch/`. Original plan:
`C:/Users/richa/Documents/Codex/2026-09-27/kd/outputs/irswitch-studio-plan.md`.
Provider presence must be verified separately from endpoint presence.

## Operations evidence — 2026-09-27

P2 source now includes native OBS actions/OAuth, diagnostics metrics and GR events,
commentary browser EN/CS plus server EN speech, editable offline validation, scaled
clean overlay preview/demo cue and confirmed live injection. Reset confirms its
safe-scene effect. Full status responses remain in JSON with freshness notices.
The renderer selector offers explicit V4 or the service configuration default;
the latter may be V4 and does not force V3.

- [x] Fixture browser override validation and correct payload/header.
- [x] Shared action lock across navigation and confirmation cancellation.
- [x] Uncertain-result block, explicit reread and manual acknowledgement.
- [x] Browser CS selection and offline validation actor-binding payload.
- [x] Server TTS/live injection confirmation gating and 390px layout.

Evidence supplied by parent: 18 frontend tests/build; Chrome
`operations-browser.cjs` PASS; independent verifier 72 Python API/OAuth/logging/
overlay/narrative/Studio tests PASS. Writes were intercepted in browser QA.
Matrix rows below remain open where full parity or live/P6 evidence is not yet
recorded. Legacy routes remain available; no retirement claim is made.
See [studio-operations.md](studio-operations.md).
## Admin parity

| Source | Feature and existing read source | Studio target | Acceptance |
| --- | --- | --- | --- |
| `/admin` | Server health `ready`, blocking/warnings with reasons/tips; switcher connections, autoswitch, current/target scene, mode/reason; `GET /api/admin/status` | Overview | [ ] Preserve unavailable/stale states; never infer connected from missing data |
| `/admin/extensions` | BLE name/BPM/HR state; LHM URL, sensors, connection, stale/error/check time, required mode/tips; sysinfo CPU temp/power, GPU load and LHM requirement; same status API | Overview / Settings connection diagnostics | [ ] Preserve enabled, required, active, busy and severity distinctions |
| `/admin/features` | Overlay theme/widgets; commentary busy/available; tape available; event-engine flags; same status API | Overview / Settings features | [ ] Distinguish enabled from active and provider availability |
| `/admin/activity` | `GET /api/admin/activity?limit=80`, source/kind/message/time and ephemeral marker | Diagnostics activity | [ ] Empty and unavailable differ; render messages as text |
| Admin transport | 2s primary polling; debounced `/ws` and `/ws/overlay` invalidation depending on page | Shared read adapters | [ ] Bounded single-flight reads, stale reporting and cleanup; transport may differ if visible behavior is preserved |

## GR switcher parity

| Feature/action | Existing endpoint or source | Studio target | Acceptance |
| --- | --- | --- | --- |
| Connections, mode, current/target scene, reason, autoswitch, RESTART state | `GET /status` | OBS scenes / Overview | [ ] Show actual server values and unavailable state |
| Session type/name/number; hide synthetic Test session details | `GET /status` | OBS scenes | [ ] Preserve meaningful session label and absent-data handling |
| Streaming, stream durations, OBS profile, stream selection/readiness, YouTube title/description/errors/quota/auth state | `GET /status` | OBS scenes / Stream diagnostics | [ ] Keep metadata distinct from actual streaming state |
| Switch count, mean latency, uptime, OBS/iRacing connected durations, error total/breakdown | `GET /metrics` | Diagnostics | [ ] Preserve units and distinguish missing from zero |
| Switcher event log with event type/time/message/data and notifications | `GET /api/events?count=<dashboard_event_log_size>` | Diagnostics / OBS scenes | [ ] Preserve event meaning and bounded log; escape text |
| Toggle autoswitch | `POST /autoswitch/toggle` | OBS scenes | [ ] One request per action, reread actual state |
| Reset RESTART mode | `POST /restart-mode/reset` | OBS scenes | [ ] Preserve action semantics and refresh state |
| Runtime log badge / DEBUG↔INFO toggle | `GET /logging/level`, `POST /logging/level` JSON `{level}` | Diagnostics | [ ] Runtime-only label; resets at process restart |
| Reload config | `POST /config/reload` | Settings / Diagnostics | [ ] Show server `applied_live` and `needs_restart` lists, including failure |
| Reinitialize stream metadata | `POST /stream/reinit` | OBS scenes | [ ] Show returned title/failure and refresh metadata |
| YouTube authorize | `GET /oauth/initiate` opens returned `authorization_url`; `GET /oauth/status` checks authentication | OBS scenes / Connections | [ ] Preserve explicit authorization action, bounded checks and timeout; do not expose credentials |
| Reset service | `POST /reset` | Diagnostics lifecycle | [ ] Confirm reset to CONNECTING, metrics clearing and safe scene; reread status/metrics/events |
| Restart service | `POST /restart` | Diagnostics lifecycle | [ ] Confirm service restart; show initiated versus failed and reconnect state |
| Shutdown service | `POST /shutdown` | Diagnostics lifecycle | [ ] Confirm service stop; show expected unavailability without retrying write |

Legacy GR has no manual override input/button. It displays `override_applied`
events. `POST /override` is an existing API capability and a planned Studio OBS
control, but is not a legacy UI parity claim. Audit its payload separately in
`API.md` before exposing it. The same applies to new scene enumeration controls.

The legacy custom confirmation dialog supports cancel, outside-click and Escape;
reset uses a normal confirmation and restart/shutdown use danger styling. Native
controls must preserve explicit intent and keyboard cancellation. Autoswitch,
RESTART reset, logging, reload, stream reinit and OAuth do not have legacy
confirmation dialogs. All migrated writes still need pending locks and no
automatic retries after an uncertain outcome; this is a plan requirement beyond
legacy behavior.

## Config and commentary parity

| Feature/action | Existing endpoint or local operation | Studio target | Acceptance |
| --- | --- | --- | --- |
| Section-grouped bool/int/float/string/choice controls, limits/help and live/restart badge | `GET /api/config`: `schema`, `overlay`; redacted switcher metadata | Settings | [ ] Use authoritative FieldSpec; exclude secrets and unsupported switcher writes |
| Save overlay settings, nullable inputs and error feedback | `PUT /api/config` JSON `{values}`; `X-Requested-With: irswitch` | Settings / contextual supported parameter editors | [ ] One existing writer; changed-only draft, validation, canonical readback and live/restart results |
| Runtime status/schema/language/speech; TTS backend/status/reason; timeline activity/stream epoch; mailbox depth/capacity; loop; tape status/drop/size; per-tape-channel funnel counters | `GET /api/commentary/runtime` | Commentary runtime | [ ] Preserve provider absence and degraded TTS explanation |
| Why silence: sequence, decision/reason, optional beat/channel/score | `GET /api/commentary/runtime/decisions?limit=20` | Commentary decisions | [ ] Provider absent differs from empty ring; bounded newest-first display |
| Refresh runtime/decisions (legacy decisions also every 4s) | Same GET endpoints | Commentary | [ ] Reads bounded, failures visible, cleaned up on leave |
| Manual text and EN/CS language selection; browser voice and rate −10…10 | Browser `speechSynthesis`, `SpeechSynthesisUtterance`; language en-US/cs-CZ; rate clamp 0.6…1.4 | Commentary testing | [ ] Browser-only audio clearly labelled; missing Web Speech explained |
| Speak/stop browser | Local speech synthesis speak/cancel | Commentary testing | [ ] Cancellation affects browser speech only; voices refresh when available |
| Offline validate | `POST /api/commentary/validate`, `commentary-runtime/2` text plus explicit actor/fact bindings and evaluation time | Commentary testing | [ ] Label fixture context as offline; show valid/issues or refusal; do not invent live bindings |
| Server manual speak | `POST /api/commentary/speak`, `{schemaVersion: "commentary-runtime/2", language: "en", text}` | Commentary testing | [ ] EN-only; report accepted/admitted/requestId vs refusal; no duplicate audio request |

Commentary writes use JSON content type and `X-Requested-With: irswitch`.
Server TTS/device/duck settings remain `config.ini` plus config reload, as stated
by the legacy page; browser voice/rate controls must not imply server configuration.

## Overlay, developer and VR parity

| Source/feature | Existing source/action | Studio target | Acceptance |
| --- | --- | --- | --- |
| OBS output `/overlay`, `/overlay/` | Snapshot `GET /api/overlay/snapshot`, live `/ws/overlay`, rendering/i18n/catalog resources | Clean OBS Browser Source; Overlay preview | [ ] Preserve URLs, transparency and idle behavior; no administrative chrome in output |
| Dry test `/overlay/demo` | Client iframe `/overlay?demo=1&renderer=v4`, V3/V4 selection, five theme choices, replay reload, cue label and scaled 1920×1080 stage | Overlay simulation | [ ] Native controls may embed the clean renderer; demo labelled; theme/renderer/replay/cue preserved |
| Golden `/overlay/golden` | Redirect to `/overlay?demo=1&renderer=v4&layout=golden&fixture=all&theme=cyber_racing&motion=off` | Overlay developer diagnostics | [ ] Preserve existing golden URL/fixture behavior |
| Debug race/bio/system panes | `/ws/overlay` snapshot and domain state | Diagnostics overlay | [ ] Preserve domains and absent/stale connection states |
| Debug TEST event buttons | `GET /api/overlay/debug/events`, `POST /overlay/debug/emit` JSON `{name}`, CSRF header | Diagnostics overlay injection | [ ] Label as live injection; distinguish from isolated simulation; report accepted/rejected action |
| VR connections/current scene/streaming/duration | `/vr-status` server render then `GET /status` polling if JS supported | Diagnostics VR + preserved widget route | [ ] Same data visible natively; external VR presentation remains supported |
| VR compact transparent widget | Minimum 420px width, 75px height, large high-contrast scene/connection/recording indicators | Preserve `/vr-status` | [ ] Do not replace external widget with full Studio navigation |
| VR cache-bust redirect | `/vr-status?redirect=1` →302 timestamped `/vr-status?t=...`, no-cache responses | Preserve widget compatibility | [ ] Redirect and server-rendered initial values remain; document RaceLab refresh limitations |

VR exposes no unique engine write action. Its unique capability is presentation
and compatibility with a consumer that may ignore JavaScript/refresh. Native
diagnostics parity does not justify retiring the standalone VR widget.

Debug injection is **not isolated**: `overlay/http.py` injects the attached runtime
manager (or a fallback manager), publishes events to the shared overlay bus and
flushes active state. The legacy page offers immediate TEST buttons without
confirmation. Studio must clearly separate this operation from client demo and
P6 replay; disabling or gating it is a deliberate safety decision to document.
The dry demo executes renderer-side scenarios; that alone does not satisfy P6
deterministic domain replay or prove absence of all network reads.

## P6 retirement and evidence gates

- [ ] Each row has native parity evidence or an explicit preserved-route decision; permanent legacy admin iframes do not satisfy migration.
- [ ] Existing API writes retain transport/security validation; unsupported provider actions show unavailability.
- [ ] Duplicate clicks cannot issue parallel writes; timeout checks actual state rather than retrying an uncertain action.
- [ ] Old links remain compatible. OBS output and VR consumer URLs retain their external contracts.
- [ ] Failure, restart, rollback and packaged upgrade checks cover wheel and Windows EXE; browser-only fixtures do not prove these integrations.
- [ ] Future replay has separate state, virtual clock/reset/run identities and cannot call OBS/TTS; renderer demo and live debug emission are not used as substitutes.

Graph/catalog, episode history and definition revision/activation are new P3–P5
capabilities, not legacy UI functions. Their authority, identity, availability,
bounded history and persistence contracts need their own acceptance evidence.
