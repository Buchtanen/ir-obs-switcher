# Spec: Robust admin dashboard

**Status:** Slice 1 shipped; **Slice 1.1 contract revision** (this document) — fix dishonest fields before Slice 2  
**Baseline:** branch work after commentary #127; admin skeleton in `src/irswitch/server/admin.py` + `src/irswitch/web/admin/`  
**Related:** [`sysinfo_lhm_upgrade_spec.md`](sysinfo_lhm_upgrade_spec.md), [`API.md`](../API.md), legacy `/gr-status`

Product contract for a **live admin** covering switcher + overlay extensions + feature readiness.  
This revision incorporates critical review from two independent reviewers (Claude Opus + GPT-5.6).

---

## 1. Intent

`/gr-status` only reflected iRacing/OBS/scene-switcher state. Newer subsystems (BLE HR, LibreHardwareMonitor → sysinfo package sensors, overlay HUD, commentary TTS) are connectable, have config vs runtime vs momentary-work semantics, and emit activity — but were invisible on the operator UI.

Goal: one **admin shell** (`/admin`) as the primary **read-only** operator overview:

1. Connection / extension readiness at a glance (including server-computed `health`)  
2. Feature flags with **enabled / available / active (+ busy)** — not a single overloaded `active`  
3. Live activity feed (switcher history + commentary decisions + overlay **lifecycle** events)  
4. Links into existing tools (`/config`, `/commentary`, `/overlay/debug`, `/gr-status` controls)

**Go-live streaming (LIVE/IDLE, duration)** remains on `/gr-status` until Slice 2 migrates controls. Until then `/admin` is “primary overview”, not “full replacement of GR”.

VR widget (`/vr-status`) stays minimal and separate (RaceLab constraints).

---

## 2. Current baseline

| Surface | Today | Gap after Slice 1 |
| --- | --- | --- |
| `/admin` + `/api/admin/*` | Skeleton UI + aggregation | Dishonest `active`/LHM/`at` clocks; no `health`; dual-WS poll amplification |
| `/gr-status` | Switcher controls + streaming | Still needed for go-live ops |
| `/config`, `/commentary` | Editors / TTS test | Linked from admin; not status views |
| `WS /ws`, `WS /ws/overlay` | Switcher / overlay live | Admin must not treat every frame as full REST refresh |

---

## 3. Information architecture

```text
/admin                 Overview (health + connections/extensions + features + activity preview)
/admin/extensions      BLE, LHM, sysinfo detail (connections / prerequisites)
/admin/features        Overlay + commentary + tape + event_engine flags
/admin/activity        Merged feed (history + lifecycle; not raw active_events snapshot spam)
/gr-status             Switcher controls + streaming (legacy until Slice 2)
/vr-status             Unchanged VR widget
```

Future rename (Slice 2 UX, optional): `connections` (iRacing, OBS, BLE, LHM, YouTube) vs `features` (overlay, commentary, tape, sysinfo, event_engine). Slice 1.1 keeps path `/admin/extensions` but documents LHM as **prerequisite**, not a user “enable” toggle.

---

## 4. Semantics (three axes + busy)

Do **not** overload one `active` boolean across incompatible meanings.

| Axis | Meaning |
| --- | --- |
| `enabled` | Config wants the subsystem on (INI / FieldSpec). Absent for pure prerequisites → use `required` instead. |
| `available` | Runtime object / provider exists (overlay runtime up, director constructed, …). |
| `active` | Ready or connected: `enabled && available` for features; for BLE = radio in connected/connecting/reconnecting. |
| `busy` | Momentary work (commentary speaking). Optional; default false. |
| `status` | Closed enum string (see §5). |
| `severity` | Server-computed: `ok` \| `warn` \| `bad` \| `idle` \| `disabled`. UI must not invent severity from free text. |

### Per component

| Component | `enabled` / `required` | `available` | `active` | `busy` / notes |
| --- | --- | --- | --- | --- |
| Overlay | `overlay.enabled` | overlay runtime present | enabled ∧ available | — |
| Commentary | `commentary.enabled` | director present | enabled ∧ available | `busy` = speaking (`now < busyUntil`); status `ready`/`speaking` |
| BLE HR | `heart_rate.enabled` | provider started | bio connected/connecting/reconnecting | — |
| System info | `system_info.enabled` | runtime sampling path present | enabled ∧ available | `degraded` only when **required metrics missing**, not merely “LHM down while RAPL/PDH fills values” (see sysinfo spec) |
| LHM | **`required`** = sysinfo wants CPU package (and later gpu_source=lhm). Not an INI enable. | HTTP listener reachable | required ∧ reachable with usable sensors | `not_required` when sysinfo/CPU package off — **no nag tip** |
| Session tape | `overlay.tape.enabled` | tape helper exists | **file path open** for current session (`path is not None`) | status `recording` only if path open |

