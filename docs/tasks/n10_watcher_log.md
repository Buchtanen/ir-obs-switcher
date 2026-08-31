# N10 — Watcher decision log

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §3  
**Depends on:** at least one watch shipped (N3 or N5)  
**Branch hint:** `feat/observer-decision-log`  
**Parallel with:** nothing that owns the same ring buffer module

## Context

Watchers must **log** what they thought happened (kind, evidence, confidence, suppressed-why) so we can tune heuristics without guessing. Mirror commentary `decisions()` — bounded ring, DEBUG tape optional.

## Owns / must not touch

- **Owns:** `race/observer/log.py` (name TBD), attach to RaceObserver ticks, optional `GET` if we already have commentary decisions API (additive), tests  
- **Must not:** new admin dashboard pages (unless a later admin slice is approved), LLM  

## Acceptance criteria

- [ ] Each watch appends: `watch`, `kind`, `emitted` bool, `reason` (`emitted` / `low_confidence` / `cooldown` / `session_policy` / `no_evidence`), `confidence`, `mono_ms`  
- [ ] Bounded ring (default 64)  
- [ ] Fail-soft  
- [ ] DEBUG tape row optional, default off  
- [ ] No per-tick spam at INFO  

## Test plan

- [ ] Unit: classify suppressed → log reason without envelope  
- [ ] Unit: ring drops oldest  
- [ ] If API: schema additive, `schemaVersion` unchanged  

## Docs impact

- [ ] `API.md` if endpoint added  
- [ ] Epic N10 status  

## Config impact

- `race_observer.log_size` default `64`  
- tape only when overlay DEBUG already on  
