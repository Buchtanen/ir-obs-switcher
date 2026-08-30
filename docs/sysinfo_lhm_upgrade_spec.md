# Spec: Sysinfo upgrade — Libre Hardware Monitor as data source

**Status:** idea / planned upgrade — **not implemented** by the admin Slice 1 work  
**Baseline:** CPU package temp/power already prefer LHM HTTP (`system/lhm_http.py`); GPU via NVML; RAM/CPU load via psutil; FPS from iRacing  
**Related:** [`admin_dashboard_spec.md`](admin_dashboard_spec.md), `CONFIG.md` `[system_info]`, README LHM note

This document defines how to upgrade overlay **sysinfo** so operator-facing metrics are driven primarily from **Libre Hardware Monitor (LHM)**, with LHM runtime treated as a **hard prerequisite** for correct sysinfo — not an optional nicety.

---

## 1. Intent

Today sysinfo is a mash-up:

| Metric | Source today |
| --- | --- |
| CPU load / clocks / RAM | `psutil` |
| CPU package temp / power | LHM HTTP (or legacy WMI) via `cpu_sensors` |
| GPU load / temp / power / VRAM / clocks | NVIDIA NVML (`pynvml`) |
| FPS / frametime | iRacing telemetry |

Problems:

1. LHM must already be running with Remote Web Server — operators discover this only when CPU temp/power stay empty.  
2. GPU path is NVIDIA-only; AMD/Intel GPUs stay blank even when LHM sees them.  
3. Admin/dashboard had no LHM readiness signal.  
4. Future sysinfo modules (fans, board, multi-GPU) already exist in LHM’s tree but are unused.

**Upgrade goal:** treat LHM as the **canonical hardware sensor bus** for sysinfo display metrics (CPU/GPU/memory package sensors). Keep iRacing for FPS/frametime. Keep fail-soft behavior (never crash the overlay loop).

---

## 2. Non-goals

- Bundling or auto-installing LibreHardwareMonitor into the irswitch installer (may be a later Windows packaging track).  
- Replacing bleak / BLE HR with LHM (HR stays BLE).  
- Remote LHM over the public internet (SSRF gate stays localhost / private NIC only).  
- New third-party Python deps for hardware access.

---

## 3. Target architecture

```text
LibreHardwareMonitor.exe (Remote Web Server)
        │  HTTP /data.json  (preferred)  or  /metrics
        ▼
 irswitch.system.lhm_http  →  normalized sensor rows
        ▼
 irswitch.system.provider  →  SystemState (cpu/gpu/memory/…)
        ▼
 OverlayBus / WS / overlay SYSINFO widget
        +
 Admin extensions card (LHM reachable?)
```

**Prerequisite policy (target):**

- If `system_info.enabled` and CPU/GPU package sensors are configured:  
  - LHM unreachable → sysinfo status `degraded`, admin shows actionable tip  
  - Do **not** silently pretend NVML-only is “full” sysinfo once the upgrade lands  
- FPS/frametime remain iRacing-sourced (empty in garage is OK)

---

## 4. Data mapping (proposed)

Flatten LHM rows → `SystemState` fields:

| Sysinfo field | LHM preference | Fallback (transition) |
| --- | --- | --- |
| `cpu.temperature` | CPU Package Temperature | (remove WMI after LHM-only) |
| `cpu.power` | CPU Package Power | none on stock Windows |
| `cpu.load` | CPU Total Load **or** keep psutil | psutil during transition |
| `cpu.frequency` | CPU Core clocks avg / effective | psutil |
| `gpu.*` | matching GPU hardware node (NVIDIA/AMD/Intel) | NVML for NVIDIA only |
| `memory.*` | LHM memory load / used | psutil |
| `performance.fps` | — | iRacing only |

Selection rules must stay deterministic (prefer Package over Core #N; prefer primary GPU hardware id).

---

## 5. Config impact (when implemented)

Likely keys under `[system_info]` (names TBD in implementing PR):

- `lhm_required` (bool, default true after migration) — degrade loudly if LHM down  
- `lhm_url` or keep autodiscovery from `LibreHardwareMonitor.config`  
- `gpu_source` = `auto` \| `lhm` \| `nvml`  
- Existing `lhm_dll_path` remains for any residual native path; HTTP remains primary for 0.9.5+

Migration note for users:

1. Install LibreHardwareMonitor 0.9.5+  
2. Options → Remote Web Server → Run  
3. File → Hardware → enable CPU (+ GPU)  
4. Confirm admin **Extensions → LHM** shows reachable before going live

---

## 6. Admin / observability

Admin Extensions page (Slice 1) already surfaces LHM as a first-class extension:

- `enabled`: always “required when sysinfo CPU package needed” (soft in Slice 1)  
- `active` / `status`: HTTP reachable + sensor row count + base URL  
- Tip copy: start LHM Remote Web Server

When this upgrade ships, sysinfo card must reference LHM status explicitly (`lhmRequired: true`).

---

## 7. Implementation slices (future work)

| Slice | Work |
| --- | --- |
| A | Docs + admin LHM status (done with admin dashboard Slice 1) |
| B | Expand LHM row picking for GPU + memory; feature-flag `gpu_source=lhm` |
| C | Prefer LHM for CPU load/clocks; psutil fallback |
| D | `lhm_required` + health banner tip; drop legacy WMI path if unused |
| E | Optional Windows helper to detect/start LHM process (careful: UX + UAC) |

Each slice needs tests with fixture `/data.json` / `/metrics` (see `tests/test_system_info.py`).

---

## 8. Acceptance criteria (when upgrade is scheduled)

- [ ] With LHM running, CPU package temp/power **and** GPU metrics populate without NVML when `gpu_source=lhm`  
- [ ] With LHM stopped, admin + overlay report degraded sysinfo with actionable tip  
- [ ] SSRF allow-list unchanged (local hosts only)  
- [ ] No main-loop crash on LHM timeout  
- [ ] `CONFIG.md` + `config.example.ini` + `API.md` updated  
- [ ] Tests cover parse + provider merge for LHM-only path
