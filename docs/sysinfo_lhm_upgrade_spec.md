# Spec: Sysinfo upgrade — Libre Hardware Monitor as data source

**Status:** planned upgrade — **not fully implemented**; Slice A (admin LHM surface) exists via admin Slice 1/1.1  
**Baseline:** accurate multi-backend CPU package path in `system/cpu_sensors.py` + LHM HTTP in `system/lhm_http.py`; GPU via NVML; RAM/CPU load via psutil; FPS from iRacing  
**Related:** [`admin_dashboard_spec.md`](admin_dashboard_spec.md), `CONFIG.md` `[system_info]`, README LHM note

Defines how to evolve overlay **sysinfo** toward LHM as the **preferred** hardware sensor bus, without lying about today’s fallbacks or silently breaking working non-LHM setups.

Incorporates critical review (Claude Opus + GPT-5.6).

---

## 1. Intent

### Actual baseline today (correct this doc if code changes)

| Metric | Sources today (precedence / notes) |
| --- | --- |
| CPU package temp/power | Multi-backend in `cpu_sensors.read_cpu_package_sensors`: RAPL (Linux), PDH thermal, **LHM HTTP**, WMI (`LibreHardwareMonitor` / `OpenHardwareMonitor` / ACPI zones), optional LHM DLL (pythonnet); HWiNFO shared memory helpers also exist in-module |
| CPU load / clocks / RAM | `psutil` |
| GPU load / temp / power / VRAM / clocks | NVIDIA NVML (`pynvml`) only |
| FPS / frametime | iRacing telemetry |

Problems:

1. Operators often need LHM Remote Web Server for package temp/power on modern Windows LHM 0.9.5+, but discover that only when values stay empty — **unless** another backend filled them.  
2. GPU path is NVIDIA-only; AMD/Intel stay blank even when LHM sees them.  
3. Admin must show LHM readiness without false “required” nags when sysinfo is off or values already exist from other backends.  
4. Future modules (fans, board, multi-GPU) exist in LHM’s tree but are unused.

**Upgrade goal:** prefer LHM as the **canonical** hardware sensor bus for display metrics (CPU/GPU/memory package sensors) **when configured**, keep iRacing for FPS/frametime, keep fail-soft (never crash the overlay loop), and **do not** mark healthy RAPL/PDH/NVML setups as degraded merely because LHM is down — until the operator opts into `lhm_required`.

---

## 2. Non-goals

- Bundling or auto-installing LibreHardwareMonitor into the installer (later packaging track only).  
- Auto-start LHM with UAC elevation (Slice E = detect + tip at most).  
- Replacing BLE HR with LHM.  
- Remote LHM over the public internet (SSRF gate: localhost / private NIC only).  
- New third-party Python deps for hardware access.  
- Writing/controlling hardware via LHM (fans/pumps) — permanently out of scope.  
- Promoting HWiNFO/AIDA/etc. to first-class backends (do not grow the stack further).

---

## 3. Target architecture

```text
LibreHardwareMonitor.exe (Remote Web Server)
        │  HTTP /data.json  (preferred)  or  /metrics
        ▼
 irswitch.system.lhm_http  →  normalized sensor rows + connection status
        ▼
 irswitch.system.provider  →  SystemState (+ per-metric source / sampledAt)
        ▼
 OverlayBus / WS / overlay SYSINFO widget
        +
 Admin extensions card (LHM connection / required mode)
```

Background single-flight LHM poller with TTL; **no** blocking probe on the async sampling hot path.

### Prerequisite policy

| Mode | When | Admin / sysinfo behavior |
| --- | --- | --- |
| `optional` | sysinfo off or CPU package not needed | LHM `not_required`, no tip |
| `recommended` | sysinfo+cpu on, default today | Warn if LHM down **and** package temp/power empty; OK if other backends fill values |
| `required` | future `system_info.lhm_required=true` | Degrade loudly if LHM down even if NVML/psutil partial; still keep FPS from iRacing |

Default for a future `lhm_required` key: prefer **`false`** or staged rollout — flipping default `true` is behavior-breaking (`semver:major` or explicit migration).

---

## 4. Data mapping (implementation rules)

Flatten LHM rows → `SystemState` with **deterministic** selection:

