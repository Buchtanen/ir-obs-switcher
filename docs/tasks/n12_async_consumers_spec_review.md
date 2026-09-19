# Review specky N12 — async consumer isolation

Kritické zhodnocení [n12_async_consumers.md](n12_async_consumers.md) (Commentary Director V2:
jeden producer, dvě nezávislé fronty, OverlayConsumer + CommentaryConsumer).

**Historical review scope:** this review evaluated async N12 only. Narrative epic (#181), skeleton composer (#195) and pit-wall CSS (#198) were not part of this review.

**Stav kódu při review:** commit `9d6f626` na větvi `cursor/narrative-observers-epic-4749`;
runtime na `master` / #181 je stále synchronní `EventFanout` + `OverlayRuntime` composition root.

**Later integration decision:** the owner subsequently required #195 on the same N12 integration branch after the isolation waves. That does not invalidate this review's sequencing warning; it supersedes only the delivery-scope exclusion. Current evidence is in [n12_implementation_report.md](n12_implementation_report.md).

**Reviewer:** cloud agent (kritický pohled po handoveru od desktop agenta).

**Disposition (desktop follow-up):** připomínky §2, §4 a §7 byly zapracovány
do závazného „Implementation appendix“ ve specifikaci. Architektura V2a/V2b se
nemění; appendix volí canonical JSON freeze, typed control plane, filler request
queue, derived merge order, context schema, coalescing keys, replay bundle a
měřitelné timing/restart AC.

---

## 0. Verdikt

Směr je **správný a nutný**. P0 fan-out opravil pojmenování a exception boundary, ale ne execution
model — slow overlay publish nebo `commentary.observe()` pořád drží stejný race tick. N12 to
pojmenovává přesně a navrhuje rozumný postup N12.0 → N12.5.

Specka je **implementovatelná jako V2a** (dva `asyncio.Task` ve službě), ale **ne jako checklist
bez doplnění kontraktu** v těchto bodech:

1. **Freeze `EventEnvelope`** — spec to vyžaduje, ale neříká *jak* (deep copy vs dataclass replace
   vs serializace). Dnes `metrics` mutuje a `stamp()` existuje.
2. **Derived events vs engine arbitration** — N12.1 slibuje merge `take_derived_envelopes()` do
   shared path; chybí pravidla priority/cooldown/dedupe vůči `EventManagerV2`.
3. **Filler / silence watchdog** — spec správně zakazuje live `RaceObserver` z commentary workeru,
   ale nepopisuje náhradu (producer message type vs periodic fact snapshot).
4. **Context snapshot** — `ContextSnapshot` je návrh typů, ne schema polí; commentary dnes bere
   `OverlayBus.bio` a quali bag přes runtime closures.

**Doporučení:** schválit spec jako architektonický kontrakt; před N12.1 doplnit krátký
*implementation appendix* (freeze API, control messages, derived merge rules). N12.5 (OS process)
nechat explicitně mimo default — spec to už dělá správně.

---

## 1. Co spec dostává správně

### 1.1 Diagnóza current gap

Tabulka „Current-state evidence“ odpovídá kódu:

| Tvrzení ve spec | Ověření |
| --- | --- |
| `EventFanout.emit()` synchronně, v pořadí registrace | `events/fanout.py` — inline loop |
| Sidecars volají `_observe_commentary` přímo | `runtime.py` — `_observe_in_car`, `_observe_session_briefs` |
| Overlay await publish před speech | `_emit_from_race()` path (spec; nezměněno v N12 docs commitu) |
| Derived bypass arbitration | `take_derived_envelopes()` v `race/observer.py` |

Spec nepretends, že P0 už vyřešil nezávislost — to je důležité pro review #181 vs N12.

### 1.2 Broadcast invariant

„Two queues, not one shared work queue“ je **kritická** věta. Shared queue = load balancing = overlay
by ztratil polovinu HUD UPDATE. Spec to blokuje explicitně.

### 1.3 Oddělení arbitration vs consumer budget

Shared path rozhodne *co je pravda* (accept, event_id, sequence). Overlay hold/priority a
CommentaryScheduler defer/TTL zůstávají **po dequeue**. Správně — jinak by TTS busy potlačoval HUD
nebo naopak.

### 1.4 Sidecar inventory

Seznam v §Sidecars je kompletní pro N12.3. Bez něj by implementace nechala díru (typicky
`ENTER_CAR` nebo `STREAM_START`).

### 1.5 Migrační slices

N12.0 characterization test před refaktorem = správná discipline (regrese sync delay). N12.3 až po
N12.2 = rozumné pořadí. N12.5 optional = neblokuje V2a.

### 1.6 V2a / V2b oddělení

Serializovatelný kontrakt bez shared mutable state je minimum pro budoucí Windows subprocess. Spec
neprodává V2b jako součást první dodávky.

---

## 2. Slabá místa a nevyjasněné kontrakty

### 2.1 Immutable envelope — specifikováno, ne implementováno

Spec: „Queue payloads are immutable… `metrics` cannot be mutated after publication.“

Dnes:

- `EventEnvelope` není frozen dataclass.
- `stamp()` a mutable `metrics` jsou běžná cesta.
- Fan-out předává `list(envelopes)` — stejná reference pro oba konzumenty i v sync režimu.

**Riziko:** overlay consumer upraví metrics pro wire → commentary vidí jiné slot bindings.

**Chybí ve spec:** jedna canonical metoda, např. `freeze_envelope(env) -> FrozenEventEnvelope`,
a zákaz mutace po stamp. Acceptance test „immutable payload“ potřebuje konkrétní API.

### 2.2 Derived events merge (N12.1)

`RaceObserver` emituje kandidáty (aftermath, flags, grid story, timing hunt). Dnes:

```text
engine tick → accepted → fan-out
observer tick → take_derived_envelopes() → often commentary-only path
```

N12.1: „Merge RaceObserver-derived candidates into shared arbitration.“

**Nejasné:**

- Projde derived stejným `EventManagerV2` jako engine emitters?
- Zachová se dnešní bypass pro `INCIDENT_AFTERMATH` (prio 72, fan-out mimo engine)?
- Kdo přiřadí `sequence` když engine batch a derived batch vzniknou ve stejném ticku?
- Double-speak pravidlo (#181 `_prefer_incident_over_aftermath`) patří produceru nebo commentary
  consumeru?

**Doporučení:** jeden odstavec „Derived merge policy“ s odkazem na existující priority table +
explicitní pravidlo same-tick incident/aftermath.

### 2.3 Filler provider a silence watchdog

#181 wiring:

```text
OverlayRuntime._wire_race_observer_fillers()
  → commentary.filler_provider closes over race_observer
```

Spec: commentary worker **nesmí** volat live `RaceObserver` z jiné lane.

**Chybí:**

- Typ zprávy: `FillerRequest` / `SilenceTick` / periodic `ContextSnapshot` s fact snapshot?
- Kdo generuje `FIELD_FACT` když director hlásí `silence_no_filler` — producer v next tick, nebo
  consumer enqueue zpět (zakázáno)?

Bez toho N12.3 buď rozbije 33 s silence filler, nebo tajně obnoví cross-lane callback.

### 2.4 `ContextSnapshot` schema

Proposed types jsou správné směrově, ale implementátor potřebuje:

| Pole | Commentary potřebuje | Overlay potřebuje | Zdroj dnes |
| --- | --- | --- | --- |
| `bio` | HR emotion | optional HUD | `OverlayBus.bio` |
| `story` | quali bag, 2+2? | ne | `RaceObserver.context` |
| `race` | overlay_mode, session | full RaceState | snapshot |

Spec neříká, zda **každý batch** nese full snapshot, nebo jen `context_version` + lookup v
consumer-local cache. Version-only je lehčí, ale vyžaduje thread-safe snapshot store v produceru.

### 2.5 Control messages vs accepted events

Session reset a config reload: spec říká „ordered control message or accepted event boundary.“

**Potřeba rozhodnout:**

- Je `SessionReset` samostatný typ mimo `EventEnvelope`?
- Nebo `CONTROL_RESET` envelope v accepted streamu?

Obojí projde AC, ale mix obou v implementaci = dvojí reset path. Spec by měl preferovat **jednu**
variantu.

### 2.6 Queue coalescing — dedupe key undefined

Backpressure §2–4: coalesce `ACTIVE`/`UPDATE` by dedupe key.

**Chybí definice klíče:** `event_type + correlation_id`? `subject.car_idx`? battle target?

Špatný klíč = ztráta legitímního UPDATE nebo ponechání duplicit. Potřebuje tabulku per event
family (battle vs sector vs timing).

### 2.7 Empty batch rule

„Batch may contain no events only when it carries a required state/control boundary.“

**Riziko zbytečného šumu:** pokud producer tickne 5 Hz a commentary queue dostává prázdné batch
s jen `context_version` bump, měří se lag špatně. Spec by měl říct **max frequency** context-only
batchů nebo coalesce context updates do event batchů.

### 2.8 Replay scope

Replay AC: „deterministically drives both consumers without live iRSDK.“

**Nejasné:** replayuje se jen accepted batch stream, nebo i context snapshot timeline? Commentary
s HR gating potřebuje bio timeline synchronně s eventy. Spec by měl říct, zda capture = `(batch,
context@version)*` nebo full tape.

---

## 3. Pořadí vůči #181 a ostatním epikům

| Závislost | Hodnocení |
| --- | --- |
| „Depends on PR #181 live-listen fixes“ | **Správně.** N12 nemění *co* se mluví; ale #181 přidává sidecars a derived typy — N12.3 musí
  migrovat všechny, ne jen engine events. |
| „Do not stack into #181 landing“ | **Správně.** Docs commit `9d6f626` na stejné větvi je OK; kód N12 = nová větev po merge #181. |
| #195 skeleton composer | **Konflikt.** Oba sahají do `director.py` / composition root. Pořadí: #181 → N12 nebo #195,
  ne paralelně. |
| #189 backlog | N12 **je** implementační spec k #189; duplicitní issue by měly odkazovat sem. |

---

## 4. Acceptance criteria — co je měřitelné vs co chybí

| AC | Měřitelnost | Poznámka |
| --- | --- | --- |
| Identical event-id lists | pass | snadno unit + integration |
| Slow commentary ≠ delay overlay | pass | N12.0 regression |
| Exception v jednom consumeru | pass | fake consumer |
| No direct overlay→director | pass | grep/import test ve spec |
| Queue overflow deterministic | **částečně** | potřebuje definici dedupe key + fixture priority mix |
| Replay deterministic | **částečně** | potřebuje replay bundle format |
| TTS TTL uses event time | pass | už dnes scheduler; ověřit že queue lag nepřepisuje event timestamp |
| Cancellation clean | pass | Windows SAPI + duck — existující riziko, N12 musí zachovat #179 chování |

**Chybí AC:**

- Producer tick wall time upper bound (např. p95 < poll interval) při full queues.
- Po consumer restart: idempotent replay bez duplicate speak (jen event-id, ne i node cooldown state).

---

## 5. Test plan — doplnění

Spec „Required tests“ je dobrý skeleton. Doporučené **konkrétní** fixture navíc:

1. **Slow overlay WS client** — commentary speak proběhne dřív než overlay wire publish dokončí
   (dnes impossible test — N12.0 ho má zachytit jako red).
2. **Derived + engine same tick** — `INCIDENT` + `INCIDENT_AFTERMATH` + flags rising edge v jednom
   producer batch.
3. **Reset mid-queue** — 5 envelopes queued, session reset control, oba consumers prázdné fronty +
   cooldown reset jednou.
4. **Config reload** — `commentary.enabled` false→true bez restartu; commentary consumer dostane
   snapshot, ne čte `OverlayRuntime`.
5. **Coalesce battle UPDATE** — 20× `BATTLE` UPDATE 5 Hz → overlay queue depth bounded, FINISH
   nikdy evicted.

---

## 6. Co ve spec **neexpandovat**

| Téma | Verdikt |
| --- | --- |
| Neo4j / graph DB | mimo N12 — správně absent |
| Nové INI queue knobs před joint test | správně odloženo |
| V2b subprocess v první dodávce | správně N12.5 only |
| LLM / skeleton composer | mimo N12 |
| Změna speak copy / graph | AC explicitně freeze — držet |

---

## 7. Doporučené úpravy specky (minimální diff)

Před startem N12.1 doplnit do `n12_async_consumers.md` (nebo krátký appendix):

1. **§Envelope freeze** — jedna funkce/typ, zákaz mutace po publish.
2. **§Derived merge** — flow diagram engine + observer → arbitration → stamp → fan-out.
3. **§Filler/silence** — message type nebo snapshot poll interval; zákaz reverse callback.
4. **§Control plane** — jedna varianta reset/reload (doporučení: typed control messages mimo
   speech envelopes).
5. **§Dedupe key table** — alespoň battle, sector, incident, ACTIVE hold.
6. **§Replay bundle** — co se ukládá na disk pro deterministic replay.

Tyto body nemění architekturu — zpřesňují kontrakt pro review a implementaci.

---

## 8. Shrnutí pro rozhodnutí

| Otázka | Odpověď |
| --- | --- |
| Je N12 potřeba? | **Ano** — P0 nestačí |
| Je spec ready pro engineering? | **Ano s appendixem** (§7) |
| Největší implementační riziko? | Derived merge + filler bez cross-lane callback |
| Největší provozní riziko? | Queue tuning bez N12.4 joint test |
| Blokovat #181 merge? | **Ne** — N12 je follow-up; spec to říká |
| Odhad slices | N12.0–N12.3 = core; N12.4 = ops důkaz; N12.5 = optional |

---

## 9. Odkazy

- Spec: [n12_async_consumers.md](n12_async_consumers.md)
- Parent: [observers_decoupling_plan.md](../observers_decoupling_plan.md) §2.2–2.3
- Related issue backlog: #189 (layer leftover)
- Narrative landing (sidecars to migrate): PR #181 / `narrative_observers_epic.md`
