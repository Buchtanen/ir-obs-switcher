# Commentary product suite

**Status:** product backlog / decision doc (runtime still Phase 0 + content DB)  
**Depends on:** [COMMENTARY_ENGINE.md](../COMMENTARY_ENGINE.md), [commentary_content_db_plan.md](commentary_content_db_plan.md), PR #120 / #127  
**Audience:** stream viewers (broadcast voice). Content DB is filled; this suite is what makes it a **product**, not only a testable engine.

## 0. Current baseline (already shipped / in PR)

| Piece | State |
| --- | --- |
| Post-arbitration director + sequence graph | Done |
| EN+CS variants, viewer voice, ~4 lines/cell | Done (content) |
| TTS SAPI / espeak / null + `/commentary` test page | Done |
| `commentary.enabled` default **off** | Done |
| Live Event Engine → speech | Wired; needs real metrics/emitters + enable |

**While testing with mock:** keep `enabled=false` in production configs; use `/commentary` + unit tests. Product slices below must stay fail-soft and not break the race loop.

## 1. Product suite packages

Ship as **separate PRs** (one package ≈ one reviewable slice). Order is the recommended path from “engine works” → “stream-ready product”.

---

### P1 — Live readiness (must before calling it live)

**Goal:** Spoken lines fire reliably from real session, not only `/commentary` speak button.

| AC | Detail |
| --- | --- |
| P1.1 | Document which graph nodes are **live-backed** vs **structure-only** (emitter exists + metrics fill slots) |
| P1.2 | For each live-backed node: at least one integration/unit path proves `choose_filled_line` gets full slot bindings from real envelope shapes |
| P1.3 | Dashboard/config: clear enable + locale (`overlay.language`) + TTS backend status on `/commentary` |
| P1.4 | Manual checklist: enable → in-car / lap / pit / one battle beat audible on Windows SAPI |

**Out:** new sinks, stream_start, WS debug.  
**Config:** none new (use existing `commentary.*`).  
**Docs:** COMMENTARY_ENGINE live node matrix; CONFIG note “enable for live”.  
**Semver:** patch or none if docs-only matrix; minor if API status fields grow.

---

### P2 — Speak decision log (“why quiet?”)

**Goal:** Operator/streamer sees why a beat did not speak (cooldown, busy, empty binding, disabled, wrong phase, HR gate).

| AC | Detail |
| --- | --- |
| P2.1 | Director records last N decisions: `spoken` \| `skipped` + reason code |
| P2.2 | Expose via `GET /api/commentary/decisions` (and optionally WS topic) |
| P2.3 | `/commentary` page shows last decisions (no secrets) |
| P2.4 | Reason codes are stable enum (documented in API.md) |

**Codes (minimum):** `disabled`, `busy`, `global_cooldown`, `node_cooldown`, `no_node`, `hr_gate`, `no_variant`, `slot_unbound`, `validator_reject`, `spoken`.  
**Config:** optional `commentary.decision_log_size` (default 32).  
**Docs:** API.md + COMMENTARY_ENGINE.  
**Semver:** minor.

---

### P3 — Stream start line

**Goal:** One short viewer-facing line when the stream goes live (OBS / app stream state), typed templates + irsdk slots — **not** free-form LLM.

| AC | Detail |
| --- | --- |
| P3.1 | New graph node `stream_start` (commentary-only event type, e.g. `STREAM_START`) |
| P3.2 | Trigger source agreed: OBS websocket stream state **or** explicit HTTP `POST /api/commentary/stream-start` for tests |
| P3.3 | Slots only from known fields (track/car/session labels already available — no invented grid) |
| P3.4 | EN+CS variants authored (viewer voice); validator green |
| P3.5 | Fail-soft if OBS down; no main-loop block |

**Config:** `commentary.stream_start_enabled` (default true when commentary enabled, or separate flag).  
**Docs:** COMMENTARY_ENGINE + CONFIG + API.  
**Semver:** minor.  
**Note:** structure PR before text fill; content can reuse VOICE_VIEWER rules.

---

### P4 — Output sink productization

**Goal:** Reliable audible path on the streaming PC beyond “hope SAPI works”.

| AC | Detail |
| --- | --- |
| P4.1 | Documented sink matrix: `sapi` / `espeak` / `null` (+ optional future `obs_media` **only if dep approved**) |
| P4.2 | Health: `/api/commentary/status` reports backend, last error, last utterance |
| P4.3 | Optional: ducking / don’t speak while mic hot — **only if** explicit product ask |
| P4.4 | No new dependency unless separately approved |

**Default path:** keep stdlib SAPI/espeak. OBS media = separate approval.  
**Semver:** minor if status/API grows; none if docs-only.

---

### P5 — Voice budget (anti-chatter)

**Goal:** Under busy race, speech stays sparse and predictable.

| AC | Detail |
| --- | --- |
| P5.1 | Global + per-node cooldowns remain time-based (already) |
| P5.2 | Optional budget tiers P0–P5 mapped from `speak_priority` bands (config) |
| P5.3 | When overlay arbitration is saturated, commentary still fail-soft (never blocks HUD) |
| P5.4 | Decision log records `budget_skip` |

**Config:** e.g. `commentary.min_priority_live` (int, default 0 = all).  
**Semver:** minor.

---

### P6 — Content polish (non-blocking)

| Item | Note |
| --- | --- |
| W7 sequence polish | Edge-aware wording (hunting→…→battle_won) |
| CS gender | Past-tense agreement; needs locale gender setting — park unless requested |
| Variant density | Already ~4/cell (752 lines); further density only on weak nodes |

**Semver:** none / patch (content-only).

---

## 2. Recommended ship order

```text
P1 Live readiness  →  P2 Decision log  →  P3 Stream start  →  P4 Sink status  →  P5 Budget  →  P6 Polish
```

**Parallel-safe:** P6 content polish can run beside P2–P4 (content-only).  
**Do not parallelize:** P2 director changes + P5 budget (same `director.py`).

## 3. Explicit non-goals (suite-wide)

- Free-form LLM at race time  
- Neo4j / external graph DB  
- Mixing OBS scene-switcher policy into commentary  
- Changing Event Engine math / overlay HUD tokens as speech  
- New TTS SaaS / cloud voices without dependency review  

## 4. Mock vs product

| Mode | What you do |
| --- | --- |
| **Engine test (now)** | Mock/content DB + `/commentary` + unit tests; `enabled=false` in real configs |
| **Product live** | P1 done + `enabled=true` on stream PC; P2 strongly recommended before public use |
| **Stream complete** | P1–P4 (P3 if you want go-live line) |

## 5. Decision checklist (for you)

Pick one:

- [ ] **A.** Stay on engine test — no product PRs yet  
- [ ] **B.** Start **P1** (live readiness matrix + slot proof)  
- [ ] **C.** Start **P1+P2** (live + why-quiet log) — recommended product MVP  
- [ ] **D.** Full suite roadmap P1→P5 as sequential PRs  

Default recommendation: **C**.

## 6. Docs / config impact map

| Package | Docs | Config |
| --- | --- | --- |
| P1 | COMMENTARY_ENGINE, maybe API status | none / status only |
| P2 | API.md, COMMENTARY_ENGINE, `/commentary` UI | `decision_log_size` |
| P3 | COMMENTARY_ENGINE, CONFIG, API, graph JSON | `stream_start_enabled` |
| P4 | COMMENTARY_ENGINE, API | none or status-only |
| P5 | COMMENTARY_ENGINE, CONFIG | `min_priority_live` |
| P6 | content plan / graph only | none |