1. Prefer sensors whose hardware id matches configured / first CPU or GPU device.  
2. Prefer Package / Tctl / “CPU Package” over Core #N.  
3. Prefer primary GPU hardware id (stable sort by LHM hardware id string); optional INI selector later.  
4. Every published metric should carry provenance when upgrade ships: `source` (`lhm` \| `nvml` \| `psutil` \| `rapl` \| …) and `sampledAt` (wall clock or mono+convert).  
5. Per-metric fallback during transition (not atomic all-or-nothing), unless `lhm_required` forces LHM for listed metrics.

| Sysinfo field | LHM preference | Fallback (transition) |
| --- | --- | --- |
| `cpu.temperature` | CPU Package Temperature | existing cpu_sensors chain |
| `cpu.power` | CPU Package Power | RAPL / none on stock Windows |
| `cpu.load` | CPU Total Load (Slice C) | psutil |
| `cpu.frequency` | effective/core clocks | psutil |
| `gpu.*` | matching GPU node (NVIDIA/AMD/Intel) when `gpu_source=lhm\|auto` | NVML if NVIDIA and allowed |
| `memory.*` | LHM memory load/used | psutil |
| `performance.fps` | — | iRacing only |

`gpu_source=auto` decision order (proposed): if LHM GPU sensors present → LHM; else if NVML works → NVML; else empty. Multi-GPU: lowest hardware id unless pinned.

Units: normalize to °C, W, %, GHz, GiB as today; document in CONFIG when keys land.

---

## 5. Config impact (when implemented)

Under `[system_info]` (names locked in implementing PR):

- `lhm_required` (bool, **default false** unless release notes justify major)  
- keep autodiscovery from `LibreHardwareMonitor.config`; optional explicit URL only if SSRF-safe  
- `gpu_source` = `auto` \| `lhm` \| `nvml`  
- existing `lhm_dll_path` residual; HTTP remains primary for 0.9.5+

Migration for operators:

1. Install LibreHardwareMonitor 0.9.5+  
2. Options → Remote Web Server → Run  
3. File → Hardware → enable CPU (+ GPU)  
4. Confirm admin Extensions → LHM `connected` before relying on package sensors  
5. Only then consider `lhm_required=true`

Docs: `CONFIG.md` + `config.example.ini` + `API.md` in the implementing PR. Semver: new keys compatible = `semver:minor`; default-true required behavior = `semver:major` or opt-in.

---

## 6. Admin / observability

Aligned with admin dashboard §4–§5:

- LHM card: `required` / `requirementMode`, `connection`, `status`, `severity`, tip only when required/recommended and unhealthy  
- Sysinfo card: `lhmRequired` mirrors config/mode, not a hardcoded `true`  
- Prefer `lastSuccessAt`, `sampleAgeMs`, `errorCode` when Slice B+ lands  
- Distinguish `unreachable` vs `reachable_empty` (HTTP up, no usable sensors)

---

## 7. Implementation slices

| Slice | Work |
| --- | --- |
| A | Docs + admin LHM status (admin Slice 1 / 1.1) |
| B | Expand LHM picking for GPU + memory; `gpu_source`; per-metric `source` provenance |
| C | Optional LHM CPU load/clocks with psutil fallback; background poller only |
| D | `lhm_required` + health tips; **audit** before dropping any legacy path; do not drop RAPL/PDH/WMI without evidence “unused” |
| E | Windows detect LHM process + tip only (no implicit start / UAC) |

Tests: fixture `/data.json` / `/metrics` matrix (Intel Package, AMD Tctl/Package, multi-GPU, empty tree, timeout). See `tests/test_system_info.py`.

---

## 8. Acceptance criteria (when scheduled)

- [ ] With LHM running and `gpu_source=lhm`, GPU metrics populate without NVML  
- [ ] With LHM stopped and `lhm_required=false`, non-empty package sensors from other backends ⇒ sysinfo **not** forced degraded solely for LHM absence  
- [ ] With `lhm_required=true` and LHM stopped ⇒ admin + sysinfo degraded with actionable tip; FPS still from iRacing  
- [ ] SSRF allow-list unchanged  
- [ ] No main-loop crash / no probe on async hot path  
- [ ] `CONFIG.md` + `config.example.ini` + `API.md` updated  
- [ ] Tests: parse + provider merge + reachable_empty + vendor fixtures
