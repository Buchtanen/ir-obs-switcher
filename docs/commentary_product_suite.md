# Commentary product suite

**Status:** active prep (build gradually on content branch)  
**Depends on:** [COMMENTARY_ENGINE.md](../COMMENTARY_ENGINE.md), [commentary_content_db_plan.md](commentary_content_db_plan.md), PR #120 (engine) + this content PR  
**Audience:** stream viewers (broadcast voice).

## 0. How we test (your order — source of truth)

```text
1) Commentary-engine branch (#120)
   SAPI → Windows playback device = Virtual Audio Driver (not headphones)
   Test with mock / /commentary speak  ← FIRST

2) Merge / checkout content (this PR: graph texts EN+CS viewer voice)
   Restart irswitchd
   Same SAPI→VAD path, richer lines  ← SECOND

3) Product packages below (P1 → P2 → P3…)
   Live emitters, why-quiet, stream start, …
```

**Mock stays valid** until P1 proves live envelopes fill slots.  
`commentary.enabled` stays **default false**; turn on only on the stream PC under test.

---

## 1. P4 vs Virtual Audio Driver — **no collision**

| Layer | What it is |
| --- | --- |
| **SAPI sink (code, #120)** | `tts_backend=sapi` — Windows Speech API via PowerShell |
| **Virtual Audio Driver (OS)** | Playback **device** routing: SAPI audio goes to a virtual cable OBS can capture, **not** to headphones |
| **P4 (this suite)** | Optional **productization**: status/health API, docs for sink matrix, maybe later OBS-media sink **if** a new dep is approved |

**Conclusion:** VAD is configuration on the gaming PC, not a second sink in code.  
P4 does **not** replace VAD and is **not required** for the mock→content SAPI test.  
P4 later only adds observability / optional alternate sinks.

Document under P4: “Recommended stream PC: set the process/default playback device so SAPI hits Virtual Audio Driver; leave headphones on a different endpoint.”

---

## 2. P6 — deferred

P6 was optional **content polish** (W7 edge wording, Czech gender for past tense, extra density).  

**Not needed now.** Content is already viewer-facing + ~4 lines/cell.  
Revisit only if live listening finds weak nodes or gender becomes a product ask.

---

## 3. Packages we prepare (order)

| # | Package | Now? | Role |
| --- | --- | --- | --- |
| **T0** | Engine mock + SAPI→VAD | **You / #120** | Prove audio path without headphones |
| **T1** | Content graph on same path | **This PR** | Prove texts after restart |
| **P1** | Live readiness matrix + slot proofs | **Prep next** | Know which events actually speak live |
| **P2** | Speak decision log (why quiet) | **Prep after P1** | Debug silence without guessing |
| **P3** | Stream start line | Later | Go-live beat |
| **P4** | Sink status / docs (VAD note) | Later / light | Does not block T0–T1 |
| **P5** | Voice budget gate | Later | Anti-chatter under race load |
| **P6** | Content polish | **Deferred** | — |

### T0 / T1 checklist (manual)

- [ ] T0: `#120` running, SAPI → VAD, `/commentary` **Mluvit na serveru** audible in OBS (not cans)
- [ ] T0: `commentary.enabled=true` + mock/live feed speaks a mock-4 style beat into VAD
- [ ] T1: content branch/PR merged or checked out, **restart**, same VAD path
- [ ] T1: CS or EN locale matches `overlay.language`; battle/pit/in-car lines sound viewer-facing

### P1 — Live readiness

| AC | Detail |
| --- | --- |
| P1.1 | Doc table: node → live-backed / partial / structure-only |
| P1.2 | Unit proofs: real-shaped envelopes bind slots (no `slot_unbound` silence) |
| P1.3 | `/commentary` shows enable + language + backend |
| P1.4 | Manual: one live battle or pit beat into VAD after enable |

### P2 — Why quiet

| AC | Detail |
| --- | --- |
| P2.1 | Director ring-buffer of decisions + reason codes |
| P2.2 | `GET /api/commentary/decisions` |
| P2.3 | List on `/commentary` |
| P2.4 | Codes in API.md |

Codes: `disabled`, `busy`, `global_cooldown`, `node_cooldown`, `no_node`, `hr_gate`, `no_variant`, `slot_unbound`, `validator_reject`, `spoken`.

### P3 — Stream start (later)

Typed `stream_start` node + OBS or HTTP trigger; viewer voice; fail-soft.

### P4 — Sink productization (later, light)

Docs + status only first. **VAD remains OS routing.** No new dep unless approved.

### P5 — Budget (later)

`min_priority_live` / speak_priority gate; needs P2 reason `budget_skip`.

---

## 4. Non-goals

- Free-form LLM at race time  
- Neo4j  
- Replacing SAPI→VAD with a cloud TTS  
- Blocking the race loop on TTS  

---

## 5. Prep status (this branch)

| Item | Status |
| --- | --- |
| Content DB EN+CS viewer voice | Done |
| Product suite aligned to T0→T1→P1→P2 | Done |
| P1 live node matrix | Done — matrix + adapters for incident/final_lap/finish + rival_threat gap/label |
| P2 decision log | Done — director ring + `/api/commentary/decisions` + `/commentary` panel |
| P3–P5 | Queued |
| P6 | Deferred |

---

## 6. Config impact

| When | Keys |
| --- | --- |
| T0–T1 | existing `commentary.*` only |
| P2 | optional `commentary.decision_log_size` (default 32) |
| P3 | `commentary.stream_start_enabled` |
| P5 | `commentary.min_priority_live` |
| P4 | none for VAD (OS); maybe status-only API |
