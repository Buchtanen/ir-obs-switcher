# Commentary speech pipeline — follow-up design

**Status:** **thin slice implemented** on `feat/observers-decoupling-joint-test` / PR #179 — **[#180](https://github.com/Buchtanen/ir-obs-switcher/issues/180)**  
**Parent plan:** [observers_decoupling_plan.md](observers_decoupling_plan.md) (P1 SpeechScheduler)  
**Related:** [commentary_llm_skeleton_poc.md](commentary_llm_skeleton_poc.md), `CONFIG.md` `[commentary.scheduler]`  
**Critical review:** incorporated below (§5); reviewer agent 2026-08-31  

---

## 1. Problem (today)

Current path:

```
events → Director (gate + SpeechScheduler ≤1 skeleton)
      → ProcessTtsSink.enqueue(skeleton)
           → [TTS worker queue] → LLM polish → SAPI/espeak
```

| Layer | Role (thin slice) |
| --- | --- |
| `CommentaryDirector` | Priority, busy = **estimate OR** `sink.is_busy()`, global cooldown, graph pick, defer ≤1 |
| `SpeechScheduler` | Park **at most one** best skeleton while “busy”; TTL; drop lower prio; **no sequential drain** of deferred |
| `ProcessTtsSink` | Serial worker; **at most one waiter** (replace-by-priority); polish then speak |

**Former failure mode (fixed in thin slice):** director free while TTS still had a deep queue → backlog under the scheduler. LLM still only polishes the in-flight item.

Locked product rules that must stay true:

- Race loop never blocks on HTTP/SAPI.
- LLM is style polish only (not event decider).
- Past framing for deferred lines is LLM instruction, applied **at speak time** ([observers §5](observers_decoupling_plan.md)).
- Hard interrupt is opt-in INI; best-effort (does not kill in-flight PowerShell today).

---

## 2. Target architecture (epic vision)

```
events
  → Gate / scoring          # director: phase, briefs, sector, HR, graph, priority
  → SpeakIntent slot         # ≤1 best + TTL + drop low (today’s SpeechScheduler policy)
  → Speech consumer          # single owner of “what is speaking”
       → optional LLM polish # winner only; past_framing resolved here
       → TTS (SAPI/espeak)   # no second unbounded queue
```

### 2.1 Responsibilities

| Component | Owns | Does not own |
| --- | --- | --- |
| **Gate** (`Director._consider` + flags) | Whether an envelope becomes a candidate utterance | Threads, HTTP, audio |
| **SpeakIntent slot** | At most one parked/ready intent; replace-by-priority; TTL | Polish text, duck |
| **Speech consumer** | Dequeue one intent → polish → speak → signal idle | iRacing / fan-out / HUD |
| **RaceObserver / fillers** | Derived envelopes into fan-out → gate | Direct TTS enqueue |

### 2.2 Ordering rules

1. Evaluate **before** entering the speak slot (current director gates).
2. Never drain a backlog of intents one-by-one after idle (already scheduler policy).
3. LLM runs **only** on the intent about to be spoken (winner), not on dropped candidates.
4. `past_framing` is set when the consumer starts work on a deferred intent (age check — see §5).
5. Interrupt: drop slot + clear consumer pending; duck restore; in-flight SAPI remains best-effort unless a later epic adds kill.

---

## 3. Thin slice (preferred next patch — not full redesign)

Stability > elegance. Fix the dual-queue bug **without** a new EventFanout peer or renaming the whole pipeline.

| # | Change | Effect |
| --- | --- | --- |
| T1 | **TTS pending depth ≤ 1** (0 waiters + 1 speaking, or replace-by-priority on enqueue) | No sequential drain under the sink |
| T2 | **Observed busy** feedback: director busy if `sink.speaking or sink.pending > 0` (estimate only as upper bound / diagnostics) | Stops false-idle enqueue storms |
| T3 | Keep `SpeechScheduler` as the only park (≤1 + TTL + drop low) | Policy already matches product |
| T4 | Keep LLM in worker **on the single in-flight item**; polish **before** duck (already true) | Fail-soft unchanged |

**Out of thin slice:** new “SpeechObserver” type, moving polish off the worker thread, killing SAPI mid-utterance, config redesign.

### 3.1 Acceptance criteria (thin slice)

