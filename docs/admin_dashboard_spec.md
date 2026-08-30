# Spec: Robust admin dashboard

**Status:** in progress — Slice 1 shipping in this work item  
**Baseline:** `master` after commentary content + P1/P2 decision log (#127)  
**Related:** [`sysinfo_lhm_upgrade_spec.md`](sysinfo_lhm_upgrade_spec.md), [`API.md`](../API.md), legacy `/gr-status`

This document is the product contract for replacing the switcher-centric GR dashboard with a **live admin** that covers switcher + overlay extensions + feature readiness.

---

## 1. Intent

The old `/gr-status` dashboard only reflected iRacing/OBS/scene-switcher state. Newer subsystems (BLE HR, LibreHardwareMonitor → sysinfo, overlay HUD, commentary TTS) are connectable, have **enabled vs active** semantics, and emit their own activity — but the dashboard did not show them.

Goal: one **admin shell** (`/admin`) that is the primary operator UI:

1. Connection / extension readiness at a glance  
2. Feature flags + live activity (enabled vs actually running)  
3. Live activity feed (switcher + commentary + overlay widgets)  
4. Links into existing tools (`/config`, `/commentary`, `/overlay/debug`, …)

VR widget (`/vr-status`) stays minimal and separate (RaceLab constraints).

---

## 2. Current baseline (accurate)

| Surface | Today | Gap |
| --- | --- | --- |
| `/gr-status` | Large inline HTML; iRacing/OBS/stream/event log | No BLE / LHM / commentary / overlay feature matrix |
| `/config` | Schema form for overlay INI keys | Not a status view |
| `/commentary` | TTS test + decisions | Not wired into main dashboard |
| `WS /ws` | Switcher status + chapters | No extension statuses |
| `WS /ws/overlay` | race / bio / system / events | Not consumed by GR dashboard |
| `GET /api/commentary/status` | settings + voices | Missing “active/speaking” in admin |
| LHM | HTTP probe inside `system/lhm_http.py` | No admin-facing status |

---

## 3. Information architecture

```text
/admin                 Overview (health + extensions strip + features strip + switcher summary)
/admin/extensions      BLE, LHM, sysinfo, NVML/psutil detail
/admin/features        Overlay + commentary + event_engine + tape (enabled / active)
/admin/activity        Live merged log (switcher events, commentary decisions, overlay widgets)
/gr-status             Legacy switcher controls (override, restart, YouTube) — linked from admin
/vr-status             Unchanged VR widget
```

Navigation is shared across admin pages and links out to `/config`, `/commentary`, `/overlay*`.

---

## 4. Semantics: enabled vs active

| Component | `enabled` | `active` / connected |
| --- | --- | --- |
| Overlay | `overlay.enabled` | Overlay runtime running and publishing (bus / runtime present) |
| Commentary | `commentary.enabled` | Runtime director present **and** currently speaking / busy, or last speak within window |
| BLE HR | `heart_rate.enabled` | `bio.status` ∈ connected / connecting / reconnecting; `bio.connected` |
| System info | `system_info.enabled` | Provider sampling; CPU package metrics require LHM |
| LHM | soft prerequisite (not an INI enable) | HTTP `/data.json` or `/metrics` reachable |
| Session tape | `overlay.tape.enabled` | Tape writer open for current session |

Admin UI must show **both** columns. “Enabled but inactive” is the actionable degraded state (e.g. LHM not running → sysinfo CPU temp/power empty).

---

## 5. API contract (Slice 1)

### `GET /api/admin/status`

Aggregated JSON for the admin shell. Fail-soft: missing runtime → `runtime: false` blocks, never 500 for external probes.

```json
{
  "version": "x.y.z",
  "switcher": { "...subset of GET /status or null..." },
  "extensions": {
    "ble": {
      "id": "ble",
      "label": "BLE heart rate",
      "enabled": true,
      "active": false,
      "status": "disconnected",
      "detail": { "deviceName": null, "bpm": null, "hrState": "unknown" }
    },
    "lhm": {
      "id": "lhm",
      "label": "Libre Hardware Monitor",
      "enabled": true,
      "active": false,
      "status": "unreachable",
      "detail": { "baseUrl": null, "sensorRows": 0, "prerequisiteFor": ["sysinfo.cpu_package"] }
    },
    "sysinfo": {
      "id": "sysinfo",
      "label": "System info",
      "enabled": true,
      "active": true,
      "status": "sampling",
      "detail": { "cpuTemp": null, "cpuPower": null, "gpuLoad": null, "lhmRequired": true }
    }
  },
  "features": {
    "overlay": { "enabled": true, "active": true, "status": "running" },
    "commentary": { "enabled": false, "active": false, "status": "disabled", "busy": false },
    "tape": { "enabled": true, "active": false, "status": "idle" },
    "eventEngine": { "v2Payload": false, "practice": false, "pitStory": false, "hrPressure": false }
  }
}
```

### `GET /api/admin/activity?limit=50`

Merged newest-first activity rows:

| `source` | Meaning |
| --- | --- |
| `switcher` | EventLog (`scene_switch`, connection_*, …) |
| `commentary` | SpeakDecision rows (`spoken` / `skipped`) |
| `overlay` | Active / recent widget envelopes from overlay bus |

```json
{
  "items": [
    {
      "at": 1710000000.12,
      "source": "commentary",
      "kind": "spoken",
      "message": "He takes P5 from Rossi.",
      "data": { "nodeId": "overtake", "reason": "ok" }
    }
  ]
}
```

### Live updates

Slice 1: admin JS connects to `WS /ws` + `WS /ws/overlay` and polls `/api/admin/status` + `/api/admin/activity` on a short interval (≈2 s).  
Later slice: optional dedicated `WS /ws/admin` if polling becomes noisy.

---

## 6. Non-goals (Slice 1)

- Rewriting `/gr-status` inline HTML into a SPA framework / bundler  
- New Python/JS dependencies  
- Editing config from Overview (still `/config`)  
- VR dashboard feature parity  
- Implementing full LHM-only sysinfo migration (see sysinfo spec — docs only until scheduled)

---

## 7. Rollout slices

| Slice | Deliverable |
| --- | --- |
| **1** | Spec + `/admin` shell + status/activity API + extensions/features/activity pages + tests + docs |
| **2** | Migrate remaining switcher controls (override, restart, YouTube) into Overview; soft-deprecate `/gr-status` |
| **3** | Optional `/ws/admin`; richer overlay decision log; LHM process detect / start hints on Windows |

---

## 8. Docs / config impact

- `API.md` — document admin endpoints  
- `README.md` — primary dashboard URL → `/admin`  
- `CONFIG.md` — no new keys in Slice 1  
- This file + `sysinfo_lhm_upgrade_spec.md`

---

## 9. Acceptance criteria (Slice 1)

- [ ] `/admin` serves and shows extension + feature status live  
- [ ] BLE and LHM appear as explicit extension cards with enabled/active/status  
- [ ] Commentary and overlay show enabled vs active  
- [ ] `/admin/activity` shows merged live log  
- [ ] Unit/API tests cover status + activity aggregation  
- [ ] Docs updated (`API.md`, `README.md`, this spec, sysinfo LHM upgrade spec)
