# Observers & decoupling plan (overlay · commentary · race · TTS)

**Status:** P0–P5 merged via [#179](https://github.com/Buchtanen/ir-obs-switcher/pull/179) (2026-09-01). Narrative landing continues on `master` (#181). **Commentary Director V2 / N12 async isolation is specified, not implemented.**
**Post-N12 refinement:** [live data channels and adaptive sampling](live_data_channels_sampling_spec.md) specifies shared live-state access and multi-rate/change-driven sampling; implementation begins only after N12 lands on `master`.
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

### 2.1 Current gap after P0

P0 changed the naming and failure boundary, but not the execution model:

- `OverlayRuntime` still owns telemetry sampling, `RaceObserver`, event arbitration,
  overlay publication, `CommentaryDirector`, scheduler, and TTS wiring;
- `EventFanout.emit()` calls consumers synchronously in registration order;
- overlay wire publication is awaited before commentary dispatch;
- commentary reads `OverlayBus.bio` and RaceObserver filler callbacks through
  `OverlayRuntime`;
- `ENTER_CAR`, session briefs, stream start, and some derived envelopes can call
  the commentary path directly instead of entering one shared accepted stream;
- RaceObserver-derived envelopes are drained after the engine tick and bypass
  shared arbitration.

The current code isolates exceptions, but a slow consumer still occupies the
same race tick and overlay remains the composition root for commentary. That is
not the independent model required for Commentary Director V2.

### 2.2 Commentary Director V2 — independent async consumers

Locked product invariant: **one race observation pipeline, one accepted event
stream, two independent consumers**. Overlay and commentary receive the same
accepted event identity and sequence, but neither waits for the other to finish.

```text
 iRSDK / OBS edges / bio / configured watches
                    │
                    ▼
        RacePipeline + one RaceObserver
   (RaceState, EventEngine, watch modules)
                    │ candidates
                    ▼
       shared arbitration + identity stamp
                    │ AcceptedEventBatch
                    ▼
             AsyncEventFanout
             enqueue both first
              ┌─────┴─────┐
              ▼           ▼
     overlay_queue   commentary_queue
              │           │
              ▼           ▼
      OverlayConsumer   CommentaryConsumer
      async task A      async task B
      HUD/bus/tape      Director/scheduler/TTS
```

Execution rules:

1. There is exactly one telemetry read, `RaceContextAnalyzer`, `EventEngine`,
   `EventManagerV2`, and `RaceObserver` instance for the live pipeline.
2. RaceObserver owns story memory and runs multiple deterministic watch modules;
   it emits candidates only. It does not call overlay, director, scheduler, or
   TTS.
3. Engine and RaceObserver candidates enter the same arbitration/stamping step.
   A commentary-only audience marker may make overlay ignore an event, but both
   consumers still observe the same accepted envelope and event id.
4. Fan-out enqueues an immutable/isolated batch to **both** queues before either
   consumer work is awaited. It never executes consumer callbacks inline.
5. Ordering is guaranteed inside each consumer by `(session_id, sequence)`.
   Completion order between overlay and commentary is deliberately undefined.
6. Each consumer owns its state, reset handling, queue policy, errors, and
   status. No import or callback may form `overlay -> commentary` or
   `commentary -> overlay`.
7. The first slice uses two supervised `asyncio.Task` workers in the single
   Windows service process. The message contract must be serializable and share
   no mutable state so either worker can later move behind an IPC transport into
   a separate OS process without changing producers or event semantics.

Shared arbitration owns factual acceptance, dedupe, correlation, and identity;
it does **not** merge HUD presentation budget with speech budget. Overlay hold /
priority and CommentaryScheduler defer/TTL remain consumer-local decisions after
dequeue. A candidate valid for any declared audience becomes one accepted event
that both consumers can account for.

`AcceptedEventBatch` must carry at least stream/batch sequence, `session_id`,
accepted monotonic time, frozen accepted-event records, and the exact frozen
read-only context snapshot used for slot/HR decisions. `EventEnvelope` is
currently mutable (`stamp()` and mutable `metrics`); the fan-out boundary uses
the canonical freeze contract in N12 so one consumer cannot change what the
other sees.

Continuous `RaceState`/bio data is not an overlay-owned backchannel. Publish a
read-only, versioned context snapshot (or an explicit state message) from the
producer lane. Overlay uses it for HUD state; commentary uses only the fields
needed for HR, slots, and story context.

### 2.3 Queue, overload, and lifecycle contract

- One bounded queue per consumer; no shared work queue, because a shared queue
  would load-balance events instead of broadcasting them.
- Healthy-path proof: both consumers receive the exact same event ids and
  sequences. Consumer-local filtering happens only after dequeue.
- The producer never awaits TTS, WebSocket clients, overlay rendering, or a
  consumer queue becoming free.
- Overflow is deterministic and visible. Preserve `FINISH`, `INCIDENT`, opener,
  `RESULT`, and `EXIT`; coalesce stale `ACTIVE`/`UPDATE` by dedupe key before
  evicting a lower-priority item. Commentary may expire an utterance by its
  event-time TTL, never silently reinterpret it as current.
- Record per consumer: queue depth/capacity, last enqueued and processed
  sequence, lag milliseconds, coalesced/dropped totals and reasons, task state,
  last error, and restart count.
- A consumer exception is caught inside that worker and cannot cancel the
  producer or sibling. Restart uses bounded backoff. Repeated failure degrades
  only that consumer.
- Startup creates both queues and workers before the producer starts publishing.
  Shutdown stops publishing, drains only within a bounded deadline, cancels
  both workers, awaits them, then restores TTS ducking / closes tape.
- Session reset and config reload are typed, ordered control messages outside
  `EventEnvelope`. Hidden cross-object reset callbacks are not allowed across
  consumer ownership.

All producer and consumer timing uses monotonic time. Queue delay is measured;
it is not added to cooldowns as if the event occurred later.

---

## 3. RaceObserver

### 3.1 Scope

- **Session:** pozice, near field (**2+2**), battle/pit/incident arcs.  
- **Stream:** agregáty Practice→Quali→Race (bounded).  
- **Weather watch:** iRSDK weather fields over time → event při **významné změně** (temp / wind / skies / precip thresholds), ne každý tick.
- **Driver facts:** session-scoped profil hero + 2+2 soupeřů podle `CarIdx`:
  iRating, Safety Rating/licence, vůz a jednou zachycená startovní pozice.
  Národnost zůstává prázdná, dokud nebude doložený zdroj; z klubu ani jména se
  neodhaduje.

### 3.2 Driver fact ledger a textový kontext

`DriverInfo.Drivers[]` se při změně SessionInfo normalizuje do bounded mapy
`CarIdx -> DriverProfileSnapshot`. Změna `UserID` na stejném `CarIdx` je výměna
jezdce a zahodí starý profil. RaceObserver pak v každém frozen ContextSnapshotu
publikuje profil hero a pouze relevantních 2+2 soupeřů; commentary je váže podle
subject/target identity konkrétního accepted eventu.

```text
iRacing read
  -> RaceObserver ledger + near field
  -> frozen ContextSnapshot N
  -> candidates / arbitration
  -> AcceptedEventBatch s vloženým snapshotem N
  -> commentary queue
  -> identity + freshness gate
  -> plně vázaná věta, nebo slot-free fallback/skip
```

Commentary nesmí číst živý RaceObserver ani doplňovat starý event z nového
soupeře. Embedded snapshot je pravda v čase eventu; `latest_context` smí pouze
zrušit binding při změně session/identity nebo u relation starší než 3 s.
Změna jezdce zvýší `identity_epoch`; `SessionReset` zahodí deferred řeč staré
session. Selhání končí slot-free variantou nebo důvodem `driver_context_stale`,
nikdy domyšleným jménem či profilem.

| Fakt | Zdroj |
| --- | --- |
| iRating | `DriverInfo.Drivers[].IRating` |
| Safety Rating | `DriverInfo.Drivers[].LicString` |
| Vůz | `DriverInfo.Drivers[].CarScreenName`, fallback `CarScreenNameShort` |
| Startovní pozice | jednorázový snapshot `CarIdxClassPosition[]` / `CarIdxPosition[]` před green; první green sample jen diagnostikovaný fallback |
| Národnost | **není doložená v aktuálním iRSDK SessionInfo kontraktu**; `null`, žádná inference z `ClubName` |

Textový graph zůstává broadcast/3. osoba. Profilový detail se používá střídmě:
typicky jeden fact na větu, minimálně 70 % řádků v dotčené buňce bez profile
slotu. iRating/SR nesmí být interpretace talentu nebo čistoty; národnost nesmí
vést ke stereotypu. Přesné sloty, ukázky a implementační handover jsou v
[`commentary_extension_handover.md`](commentary_extension_handover.md#driver-fact-extension-needs-engineering).

### 3.3 Souběžný útok vpředu a obrana zezadu

`hunting` a `hunted` jsou dva nezávislé vztahy, ne přepínač jednoho módu.
RaceObserver/EventEngine drží současně:

```text
front: hero stahuje soupeře vpředu
rear:  soupeř zezadu stahuje hero

front + rear ACTIVE
  -> oba parent eventy zůstávají aktivní
  -> třetí composite BATTLE_FOR_POSITION / two_front_battle
```

Dedupe a coalescing musí obsahovat směr + `targetCarIdx` + relation epoch.
Společný `battle` channel ani vyšší priorita nesmí jeden směr vytlačit. Composite
nese `front_target_*`, `front_gap`, `rear_target_*`, `rear_gap` a vlastní
correlation se dvěma identitami. Když jedna strana skončí, composite končí a
druhá parent větev pokračuje bez nového ENTER.

Pro hlas se při společném ENTER preferuje jedna věta z explicitní větve
`two_front_battle`; parent rozhodnutí se pouze označí `covered_by_two_front`.
Stav parentů, replay ani pozdější UPDATE/EXIT se nemažou. Slot-light fallback
musí umět říct, že hero útočí dopředu a současně hlídá pozici zezadu, i když
chybí obě jména. `BATTLE_FOR_POSITION` se nesmí dál vydávat za
`side_by_side`, protože jde o jinou geometrii souboje.

Přesný payload, navržené hrany a EN/CS texty:
[`commentary_extension_handover.md`](commentary_extension_handover.md#two-front-battle-branch-needs-engineering).

### 3.4 Derived (první vlna)

| Derived | Trigger |
| --- | --- |
| `INCIDENT_AFTERMATH` | Po incidentu: stalled vs rolling |
| `BACK_UNDER_WAY` | Auto znovu jede |
| `WEATHER_CHANGE` | Prahová změna počasí |
| `FIELD_FACT` / silence fill | Leader / hero P / gap; vzácně jeden nevyužitý driver fact (pro 33 s watchdog) |
| `RIVAL_REAPPEARS` | Stejný car znovu v near field — **parked / cut from narrative epic v1** (unused in code) |
| `SESSION_WRAP` / `SESSION_PREVIEW` | Hranice session |

### 3.5 Incident vs Finish (hlas + HUD)

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
3. Jinak: `FIELD_FACT` (leader, hero position, gap ahead/behind; volitelně jeden
   driver fact, pokud jej per-driver cooldown ještě nepoužil).
4. Nic → zůstat tiše (watchdog neforcuje prázdný kec).

---

## 5. LLM framing + situační kontext

- Primární „už to bylo“ = **LLM instruction** nad skeletonem (ne past-tense buňky ve graphu jako povinnost).  
- Fail-soft → skeleton bez past, nebo skip pokud by přítomný čas lhal.  
- Framing až **těsně před speak** (ne při defer park).  
- Stále platí: žádný nový dep bez review; používá existující `llm_polish` transport.

LLM nedostává jen skeleton, ale bounded `SITUATION FACTS` ze stejného frozen
ContextSnapshotu jako event: aktuální/dokončené kolo, známý celkový počet,
remaining laps/time, upstream fázi `opening/middle/closing/final_lap/checkered/
finished`, pozici a pouze použité hero/target facts. Nedostává raw telemetry,
celý roster ani live RaceObserver.

```text
ContextSnapshot N + accepted event
  -> fully bound skeleton
  -> 3 s freshness gate pro current lap/phase
  -> FACT LOCK + SITUATION FACTS + max 1 povolená situační fráze
  -> LLM polish
  -> čísla/fáze post-validation
  -> TTS, nebo původní skeleton
```

Fázi počítá RaceObserver deterministicky (20 % opening, 20–70 % middle, od
70 % closing; final/checkered/finished mají explicitní override). LLM nesmí
domyslet final lap ani nové číslo kola. Starý deferred event zůstává v minulém
kontextu; nejnovější snapshot jej smí zneplatnit, ne přepsat.

Director sestaví allowlist přesných lokalizovaných dodatků (`lap 12`,
`12. kolo z 30`, `middle phase`). Když 90s situační cooldown dovolí obohacení,
LLM smí použít nanejvýš jeden; jinak dostane `NONE`. Tím jsou data v promptu
prakticky použitelná, ale model nemůže slepit do každé věty kolo, fázi i zbytek.

Pro orientaci diváka se do `FIELD_FACT` navrhují sloty `current_lap`,
`lap_context`, `race_phase`, `remaining_context`. Změna fáze nebo 120 s bez
zmínky o kole/fázi připraví low-priority fact; battle/incident/pit/final/finish
jej mohou odsunout. Přesný kontrakt a texty:
[`commentary_extension_handover.md`](commentary_extension_handover.md#situation-and-llm-context-needs-engineering).

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
**Next:** N5 v1 shipped (`SESSION_FLAG` yellow/green/checkered). Stop for live listen.

### P4 — Stream narrative pre/post ✅
`SESSION_WRAP` / `SESSION_PREVIEW` from RaceObserver at session boundaries;
sequenced before `session_briefs` sidecars; gated by `commentary.session_briefs`.
**Issue #175.**  
**Next:** epic **N8** opener mutex + stream TTS (wrap stays gated by `session_briefs`). **N7 recap/parade pad** is opt-in `race_observer.grid_story` (not `session_briefs`). Wrap must not fire on field checkered after N4.

### P5 — Content gaps ✅
`ATTACK_RANGE` graph node (ENTER TTS); optional mid-pit `PIT_STOPPED` ENTER.
Lane/released stay HUD-only. **Issue #177.**  
**Next:** done for ATTACK_RANGE / PIT_STOPPED. Further copy = epic **N11 wave A** (stream_start / in_car only).

### V2 / N12 — Commentary Director async isolation (specified)

Extract the race/event producer from `OverlayRuntime`; make overlay and
commentary independently supervised async consumers with separate bounded
queues and identical accepted event identity. Unify direct sidecars and
RaceObserver-derived events behind the same arbitration/fan-out boundary.
Detailed handover and acceptance criteria: [N12](tasks/n12_async_consumers.md).
The linked critical review is incorporated in N12's binding implementation
appendix (freeze, derived merge, context/control/filler, coalescing, replay, and
timing/idempotence contracts).

V2/N12 is a follow-up after the #181 live listen. It does not change P0–P5 behavior,
current INI defaults, or the #181 landing order.

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
| `docs/tasks/n12_async_consumers.md` | Commentary Director V2 producer/fan-out/consumer refactor |
| `CONFIG.md` / example.ini | až P1 (`[commentary.scheduler]`) |
| `COMMENTARY_ENGINE.md` / `API.md` | až implementace |

**Config runtime:** žádná změna defaultů, dokud P1 nepůjde s `defer_enabled=false`, `hard_interrupt=false`.