“Enabled but inactive” is actionable **only** when severity is `warn`/`bad` (missing dependency, disconnected). `ready` + `active=true` + `busy=false` is healthy idle — **not** a warning.

### Requirement mode (LHM / future)

`requirementMode`: `optional` \| `recommended` \| `required`  
Slice 1.1: LHM is `recommended` for CPU package when sysinfo+cpu enabled; becomes `required` only when config `lhm_required=true` ships (sysinfo upgrade). API must not hardcode `lhmRequired: true` forever.

---

## 5. API contract

### Naming

- New `/api/admin/*` fields: **camelCase**  
- Nested `switcher` block: **frozen legacy snake_case**, explicit field list (subset of `/status`)  
- `schemaVersion`: integer, currently `1` (bump on breaking admin payload changes)

### `GET /api/admin/status`

Fail-soft: external probe failures → **HTTP 200** with `severity`/`errorCode` on the card. HTTP 500 only for internal contract bugs.

```json
{
  "schemaVersion": 1,
  "version": "x.y.z",
  "runtime": { "overlay": true, "switcher": false },
  "health": {
    "ready": false,
    "blocking": [{ "id": "obs", "reason": "disconnected", "tip": "…" }],
    "warnings": [{ "id": "lhm", "reason": "unreachable", "tip": "…" }]
  },
  "switcher": {
    "connected_iracing": false,
    "connected_obs": false,
    "autoswitch": true,
    "mode": null,
    "current_scene": null,
    "target_scene": null,
    "reason": null,
    "session_type": null
  },
  "extensions": { "ble": {}, "lhm": {}, "sysinfo": {} },
  "features": { "overlay": {}, "commentary": {}, "tape": {}, "eventEngine": {} }
}
```

Each extension/feature card (except raw `eventEngine` flags object):

```json
{
  "id": "ble",
  "label": "BLE heart rate",
  "enabled": true,
  "available": true,
  "active": true,
  "busy": false,
  "status": "connected",
  "severity": "ok",
  "detail": {}
}
```

LHM card uses `required` + `requirementMode` instead of pretending `enabled` is a user toggle:

```json
{
  "id": "lhm",
  "label": "Libre Hardware Monitor",
  "required": true,
  "requirementMode": "recommended",
  "available": false,
  "active": false,
  "status": "unreachable",
  "severity": "warn",
  "detail": {
    "connection": "unreachable",
    "lastBaseUrl": null,
    "sensorRows": 0,
    "prerequisiteFor": ["sysinfo.cpu_package"],
    "tip": "…"
  }
}
```

When `required=false`: `status=not_required`, `severity=idle`, **omit tip**.

#### Status enums (closed)

| Component | Allowed `status` |
| --- | --- |
| ble | `disabled`, `disconnected`, `connecting`, `reconnecting`, `connected`, `error` |
| lhm | `not_required`, `unreachable`, `reachable_empty`, `connected`, `error`, `stale` |
| sysinfo | `disabled`, `idle`, `sampling`, `degraded`, `error` |
| overlay | `disabled`, `idle`, `running` |
| commentary | `disabled`, `idle`, `ready`, `speaking` |
| tape | `disabled`, `idle`, `recording` |

#### Live transport (Slice 1.1)

- **Primary:** poll `/api/admin/status` + `/api/admin/activity` every ≈2 s  
- **At most one** status request and one activity request in flight (single-flight)  
- Optional WS `/ws` and/or `/ws/overlay` may **invalidate** poll with **debounce ≥ 500 ms** — must not fire unbounded REST on every overlay frame  
- Pages that do not need overlay traffic must not open `/ws/overlay`  
- LHM probe: read **cache** from status path; background/single-flight probe TTL ≥ poll interval (target 5–10 s). Status returns `detail.checkedAt` / `stale` when added

Streaming fields: **not** in Slice 1.1 status (remain on `/gr-status` / full `/status`).

### `GET /api/admin/activity?limit=50`

**Not** “dump `active_events` every poll”.

