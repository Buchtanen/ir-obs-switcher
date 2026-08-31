# N3 — Incident classifier, chain, aftermath, recovered

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §2.3, §3.4  
**Depends on:** N1, P3 aftermath FSM ([#174](https://github.com/Buchtanen/ir-obs-switcher/pull/174) / issue #172) already on the stack  
**Blocks:** N11 incident copy, N10 log  
**Branch hint:** `feat/incident-classifier-arc`  
**Extends:** P3 — do not replace `INCIDENT_AFTERMATH` / `BACK_UNDER_WAY`

## Context

Today `IncidentEmitter` only sees `PlayerCarMyIncidentCount` delta ≥ `incident_min_delta`. P3 already adds stalled/rolling aftermath without Speed. This task adds **kinds**, **chains**, and richer **recovered** on top of that FSM.

iRSDK has **no incident-type enum**. This task is a documented heuristic + FSM.

## Owns / must not touch

- **Owns:** new `src/irswitch/race/observer/incident.py` (or equivalent under `race/`), derived events from RaceObserver, commentary-only envelopes + adapter metrics `branch` / `confidence` / `chain`, tests  
- **May adjust:** `race/aftermath.py` / observer wiring **after** P4 is on master; keep existing event names  
- **Must not:** rewrite P3 from scratch, graph *texts* (N11), flag bits (N5), finish (N4)  

## Acceptance criteria

- [ ] On incident increment, classify `off_track` | `lost_control` | `contact_car` | `contact_object` | `unknown` with `confidence`  
- [ ] Nearby-car gate uses existing dist / lap-pct (thresholds in settings, documented)  
- [ ] Chain: lost-control and/or off-track within window then contact → `metrics.chain=true`, one `correlation_id`  
- [ ] Aftermath FSM: after incident, if speed below crawl for `T_stop` or slow band → not recovered; when speed ≥ roll for `T_hold` → `INCIDENT_RECOVERED` / `BACK_UNDER_WAY`  
- [ ] Tow (`PlayerCarTowTime > 0`) and ESC teleport cancel the arc without “recovered”  
- [ ] Practice/Quali: recovered **optional / quieter** (default: do not speak recovered in P/Q)  
- [ ] Race: recovered speaks (scheduler still applies)  
- [ ] Generic `incident` node still works if branch unbound (N2 fallback)  
- [ ] Fail-soft; unit tests with fake clock cover each kind + chain + recovered + tow  
- [ ] Feature flag default preserves old single `incident` speak until classify is on  

## Test plan

- [ ] Unit: off-track surface vs count tick → `off_track` high confidence  
- [ ] Unit: nearby car + tick → `contact_car`  
- [ ] Unit: no neighbor + tick + on-track → `contact_object` or `unknown` (assert documented choice)  
- [ ] Unit: yaw-rate spike then tick → `lost_control` then chain to contact  
- [ ] Unit: speed 0 for N s then roll → recovered once; no double emit  
- [ ] Unit: tow during aftermath → no recovered  
- [ ] Existing `IncidentEmitter` tests: no double TTS when flag off  

## Docs impact

- [ ] Epic §2.3 confidence table stays accurate  
- [ ] `COMMENTARY_ENGINE.md` new event types  
- [ ] `CONFIG.md` + `config.example.ini` if flags/thresholds added  
- [ ] `docs/scenario_coverage_matrix.md` incident row  

## Config impact

Changed keys (proposal):

- `race_observer.incident_classify` (default `false` until trusted)  
- crawl / roll speed thresholds (m/s) and window seconds  

Migration: off → today’s count-only incident.
