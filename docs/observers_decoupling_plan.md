# Observers & decoupling plan (overlay · commentary · race · TTS)

**Status:** P0–P5 on joint umbrella [#179](https://github.com/Buchtanen/ir-obs-switcher/pull/179) (`feat/observers-decoupling-joint-test`)  
**Depends on inventory:** [scenario_coverage_matrix.md](scenario_coverage_matrix.md)  
**Product expansion:** [narrative_observers_epic.md](narrative_observers_epic.md) — reshaped after two reviews vs this umbrella. N-tasks **extend** P0–P5. N9 cover cut. Incident v1 = off_track vs unknown; Speed is motion not classify-primary. Finish = three booleans (`session_checkered` ≠ checkered bit). Opener mutex. Landing order **N1 → N2 → N4 → N8 → N11 A**. Gap-hunt TTS keys live under `[commentary]`.  
**Audience:** architecture / next epic planning

---

## 0. Locked product decisions (answers)

| # | Otázka | Rozhodnutí |
| --- | --- | --- |
| 1 | Incident vs Finish | **Finish** má HUD i commentary. **Incident** má taky commentary (a HUD). Finish zůstává výše v prioritě; incident se nepouští „místo“ finish — po finish / vedle vlastní vysoké prio cesty. |
| 2 | Hard interrupt TTS | **Ano**, INI flag `hard_interrupt` (default **false**, na stream PC zapnout po poslechu). |
| 3 | Filler při max silence 33 s | Mix: (a) **počasí** ze iRSDK v čase (změna temp/vítr/…), (b) **vata z race facts** (leader, pozice hero, …). Strom rozhodne kdy co. |
| 4 | Past-tense / „už to bylo“ | **Jen LLM framing** (žádné samostatné past-tense graph varianty jako primární řešení). |
| 5 | Near field N | **2 ahead + 2 behind** (produktové rozhodnutí). Battle emitter může dál řešit 1+1 pro HUD; RaceObserver drží 2+2 pro story / filler / stream memory. |

### 0.1 Co znamenalo „near field N“ (vysvětlení)

Dnes battle/rival bere prakticky **jedno auto vpředu** a **jedno vzadu** (okamžití sousedé hero) pro HUD.

„N“ = kolik sousedů si RaceObserver **pamatuje a pojmenovává** pro příběh:

| N | Příklad |
| --- | --- |
| **1+1** | „Honí Petra“ / „za ním je Karel“ — dnešní battle HUD |
| **2+2** (locked) | „mezi Petrem a Honzou, za ním Karel a David“ — hustší pole pro filler / stream memory |

Neznamená to sledovat celý grid. Jen okolí hero. **Locked: 2+2** pro RaceObserver.

---

## 1. Posouzení nápadů (stručně)

| Nápad | Verdikt | Proč |
| --- | --- | --- |
| Overlay a commentary jako **dva odběratele** stejného event streamu, ne řetěz | **Souhlas — P0** | Fan-out je schovaný v `OverlayRuntime._emit_from_race` → `_observe_commentary`. Commentary není závislé na renderu widgetu, ale **je** závislé na orchestrátoru HUD. |
| **Race observer** (session + stream kontext, okolní jezdci, příběh, aftermath incidentu) | **Souhlas — jádro epiku** | `RaceContextAnalyzer` už dělá hero↔ahead/behind. Chybí **stavová paměť** a **odvozené eventy**. |
| Incidenty vysoká prio | **Souhlas dle §0** | Finish dál nahoře (HUD+voice). Incident taky voice+HUD; hard interrupt TTS jen když zapnutý flag. |
| **TTS / LLM observer** — defer při busy, past framing LLM, max gap **33 s** | **Souhlas** | Dnes `busy` → ztráta. Defer + TTL + LLM framing až před speak. |
| Doplnit známé mezery | **Ano, po P0–P1** | |

**Rizika:**

- Race observer ≠ LLM loop — LLM jen framing/polish.  
- Defer fronta s TTL.  
- Deferred speak **ne** jako falešný druhý HUD ENTER.  
- Stream paměť bounded.

---

## 2. Cílový tvar (fan-out, ne řetěz)

```text
                    TelemetrySnapshot
                            │
                    RaceContextAnalyzer
                            │
                        RaceState
                     ┌──────┴──────┐
                     │             │
              EventEngine     RaceObserver
              (emitters)      (session/stream memory + weather watch)
                     │             │
                     │    derived CandidateEvent[]
                     └──────┬──────┘
                            ▼
                   Shared Arbitration
                            ▼
                   Accepted EventEnvelope[]
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         OverlaySink   CommentaryPath   Tape/Debug
                       (Director +
                        SpeechScheduler +
                        LLM framing)
```

| Komponenta | Smí | Nesmí |
| --- | --- | --- |
| EventEngine | Emitovat z `RaceState` | Znát HUD / TTS |
| RaceObserver | Paměť; derived eventy; `StoryContext`; weather deltas | Volat TTS |
| Arbitration | Jedna pravda „co se stalo“ | Storytelling text |
| OverlaySink | HUD | Gateovat commentary |
| CommentaryPath | Výběr, defer, hard-interrupt (flag), LLM framing, TTS | Měnit HUD priority |
| OBS SM | Scény | Zůstat oddělená |

---

## 3. RaceObserver

### 3.1 Scope

- **Session:** pozice, near field (**2+2**), battle/pit/incident arcs.  
- **Stream:** agregáty Practice→Quali→Race (bounded).  
- **Weather watch:** iRSDK weather fields over time → event při **významné změně** (temp / wind / skies / precip thresholds), ne každý tick.

### 3.2 Derived (první vlna)

| Derived | Trigger |
| --- | --- |
| `INCIDENT_AFTERMATH` | Po incidentu: stalled vs rolling |
| `BACK_UNDER_WAY` | Auto znovu jede |
| `WEATHER_CHANGE` | Prahová změna počasí |
| `FIELD_FACT` / silence fill | Leader / hero P / gap (pro 33 s watchdog) |
| `RIVAL_REAPPEARS` | Stejný car znovu v near field — **parked / cut from narrative epic v1** (unused in code) |
| `SESSION_WRAP` / `SESSION_PREVIEW` | Hranice session |

### 3.3 Incident vs Finish (hlas + HUD)

| Událost | Overlay | Commentary |
| --- | --- | --- |
| Finish | ano (prio 100) | ano |
| Incident | ano (prio 90) | ano; po/vedle finish dle času; při `hard_interrupt=true` může přerušit probíhající non-finish TTS |

Finish se **nesnižuje** pod incident na HUD.

---

## 4. SpeechScheduler / TTS observer

```text
envelopes → Director.try_build (bez busy reject)
         → SpeechScheduler
              speaking + hard_interrupt? → stop current (ini) / else defer
              park DeferredHeap (prio, ttl)
         → on idle → LLM framing (past) → TTS
         → SilenceWatchdog (>33s) → weather change OR field fact
```

### Config (návrh)

```ini
[commentary.scheduler]
defer_enabled = false
hard_interrupt = false
max_deferred = 8
default_ttl_s = 12
incident_ttl_s = 45
max_silence_s = 33
# past framing = LLM only (uses commentary.llm_* when polish/framing on)
llm_past_framing = true
```

Hard interrupt **default false** (bezpečnější), zapne se na stream PC až po poslechu.

### Silence filler policy (strom)

1. Je pending deferred s TTL? → to nejdřív.  
2. Jinak: došlo k `WEATHER_CHANGE` od last speak? → weather line.  
3. Jinak: `FIELD_FACT` (leader, hero position, gap ahead/behind).  
4. Nic → zůstat tiše (watchdog neforcuje prázdný kec).

---

## 5. LLM framing (past only path)

- Primární „už to bylo“ = **LLM instruction** nad skeletonem (ne past-tense buňky ve graphu jako povinnost).  
- Fail-soft → skeleton bez past, nebo skip pokud by přítomný čas lhal.  
- Framing až **těsně před speak** (ne při defer park).  
- Stále platí: žádný nový dep bez review; používá existující `llm_polish` transport.

---

## 6. Fázovaný plán

### P0 — Decouple fan-out
Peer `EventConsumer`s (`src/irswitch/events/fanout.py`); commentary via `CommentaryEventConsumer`; `_emit_from_race` dispatches speech through `EventFanout` while overlay still publishes wire to the bus. Behavior-preserving; tape parity. **Issue #166.**

### P1 — SpeechScheduler
Defer + TTL + decision codes (`deferred` / `spoken_deferred` / `deferred_expired` / `interrupted` / `silence_no_filler`); `hard_interrupt` ini (default false); silence 33 s (filler → P2); LLM past framing when `llm_polish`; flags default off. **Issue #168.**

### P2 — RaceObserver MVP ✅
`StoryContext` **2+2** near field; weather watch; session reset; slot bindings;
silence filler via `filler_provider` / `filler_formatter` (`WEATHER_CHANGE` /
`FIELD_FACT`). Wired in `OverlayRuntime`. **Issue #170.**

### P3 — Incident aftermath FSM ✅
Derived `INCIDENT_AFTERMATH` (stalled/rolling) + `BACK_UNDER_WAY`; LapDistPct /
surface / tow proxies + `RaceState.speed_mps` motion (N3; LapDistPct fallback;
surface-first classify); template speech via director formatter fallback; fan-out
to commentary. **Issue #172.**  
**Next:** epic **N5 v1** (race yellow/green/checkered as `SESSION_FLAG`). N3 v1 shipped (`off_track` vs `unknown` on INCIDENT; Speed as motion, surface-first classify). Keep `BACK_UNDER_WAY`. No parallel FSM, no `INCIDENT_RECOVERED`.

### P4 — Stream narrative pre/post ✅
`SESSION_WRAP` / `SESSION_PREVIEW` from RaceObserver at session boundaries;
sequenced before `session_briefs` sidecars; gated by `commentary.session_briefs`.
**Issue #175.**  
**Next:** epic **N8** opener mutex + stream TTS (wrap stays gated by `session_briefs`). **N7 recap/rolling deferred.** Wrap must not fire on field checkered after N4.

### P5 — Content gaps ✅
`ATTACK_RANGE` graph node (ENTER TTS); optional mid-pit `PIT_STOPPED` ENTER.
Lane/released stay HUD-only. **Issue #177.**  
**Next:** done for ATTACK_RANGE / PIT_STOPPED. Further copy = epic **N11 wave A** (stream_start / in_car only).

---

## 7. Nedělat v prvním PR

- LLM jako rozhodovač eventů.  
- Hard interrupt bez ini.  
- Neomezený stream transcript.  
- Commentary gated za „widget shown“.  
- Past-tense jako povinná second copy všech graph nodů.

---

## 7.1 Follow-up (post joint-test) — speech queue / busy truth

**Doc:** [commentary_speech_queue_followup.md](commentary_speech_queue_followup.md) · **Issue [#180](https://github.com/Buchtanen/ir-obs-switcher/issues/180)**

**Thin slice (T1–T4) on joint-test branch:** TTS pending depth ≤1 + director busy = estimate **or** `sink.is_busy()`. Epic Gate→Queue→Consumer jen pokud to nestačí.

---

## 8. Docs impact

| Doc | Akce |
| --- | --- |
| `docs/scenario_coverage_matrix.md` | inventory |
| `docs/observers_decoupling_plan.md` | tento plán + locked answers |
| `docs/commentary_speech_queue_followup.md` | post–P1 follow-up: TTS backpressure / busy truth (thin slice first) |
| `docs/narrative_observers_epic.md` | product expansion + N1–N11 task index |
| `CONFIG.md` / example.ini | až P1 (`[commentary.scheduler]`) |
| `COMMENTARY_ENGINE.md` / `API.md` | až implementace |

**Config runtime:** žádná změna defaultů, dokud P1 nepůjde s `defer_enabled=false`, `hard_interrupt=false`.