- [x] With `defer_enabled=true`, rapid high-rate envelopes do not produce a multi-item TTS backlog (instrument or test with fake slow speak).
- [x] Decision tape still uses `deferred` / `spoken_deferred` / `deferred_dropped` / `deferred_expired` / `busy` / `interrupted`.
- [x] `hard_interrupt=true` still clears sink pending + sets interrupt flag; duck restores.
- [x] `llm_polish=false` path unchanged latency profile (no extra waits).
- [x] Unit tests do not require real SAPI; `NullTtsSink.force_busy` + `ProcessTtsSink.is_busy` / depth≤1 tests.

### 3.2 Config (thin slice)

Prefer **no new keys** first (`busy_mode=observed` implicit when sink supports it). If needed later:

```ini
[commentary.scheduler]
# existing keys unchanged
# optional later: busy_mode = estimate | observed
```

---

## 4. Epic slice (only after thin slice + joint-test content stable)

Rename/clarify ownership only if T1–T4 are insufficient:

1. Formal `SpeakIntent` dataclass (skeleton text + meta + parked_at + priority).
2. Consumer API: `try_pull() → polish → speak → on_idle` with explicit cancel contract.
3. Age threshold for past framing (e.g. skip past or skip speak if parked longer than N×TTL).
4. Docs: `COMMENTARY_ENGINE.md` pipeline diagram; API decision log fields if any.

**Do not** put LLM on the race/async loop. **Do not** let RaceObserver enqueue TTS directly.

---

## 5. Critical evaluation (summary)

### Keep

- Diagnosis of dual-queue + estimate busy is correct.
- ≤1 best / TTL / drop low / no sequential deferred drain is the right policy (already in scheduler).
- Gate stays on director; fillers stay on fan-out → director.
- Non-blocking enqueue + serial audio worker.

### Hard risks if jumping straight to “full redesign”

| Area | Risk |
| --- | --- |
| Source of truth for busy | Without observed busy, renaming queues is cosmetic |
| hard_interrupt | Still does not kill in-flight SAPI/LLM HTTP |
| Ducking | Must remain single consumer; two speak paths → stuck mute |
| session_briefs / ENTER_CAR | Max-1 slot without priority vs brief policy can drop intros |
| past_framing | Late dequeue of old park → wrong “moments ago”; need age rule |
| Testability | Real busy feedback needs fake sink clocks — avoid flaky CI |
| Scope | Full consumer epic on #179 joint branch fights content/test signal |

### Verdict

| Option | Decision |
| --- | --- |
| Full Gate→Queue→Consumer→LLM→TTS now | **Park** (underspecified ownership/cancel/backpressure) |
| Thin slice T1–T4 | **Ship as follow-up** after #179 joint test (patch/minor) |
| Epic redesign | **Only if** thin slice still leaves dual-path bugs |

---

## 6. Migration notes

- Default INI stays safe (`defer_enabled` / `hard_interrupt` opt-in).
- No change to graph content or RaceObserver envelopes in the thin slice.
- Preserve decision reasons for GR/debug tape compatibility.
- Thin slice landed: `COMMENTARY_ENGINE.md` TTS notes + this doc status → `implemented (thin)`.

---

## 7. Docs / work-item checklist

When opening the follow-up issue/PR:

```markdown
## Context
TTS worker queue can backlog under estimated busy; LLM polish is fine on winner but dual-queue fights SpeechScheduler ≤1 policy.

## Acceptance criteria
- [ ] Thin slice T1–T4 from docs/commentary_speech_queue_followup.md
- [ ] Tests: backlog / observed busy / interrupt / llm off

## Test plan
- [ ] Unit: fake sink pending/speaking
- [ ] Manual: defer_enabled + llm_polish on stream PC — no stacked calls after battle burst

## Docs impact
- [ ] docs/commentary_speech_queue_followup.md (status)
- [ ] COMMENTARY_ENGINE.md
- [ ] CONFIG.md only if new keys

## Config impact
None for thin slice (unless busy_mode added).
```

---

## 8. Pointers in code (as of joint-test branch)

- Director busy + defer: `src/irswitch/commentary/director.py` (`tick`, `_park_ranked`, `_speak_prepared`)
- Slot policy: `src/irswitch/commentary/scheduler.py`
- Worker polish+speak: `src/irswitch/commentary/tts.py` (`ProcessTtsSink._speak`)
- Polish transport: `src/irswitch/commentary/polish.py`