| `source` | Kind of data |
| --- | --- |
| `switcher` | EventLog history |
| `commentary` | SpeakDecision history |
| `overlay` | **Lifecycle** events only (ENTER/UPDATE/EXIT / spoken widget shown). Until a ring buffer exists, overlay rows are labeled `kind` + `ephemeral: true` and clients must replace-by-`dedupeKey`, not append forever |

#### Clocks (mandatory)

Mixed clocks are forbidden in one `at` field.

| Field | Meaning |
| --- | --- |
| `occurredAt` | Wall-clock **UTC epoch seconds** (float) for display and cross-source sort |
| `monoMs` | Optional monotonic ms for same-process ordering / tie-break |
| `id` or `dedupeKey` | Stable string per logical event |

Conversion: `occurredAt = time.time() - (time.monotonic() - mono_seconds)`.

Sort: `occurredAt` desc, then `source` priority (`commentary` > `overlay` > `switcher`), then `dedupeKey`.

#### Retention

| Source | Retention today |
| --- | --- |
| switcher | `dashboards.dashboard_event_log_size` (default 50) |
| commentary | `commentary.decision_log_size` (default 32) |
| overlay lifecycle | TBD ring (Slice 1.2+); until then ephemeral snapshot ≤ active widget count |

`limit` clamped 1–200; invalid/non-numeric → default 50 (document in API.md). `limit` cannot invent history beyond retention.

---

## 6. Security posture

- Default bind `127.0.0.1` remains the threat model for local-only telemetry (includes BPM).  
- `/api/admin/*` GET must not widen exposure vs today; document that CORS `*` + LAN bind would leak health data — prefer localhost.  
- Slice 2 write actions (override/restart/…) **must** use the same localhost + `X-Requested-With: irswitch` guard as `PUT /api/config`.  
- No secrets in admin payloads.

---

## 7. Architecture constraint

`server/admin.py` aggregates **public** snapshots only. Spec target: each subsystem exposes `status_snapshot()` (or equivalent public method). Accessing `_`-prefixed foreign attributes is a known Slice 1 debt; Slice 1.2+ must eliminate it (AC below).

---

## 8. Non-goals

- SPA / bundler / new Python or JS dependencies  
- Editing config from Overview (still `/config`)  
- VR feature parity  
- Full LHM-only sysinfo migration (sysinfo spec; docs + phased code)  
- Alerting, multi-PC remote admin, RBAC, time-series DB  
- Auto-start LHM with UAC (detect/tip only)

---

## 9. Rollout slices

| Slice | Deliverable |
| --- | --- |
| **1** | Skeleton `/admin` + APIs + docs (shipped) |
| **1.1** | Contract honesty: axes, clocks, LHM required/not_required, commentary ready≠warn, activity clocks, poll single-flight/debounce, `schemaVersion`, severity, tape path-open |
| **1.2** | `health` aggregation; public `status_snapshot()`; overlay lifecycle ring; LHM background probe TTL |
| **2** | Migrate switcher controls + streaming into Overview; soft-deprecate `/gr-status` (banner + README legacy; delete = separate `semver:major`) |
| **3** | Optional `/ws/admin` (bounded queue, heartbeat, no duplicate REST storm); richer EE decision log |

---

## 10. Docs / config impact

- `API.md` — admin endpoints must match this contract (examples verified against payload)  
- `README.md` — `/admin` primary overview; `/gr-status` controls/streaming until Slice 2  
- `CONFIG.md` — no new keys in 1.1; retention keys referenced  
- This file + `sysinfo_lhm_upgrade_spec.md`

---

## 11. Acceptance criteria

### Slice 1.1
- [ ] Cards expose `enabled`/`available`/`active`/`busy`/`status`/`severity` (LHM: `required`/`requirementMode`)  
- [ ] Commentary `ready` ⇒ `active=true`, `busy=false`, severity not warn  
- [ ] Sysinfo disabled ⇒ LHM `required=false`, `status=not_required`, no tip  
- [ ] Activity `occurredAt` is wall-clock epoch for all sources; sort deterministic  
- [ ] Admin JS: single-flight poll; WS invalidate debounced ≥500 ms  
- [ ] `schemaVersion: 1` present  
- [ ] Tape `recording` only when tape `path` is open  
- [ ] Tests cover the above; docs examples match payload  

### Slice 1.2+
- [ ] `health.ready` / blocking / warnings server-side  
- [ ] No `_private` foreign attribute access from `server/admin.py`  
- [ ] LHM probe single-flight; status p95 stays low with LHM down  
- [ ] Overlay lifecycle ring with `dedupeKey`
