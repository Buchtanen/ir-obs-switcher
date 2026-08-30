# Fused parallel implementation plan — admin + sysinfo LHM

**Status:** plan only — not an implementation order until user approves a wave  
**Sources:** dual plans from Claude Opus + GPT-5.6 on revised specs (admin 1.1 landed)  
**Branch baseline:** `cursor/admin-dashboard-c352`

---

## Verdict (critical)

Both plans agree on the only safe parallelism: **producers in parallel, one consumer owns `admin.py` / admin JS / API.md**.

Disagreements are mostly packaging (how to split LHM vs config vs OBS). Fusion below picks the stricter ownership rules and drops false parallelism.

| Agree | Diverge → fusion choice |
| --- | --- |
| First wave = 3 producer streams, no admin wire edits | Claude puts **health (W1) in wave 1 owning `admin.py`**; GPT forbids admin until producers merge → **GPT wins** (health is consumer work in wave 2) |
| `status_snapshot()` producers separate from admin | Claude hooks lifecycle later on `runtime.py`; GPT hooks on `bus.py` → **GPT wins** (avoids fighting W1/`runtime.py`) |
| LHM HTTP isolated from provider/config | Claude splits select vs transport early; GPT keeps select with provider B → **split select as pure module OK in wave 1 *only if* it never touches `provider.py`/`lhm_http.py`** |
| Sysinfo B→C→D sequential on same merge point | Same |
| Slice 2 needs cached stream status, not OBS-per-request | GPT adds explicit OBS snapshot stream → **keep** |
| No SPA, no new deps, no LHM autostart | Same |

**False parallelism to reject:** splitting `admin.py` vs `admin.js`; splitting config.py/settings/schema; parallel B/C/D on `provider.py`; two agents on `overlay/runtime.py`.

---

## Architecture rule

```text
Wave 1 (parallel):   public producers + pure helpers     ──no──► /api/admin/*
        │
        ▼ merge gate
Wave 2 (parallel):   admin consumer 1.2  |  sysinfo B  |  OBS stream cache
        │
        ▼
Later (mostly serial lanes): sysinfo C→D, admin Slice 2, EE log, admin Slice 3, LHM detect tip
```

`schemaVersion` stays **1** while changes are additive. Breaking field renames ⇒ separate v2 proposal.

---

## First wave (start together) — 3 worktrees

Each: own issue, own branch off current admin branch (or master after merge), exclusive files only.

### P1 — Public runtime snapshots
**Branch hint:** `feat/admin-public-snapshots`  
**Owns:** `bio/provider.py`, `commentary/director.py`, `overlay/runtime.py`, `overlay/tape.py`, `overlay/http.py` (`get_overlay_runtime()`), tests for those  
**Does not touch:** `server/admin.py`, `web/admin/**`, `API.md`  
**AC:** public `status_snapshot()` for commentary/tape/runtime/bio as needed; no foreign `_private` needed later; fail-soft; unit tests

### P2 — Overlay lifecycle ring
**Branch hint:** `feat/overlay-lifecycle-ring`  
**Owns:** new `overlay/activity.py` (or `lifecycle_log.py`), `overlay/bus.py` only for hook in `publish_event`, tests  
**Does not touch:** `runtime.py`, `admin.py`  
**AC:** bounded ring; lifecycle only; `dedupeKey` + wall `occurredAt` + `monoMs`; no crash on bad envelope

### P3 — LHM transport cache / observability
**Branch hint:** `feat/lhm-status-cache`  
**Owns:** `system/lhm_http.py`, optional tiny helpers, LHM-focused tests/fixtures  
**Does not touch:** `provider.py`, config, admin  
**AC:** distinguish `unreachable` vs `reachable_empty`; TTL 5–10 s + single-flight; `checkedAt` / `lastSuccessAt` / `errorCode` / `stale`; SSRF unchanged; request path can read cache without forcing probe

**Optional 4th only if spare capacity and zero overlap:** pure `system/lhm_select.py` + fixtures (GPU/memory/CPU load pickers) — **no** provider wiring.

---

## Second wave (after P1–P3 merged)

### C1 — Admin Slice 1.2 (sole contract owner)
**Owns:** `server/admin.py`, new `server/admin_health.py`, `web/admin/**`, `tests/test_admin_api.py`, `API.md`, README admin notes  
**Consumes:** P1 snapshots, P2 ring, P3 LHM cache  
**AC:** server `health`; no `_private` foreign attrs; activity from lifecycle ring; LHM cache-only on GET; pages don’t open unused WS; additive `schemaVersion: 1`

### C2 — Sysinfo B (GPU/memory + provenance + `gpu_source`)
**Owns:** `system/provider.py`, new mapping module if needed, `overlay/models.py` (additive fields), settings/schema/config/example/CONFIG for `gpu_source` only  
**Depends:** P3 (+ optional lhm_select)  
**AC:** per-metric `source`/`sampledAt`; deterministic GPU pick; NVML fallback per policy; no admin wire edits

### C3 — OBS stream snapshot (cache-only)
**Owns:** new `obs/status.py` (or similar), minimal `obs/client.py` hooks, tests  
**AC:** LIVE/IDLE + duration + freshness from cache; owned background refresh; admin must not call OBS in-request later

---

## Later lanes (do not start in wave 1)

| Lane | Order | Notes |
| --- | --- | --- |
| Sysinfo C | after B | CPU load/clocks via LHM cache + psutil fallback |
| Sysinfo D | after C | `lhm_required` default **false**; admin health mapping by C1 follow-up |
| Admin Slice 2 | after C1 + C3 | controls + streaming UI; CSRF/localhost; soft-deprecate `/gr-status` (no delete) |
| EE decision log | parallel with Slice 2 OK | `events/decision_log.py` + manager_v2 only; admin wires in Slice 3 |
| Admin Slice 3 | after Slice 2 + EE log | `/ws/admin` coalesced; poll fallback |
| LHM process detect tip | after D | detect only, no start/UAC |

---

## Explicitly defer

Delete `/gr-status`; schema v2; LHM install/autostart; drop RAPL/PDH/WMI without audit; config edit from Overview; VR parity; RBAC/remote admin; fan control.

---

## Integration gates

1. Wave 1 PRs merge without changing `/api/admin/*`.  
2. C1 rebase on all three; contract tests + fail-soft injection (BLE/LHM/OBS/commentary) still HTTP 200.  
3. Spy/assert: admin GET does not start LHM/OBS I/O.  
4. Each PR: one `semver:*` label; docs impact; own issue + diary.

---

## Recommended action now

1. Finish/merge current admin Slice 1.1 PR (formatting already pushed).  
2. After approval: open **three** issues + branches for P1/P2/P3 and run agents in parallel.  
3. Do **not** start C1 until P1–P3 are on the integration branch.
