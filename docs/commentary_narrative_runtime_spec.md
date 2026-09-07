# Commentary narrative runtime — cílová specifikace

**Status:** předimplementační design-freeze kandidát, nikoli popis současného runtime
**Baseline:** `master@0ce75d4` (`feat: stateful commentary sequence graph and SuperTonic TTS (#214)`)
**Issue:** [#234](https://github.com/Buchtanen/ir-obs-switcher/issues/234)
**Datum:** 2026-09-06
**Krizová kontrola:** 2026-09-07, závěry v § 24
**Rozsah:** tok streamu a session, paměť faktů, epizody, beaty, filler, závodní komentář, výběr, jazyková realizace, validace a migrace z dnešního komentářového enginu

## 1. Rozhodnutí

Komentář se rozdělí na čtyři nezávislé problémy:

1. **pravda:** co je z iRSDK a odvozených detektorů právě doloženo;
2. **děj:** které stavové epizody existují a jak se vyvíjejí;
3. **režie:** který beat má nyní hodnotu odvysílat;
4. **jazyk:** jak přesně vybraný beat vyslovit.

LLM nebude rozhodovat o pravdě, průběhu epizody ani o výběru tématu. Dostane pouze immutable `BeatPlan` s vybranými atomickými tvrzeními a rodinou povolených realizací. Výstup projde významovou validací a těsně před TTS kontrolou aktuálnosti.

Základní tok:

~~~mermaid
flowchart LR
    SDK[iRSDK snapshot] --> FACT[Atomické fakty]
    FACT --> DET[Časové detektory]
    DET --> EVT[Závodní eventy]
    TIMELINE[Stream/session timeline] --> CTRL[Deterministické lifecycle eventy]
    TIMELINE --> FACT
    CLOCK[Monotonic silence clock] --> SIL[Long-silence event]
    TIMELINE --> EP
    EVT --> REDUCE[Narrative event reducer]
    CTRL --> REDUCE
    SIL --> REDUCE
    REDUCE --> EP[Episode registry]
    REDUCE --> OPP[Event opportunity queue]
    EP --> DIR
    OPP --> DIR
    FACT --> DIR[Story director]
    DIR --> BEAT[Beat planner]
    BEAT --> PROMPT[Prompt compiler]
    PROMPT --> LLM[Qwen surface realizer]
    LLM --> VERIFY[Semantic verifier]
    VERIFY -- accepted --> COMMIT[Freshness commit gate]
    VERIFY -- rejected --> DROP[Discard beat attempt]
    COMMIT -- current --> TTS[TTS]
    COMMIT -- stale --> DROP
    DROP -- reselect different beat --> DIR
    TTS --> EXP[Exposure/fatigue]
    EXP --> DONE[Speech completed event]
    DONE --> REDUCE
    TIMELINE -. reset/rewind .-> COMMIT
~~~

Diagram neznamená frontu budoucích vět. Eventy kontinuálně mění stav a jejich speakable význam může omezeně čekat jako event opportunity s TTL. BeatPlan a text vzniknou nejvýše pro jednu právě vybíranou utterance a pouze tehdy, když je speech lane volná. Eventy přijaté během generování nebo řeči aktualizují fakta, epizody a opportunity metadata; po dokončení se z aktuálního stavu plánuje znovu.

## 2. Cíle a hranice

### 2.1 Cíle

- vytvořit souvislý komentář napříč volitelnými Practice, Qualifying a Race;
- zachovat historii při restartu stejné session i návratu do dřívější session;
- nikdy nezaměnit historický fakt za aktuální pravdu;
- stavět vícevěté mini-příběhy z jednotlivých auditovatelných beatů;
- společně řídit závodní i filler komentář a připustit ticho;
- nemít frontu předgenerovaných vět ani BeatPlanů;
- oddělit hard způsobilost od měkkého skórování a variability;
- umět explicitní authored/deterministický režim pro rodiny, které se tak předem nakonfigurují;
- používat Qwen pouze jako omezený surface realizer;
- podporovat v cílovém runtime pouze anglický výstup (`en`);
- zachovat fail-soft, async-first a bounded-memory vlastnosti služby;
- implementovat po ověřitelných interních řezech v jediné dlouho žijící v2 větvi a dodat jeden atomický breaking cutover.

### 2.2 Non-goals první implementace

- LLM nebude detekovat závodní události z raw telemetrie;
- LLM nebude počítat trendy, mezery, pozice ani výsledky;
- embedding nebude rozhodovat o fakticitě;
- nebude zaveden grafový databázový server ani nová povinná síťová služba;
- nebude se trénovat nový jazykový model;
- implementace nebude měnit `master` po dílčích rodinách ani do něj posílat plánovací dokumenty;
- dočasný legacy/shadow adapter smí existovat pouze ve vývojové větvi a před finálním breaking PR musí být odstraněn;
- první interní vertical slice není produkční rollout: finální v2.0.0 musí mít explicitní disposition všech 60 známých master event identifikátorů.

## 3. Slovník a vlastnictví

| Pojem | Význam | Vlastník |
| --- | --- | --- |
| Stream | Jeden OBS přenos od potvrzeného začátku do konce | `StreamTimeline` |
| Session stage | `practice`, `qualifying`, `race` v kanonickém pořadí | iRSDK + timeline |
| Session occurrence | Jeden konkrétní běh stage; restart vytváří nový occurrence | `StreamTimeline` |
| Lineage | Aktivní cesta occurrence od nejstarší přítomné stage k aktuální | `StreamTimeline` |
| Atomický fakt | Jedno typované tvrzení s aktéry, hodnotou, časem, evidencí a scope | `FactLedger` |
| Event | Potvrzená diskrétní změna nebo výsledek odvozený z faktů | detektory/event emitters |
| Event opportunity | Speakable význam eventu čekající pouze jako metadata, nikdy jako text nebo BeatPlan | `EventOpportunityQueue` |
| `tape_channel` | Stabilní eventová klasifikace pro tape, cadence metriky a ladění kick rate | event catalog |
| Story definition | Deklarace typu dějové epizody | `StoryCatalog` |
| Episode instance | Živý stav konkrétního příběhu ve světě | `EpisodeRegistry` |
| Beat | Jedna redakční jednotka: opening, update, outcome, recap nebo filler | `BeatPlanner` |
| Beat plan | Immutable význam a realizační kontrakt jednoho beatu | `BeatPlanner` |
| Utterance | Konkrétní jedna nebo dvě věty vytvořené z beat plánu | realizer |
| Mini-příběh | Posloupnost nula až N odvysílaných beatů jedné nebo více korelovaných epizod | `EpisodeRegistry` + director |
| Exposure | Beat, který skutečně dosáhl stavu `speaking` | speech lifecycle |

Věta není epizoda. Epizoda může vzniknout a zaniknout, aniž se stihne odvysílat. Jeden beat obvykle realizuje jednu větu; technicky smí mít dvě krátké věty, pokud je to nutné pro jasné role.

## 4. Neměnné invarianty

1. iRSDK je autorita aktuální session stage a session identity.
2. Přítomné stage jdou vždy v pořadí Practice → Qualifying → Race.
3. Chybějící stage se přeskočí; pořadí se nikdy nepřehazuje.
4. Restart nebo rewind nemaže streamovou historii.
5. Restart vytváří nový `SessionOccurrence`; nerecykluje identitu starého běhu.
6. Aktuální fakta patří právě jednomu occurrence a jedné lineage.
7. Fakta ze superseded větve zůstávají historická, ale nesmějí být current/inherited truth nové větve.
8. Downstream session může čerpat jen z aktivních předků své lineage a z výslovně historických tvrzení.
9. Epizoda patří ke konkrétnímu occurrence, lineage a source revision.
10. Necommitnutý beat změnu occurrence, lineage nebo rozhodných faktů nepřežije.
11. Faktická validace textu a kontrola aktuálnosti jsou dvě samostatné brány.
12. Skórování nikdy nemění pravdu ani stav detektorů.
13. Penalizace audience exposure vzniká až při skutečném `speaking`.
14. Filler nesmí blokovat důležitější závodní beat před commitem.
15. Ticho je platné rozhodnutí.
16. Chyba iRSDK, detektoru, LLM, validátoru nebo TTS nikdy nesmí shodit hlavní race loop.
17. Nový runtime generuje a validuje pouze angličtinu; jiný locale se nesmí tiše přepnout na neauditovaný obsah.
18. Připravená věta se neukládá na později: existuje nejvýše jedna building/verified/committed utterance a po jejím dokončení se plánuje z aktuálního stavu.
19. Tape recording je konfigurovatelný, bounded a oddělený od globální hlučnosti provozního logu.
20. Trigger deklarovaný jako `tuning.required` nesmí běžet bez ověřitelného capture plánu; selhání recorderu nikdy nesmí shodit main loop.
21. Event opportunity smí čekat pouze do svého `expires_monotonic_ms`; nenese připravenou větu, prompt ani BeatPlan.
22. Po každém beatu soutěží v jednom director passu platné event opportunities a přirození successors aktivních epizod.
23. Každý event type má právě jeden stabilní `tape_channel`; změna channel ID je verzovaná změna katalogu.

## 5. Tok streamu a session lineage

### 5.1 Povolené kombinace

Konfigurace nebo skutečnost určí podmnožinu kanonického pořadí:

~~~text
Practice
Race
Practice → Race
Qualifying → Race
Practice → Qualifying → Race
~~~

Runtime nemusí mít zvláštní FSM pro každou kombinaci. Udržuje ordered stage mask a aktuální occurrence. Autoritativní změna iRSDK může stage posunout vpřed nebo vrátit na dřívější přítomnou stage.

### 5.2 Identita occurrence

Navržený kontrakt:

~~~python
@dataclass(frozen=True)
class SessionOccurrenceId:
    broadcast_epoch: int
    stream_epoch: int
    stage: Literal["practice", "qualifying", "race"]
    occurrence: int
    session_ref: tuple[str, int]
~~~

- `broadcast_epoch` je debounced OBS output identita vlastněná `BroadcastClock`;
- `stream_epoch` je identita jednoho nepřerušeného narrative runu pod daným broadcastem; mění se při novém OBS streamu, process attach/recovery a po disable→enable automatic commentary;
- `occurrence` monotonicky roste pro danou stage v rámci streamu;
- `session_ref` je přesně `(SubSessionID, SessionNum)`; TrackID zůstává pouze metadata;
- nový `stream_epoch` vždy vytvoří novou occurrence projection i tehdy, když upstream iRSDK session pokračuje. Staré narrative identity se nesmějí znovu aktivovat.

### 5.3 Normální průchod

~~~text
P1 → Q1 → R1
~~~

- `Q1` dědí povolené souhrny z `P1`;
- `R1` dědí povolené souhrny z `P1` a `Q1`;
- occurrence-local fakta se mezi stage nepřenášejí jako aktuální stav.

### 5.4 Restart stejné session

~~~text
P1 → Q1 → R1
          └─ restart → R2

aktivní lineage: P1 → Q1 → R2
historie: R1
~~~

Restart provede atomicky:

1. uzavře nebo invaliduje aktivní epizody `R1`;
2. zruší planned/building/verified beaty `R1`;
3. ukončí TTS podle interrupt policy;
4. archivuje occurrence-local fakta `R1`;
5. vytvoří `R2`;
6. znovu zdědí povolené souhrny `P1` a `Q1`;
7. ponechá `R1` v historické paměti;
8. nastaví explicitní transition fact `session_restarted`, pouze pokud je restart spolehlivě potvrzen.

Stejná pravidla platí pro `P1 → P2` a `Q1 → Q2`.

### 5.5 Rewind do dřívější session

Příklad návratu z Race do Qualifying:

~~~text
P1 → Q1 → R1
 \→ Q2 → R2
~~~

Po vytvoření `Q2`:

- aktivní předek `P1` zůstává;
- `Q1` a `R1` zůstávají v úplné streamové historii;
- `Q1` a `R1` jsou na nové aktivní větvi superseded;
- `Q2` smí dědit fakta z `P1`, nikoliv current truth z `Q1` nebo `R1`;
- `R2` později dědí `P1 + Q2`, nikoliv `Q1 + R1`;
- nový komentář může historicky odkázat na `Q1/R1` jen výslovně minulým rámováním a jen pokud BeatPlan takový historical claim vybral.

Návrat do Practice vytvoří novou kořenovou větev `P2`; všechny předchozí Qualifying a Race occurrences zůstanou pouze historické.

### 5.6 Lineage model

~~~python
@dataclass(frozen=True)
class SessionOccurrence:
    id: SessionOccurrenceId
    parent_id: SessionOccurrenceId | None
    started_at: float
    ended_at: float | None
    end_reason: str | None
    status: Literal["active", "completed", "restarted", "superseded", "abandoned"]
~~~

`parent_id` ukazuje pouze na poslední aktivní occurrence dřívější stage. Restart stejné stage zachová stejného parenta. Tím lze vždy jednoznačně určit aktivní ancestry.

### 5.7 Detekce přechodu a restartu

Canonical `SessionRef` je dvojice `(SubSessionID, SessionNum)`. Obě hodnoty musejí být přítomné a validní; `TrackID` je metadata/fact, nikoli fallback identity. Dokud úplný ref není k dispozici, timeline nemění occurrence a nové session-scoped tvrzení je hard-gated. Přechody mají jedinou precedence tabulku:

1. `connected=false` suspenduje current occurrence a detektory, ale nemění identity ani lineage.
2. První coherent snapshot po connect/reconnect se vyhodnotí proti poslednímu `SessionRef`.
3. Změna `SessionRef` je session transition. Současný rewind `SessionTime` se ignoruje, nový occurrence začíná s run revision 0.
4. Při stejném `SessionRef` je pokles `SessionTime > 5.0 s`, potvrzený po dobu nejméně `100 ms` dalšími coherent samples, restart stejné session. Pending samples nejdou do stateful detectorů.
5. Při stejném ref bez potvrzeného rewind jde o reconnect/jitter a occurrence zůstává.

Stage se čte výhradně z řádku `SessionInfo.Sessions[SessionNum]`. `unsupported/unknown → supported` při stejném ref je jednorázové doplnění dosud neznámé klasifikace. Změna jednoho supported stage na jiný supported stage při stejném ref je `session_identity_conflict`: runtime suspenduje nové session-scoped opportunities, zachová poslední potvrzenou stage a čeká na změnu ref nebo návrat konzistentních dat. Nikdy z toho nevytvoří fiktivní přechod.

Při návratu na starší ref/stage vzniká vždy nový occurrence. Parent je poslední aktivní occurrence nejbližší dřívější přítomné stage; pozdější active occurrences se stanou `superseded`. Tím `Race → Qualifying` zachová Practice ancestor, pokud existoval, a další Race dědí z nové Qualifying occurrence.

Cílový `StreamTimeline` sjednotí dnešní `SessionCoordinator`, `RunClock` a část `StreamNarrativeFsm`, protože teprve společně znají stage, occurrence, restart a lineage.

### 5.8 Autorita streamu, reconnect a restart procesu

- OBS output state je autorita `broadcast_epoch` a skutečných output hran; iRSDK připojení samo stream nezačíná ani nekončí.
- `STREAM_STARTED` vznikne na potvrzené hraně `not_streaming/unknown → streaming`; `STREAM_ENDED` pouze na potvrzené hraně `streaming → not_streaming`.
- OBS websocket disconnect znamená `unknown`, nikoliv `STREAM_ENDED`. Pokud se stejný proces znovu připojí a OBS stále streamuje, zachová stejný `broadcast_epoch` i současný `stream_epoch`.
- Start streamu uprostřed již běžící iRacing session vytvoří occurrence s `start_reason=attached_mid_session` a `history_complete=false`. Runtime nesmí domýšlet předchozí Practice/Qualifying ani jejich fakta.
- iRacing disconnect suspenduje current facts/detectors a invaliduje necommitnuté beaty; sám o sobě neukončí OBS stream. Reconnect bez session-key změny nebo potvrzeného rewind zachová occurrence.
- Restart služby/procesu není session restart. Pokud se proces spustí do již živého OBS streamu a nemá ověřený persisted checkpoint, nový proces založí nový lokální `broadcast_epoch` pro attached output a nový narrative `stream_epoch` s `start_reason=process_recovery` a `history_complete=false`. Historické claims před restartem jsou zakázané; tape z předchozího procesu se automaticky nerehydruje ve v2.0.0.
- Disable automatic commentary ukončí současný narrative `stream_epoch`, ale nikoli `broadcast_epoch`. Pozdější enable při stále aktivním outputu založí nový `stream_epoch` s `start_reason=enabled_mid_stream`, novou occurrence projection a `history_complete=false`; staré episodes/opportunities/exposure zůstávají jen v tape/auditu.
- Ukončení streamu uzavře všechny current episodes/opportunities, zapíše manifest trailer a poté uvolní in-memory stream state.

Interní stage enum je `practice | qualifying | race`; adapter je jediný, kdo mapuje iRSDK `Practice | Qualify | Race`. `Warmup`, `Test` a neznámé typy se mapují na explicitní `unsupported`, ne na Practice. V unsupported stage je race/story commentary tiché; povolen je pouze explicitní stream/service lifecycle beat, jehož claims nepojmenovávají session jako Practice/Qualifying/Race.

Všechny speakable beaty mají hard gate `stream_active=true`. Potvrzený output start používá již existující debounced `BroadcastClock.broadcast_epoch`; krátký OBS output flicker nevytváří nový broadcast ani narrative run. `StreamTimeline` nad ním alokuje `stream_epoch`. Start reason je výlučný: `normal` při procesu známé potvrzené inactive/unknown→active hraně; `attached_live` při prvním připojení enabled NarrativeRuntime k již aktivnímu BroadcastClock epoch v témže procesu; `process_recovery` pokud nový proces poprvé potvrdí již aktivní OBS bez checkpointu; `enabled_mid_stream` při opětovném enable po předchozím narrative runu v témže stále aktivním broadcast epoch. Stav `unknown` ani resume existujícího runu nic nového nealokuje a nikdy sám neemituje end.

## 6. Faktická paměť

### 6.1 Atomický fakt

~~~python
@dataclass(frozen=True)
class AtomicFact:
    fact_id: str
    predicate: str
    subject_id: str | None
    object_id: str | None
    attributes: tuple[tuple[str, JsonScalar], ...]
    polarity: Literal["positive", "negative"]
    valid_from: float
    valid_until: float | None
    observed_at: float
    broadcast_epoch: int
    stream_epoch: int
    occurrence_id: SessionOccurrenceId | None
    lineage_id: str | None
    evidence_refs: tuple[str, ...]
    confidence: float
    scope: FactScope
    status: FactStatus
    revision: int
~~~

Predikát s aktéry je uspořádaný. `closing(Richard, Page)` není stejný fakt jako `closing(Page, Richard)`.

`occurrence_id` a `lineage_id` smějí být `None` pouze pro skutečný `stream` scope fakt, který může existovat před první coherent iRacing session, například `stream.started`, `broadcast.context` nebo `context.track_identity`. Occurrence/downstream/historical fakta vždy nesou původní occurrence; runtime nevytváří syntetickou session kvůli stream lifecycle či pre-session lobby tvrzení.

### 6.2 Scope faktů

| Scope | Restart stejné session | Přechod vpřed | Rewind | Příklady |
| --- | --- | --- | --- | --- |
| `occurrence` | archivovat/reset | pouze historie | pouze historie | current lap, gap, battle, pozice, pit stav |
| `downstream` | starý běh historie | přenést jako minulý souhrn | jen z aktivních předků | practice best, quali result, čistá kola |
| `stream` | zachovat | zachovat | zachovat | jezdec, trať, odvysílané beaty, occurrence timeline |
| `revalidate` | znovu ověřit | znovu ověřit | znovu ověřit | počasí, wetness, roster, pravidla session |
| `historical_only` | zachovat minulost | zachovat minulost | zachovat minulost | abandoned race outcome, starý quali attempt |

### 6.3 Stav faktu

~~~text
active → expired
active → superseded
active → historical
provisional → active | rejected | unknown
~~~

`unknown` není nula ani false. Beat planner musí vyžadovat konkrétní evidence policy; chybějící nebo sporný fakt kandidáta zakáže.

### 6.4 Inheritance view

Při vytvoření occurrence se fyzicky nekopírují všechny záznamy. `FactLedger` vytvoří read-only view:

~~~text
current occurrence facts
+ downstream summaries from active ancestors
+ explicitly requested historical facts
+ stream-persistent facts
- expired/superseded/incompatible facts
~~~

Každý použitý fakt zůstane ve `BeatPlan` označen origin occurrence a evidence refs. Textový výstup tedy lze zpětně auditovat.

### 6.5 Bounded memory

Navržené počáteční stropy, které je nutné replayem kalibrovat:

| Záznam | Strop |
| --- | ---: |
| Session occurrences jednoho streamu | aktivní lineage + 64 historical headers |
| Aktivní atomické fakty | 512 |
| Historical fact summaries | 512 |
| Aktivní episode instances | 64 |
| Uzavřené episode summaries | 256 |
| Detailní accepted eventy v krátkém okně | 256 |
| Skutečně odvysílané beaty | 128 |
| Semantic/pattern fatigue entries | 256 / 256 |

Po evikci detailu musí zůstat self-contained summary a celo-streamové agregáty. Odhadovaná Python metadata jsou řádově jednotky MB; dominantní paměťovou položkou zůstává jazykový/TTS model, nikoliv narrative ledger.

Aktivní lineage se nikdy neeviktuje. Po překročení 64 neaktivních occurrence headers se nejstarší detail sloučí do per-stage `CompactedHistorySummary` s počtem restartů, best/result facts povolenými pro historical řeč a tape range reference; individuální staré occurrence už není speakable. Úplný audit zůstává v NarrativeTape. Požadavek „pamatovat historii“ tedy znamená: vždy zachovat aktivní ancestors a bezpečné deklarované souhrny, nikoliv držet neomezeně všechny raw samples a epizody v RAM.

### 6.6 Od telemetrie k odvozenému stavu a eventu

Samotná hodnota `under_pressure=true` nesmí vzniknout ad-hoc podmínkou v commentary vrstvě. Cílový tok má čtyři oddělené kroky:

~~~text
normalized snapshot
→ FeatureEngine: číselné signály + quality/coverage
→ DetectorBank: candidate/active/clearing stav s hysterezí
→ AtomicFact: aktuální odvozený stav
→ EventEmitter: diskrétní STARTED/UPDATED/ENDED event na hraně stavu
~~~

Rozlišují se čtyři třídy spouštěčů:

| Třída | Příklad | Mechanismus |
| --- | --- | --- |
| Přímý edge event | průjezd S/F, průjezd sektorem | změna lap/sector identity s deduplikací |
| Lifecycle event | stream start, session start/end/restart | `StreamTimeline` a OBS/iRSDK stav |
| Temporal detector | `HUNTED` / `battle.pressure_behind` | trend, okno, coverage, potvrzení a hystereze |
| Composite event | two-front battle | kombinace více současně platných fact/event stavů |

Všechny jsou deterministické: stejné vstupní samples, stejné effective parameters a stejné pořadí vytvoří stejné facts a eventy.

### 6.7 FeatureDefinition

`FeatureEngine` počítá během ticku pouze pojmenované a typované hodnoty. Algoritmus je implementovaný a testovaný v kódu; definice vybírá algoritmus z registry a dodává validované parametry. Konfigurace nesmí obsahovat libovolný Python výraz.

~~~yaml
id: gap_behind_trend
algorithm: robust_window_trend
inputs:
  value: gap_behind_s
  correlation_key: car_behind_id
unit: seconds
parameters:
  window_s: ${under_pressure.trend_window_s}
  bucket_s: ${under_pressure.bucket_s}
  min_samples: ${under_pressure.min_samples}
  min_coverage: ${under_pressure.min_coverage}
outputs:
  - slope_s_per_s
  - net_change_s
  - coverage
  - confidence
  - target_stable
unknown_when:
  any:
    - input_stale: true
    - target_stable: false
    - coverage_lt: ${under_pressure.min_coverage}
~~~

Feature frame je immutable pro daný tick a každá hodnota nese `observed_at`, jednotku, quality, evidence refs a occurrence/lineage. `unknown` se nikdy nepřevádí na nulu nebo `false`.

Gap není automaticky spolehlivý jen proto, že je číselný. Master dnes počítá `estimated_gap_seconds` z rozdílu fractional lap distance násobeného hero last/best lap time; `CarIdxEstTime` extrahuje, ale v tomto výpočtu jej nepoužívá. Refaktor proto musí zavést versioned `gap_estimator` feature s explicitním algoritmem a quality flags. První implementace smí převzít dnešní odhad, avšak označí jej `estimated_v1`; pozdější `est_time` nebo hybridní algoritmus nesmí změnit význam stejné feature version. Wrap-around S/F, rozdílná pace, lap-down cars, pit lane, teleport/tow a změna target identity musí být samostatné testy a invalidation reasons.

### 6.8 Skládání podmínek

Podmínka triggeru, validity nebo ukončení je typovaný predicate AST. Může kombinovat libovolný počet kompatibilních stavů, nikoliv jen jednu enum hodnotu:

~~~yaml
all:
  - session.stage in [race]
  - vehicle.phase in [racing]
  - race_control.flag in [green]
  - telemetry.coverage >= ${under_pressure.min_coverage}
  - relation.car_behind_id == correlation.target_id
  - gap_behind_s <= ${under_pressure.enter_gap_max_s}
  - gap_behind_trend.net_change_s >= ${under_pressure.min_closing_change_s}
  - gap_behind_trend.slope_s_per_s <= ${under_pressure.max_closing_slope}
  - held_for:
      seconds: ${under_pressure.confirm_s}
      condition:
        gap_behind_trend.confidence >= ${under_pressure.min_confidence}
  - not:
      any:
        - hero.in_pit: true
        - target.in_pit: true
        - session.state in [gridding, finished]
~~~

Povolené operátory první verze:

- `all`, `any`, `not`;
- `eq`, `ne`, `in`, `not_in`, `lt/lte/gt/gte`, `between`;
- `changed`, `changed_by`, `crossed`, `rising_edge`, `falling_edge`;
- `held_for`, `within`, `since`, `count_within`, `sequence_within`;
- reference na jiný typed state/fact/feature a kontrola stejné correlation identity.

Složitější matematika, například trend, rozdíl, poměr, percentile nebo band classification, patří do pojmenované `FeatureDefinition`. Predicate AST ji pouze porovnává. Tím zůstává schema auditovatelné a rychlé.

### 6.9 Stavový detektor a hystereze

Temporal detector musí vlastnit lifecycle, aby stejnou podmínku neemittoval v každém ticku:

~~~text
inactive → candidate → active → clearing → inactive
              │          │
              └→ rejected└→ active, pokud se stav obnoví
~~~

Formálně pro detector state `q`, feature frame `φ`, world state `W` a parameter snapshot `θ`:

~~~text
q_(t+1) = δ(q_t, φ_t, W_t; θ)

emit STARTED právě když q_t != active AND q_(t+1) = active
emit UPDATED právě když q_t = active AND material_revision vzroste
emit ENDED   právě když q_t = active/clearing AND q_(t+1) = inactive
~~~

- `candidate`: vstupní podmínky začaly platit, ale ještě neuplynulo confirmation window;
- `active`: vznikne `*_STARTED` a publikuje se current AtomicFact;
- material band/revision change: může vzniknout bounded `*_UPDATED`;
- `clearing`: exit podmínka musí vydržet samostatné okno;
- návrat do `inactive`: vznikne `*_ENDED` s doloženým reason;
- target/correlation identity change vždy ukončí starou instanci a případně založí novou candidate instanci.

Enter a exit prahy nesmějí být stejné. Hystereze, confirmation window, minimum update interval a material-change bands zabraňují flappingu a event stormu.

### 6.10 Příklad `UNDER_PRESSURE`

Pro gap samples `g_i` v časech `t_i` se nejprve vytvoří krátké časové buckety a v každém se použije medián. Nad posledním oknem délky `W` se počítá trend:

~~~text
slope = Σ((t_i - mean(t)) × (g_i - mean(g)))
        / Σ((t_i - mean(t))²)

net_closing = median(g v první třetině okna)
            - median(g v poslední třetině okna)
~~~

Klesající gap má `slope < 0`; významné přibližování má `net_closing > 0`. Kombinace slope, net change, delšího okna, mediánových bucketů a coverage omezuje falešné detekce způsobené jedním brzdným bodem.

Ilustrační definice — hodnoty jsou startovní hypotéza pro replay tuning, ne produkční závazek:

~~~yaml
id: under_pressure
correlation_key: [hero_id, car_behind_id, occurrence_id]
feature: gap_behind_trend
tuning:
  policy: required               # experimental profile only; release catalog uses optional
  parameters:
    - trend_window_s
    - min_closing_change_s
    - max_closing_slope
    - min_coverage
    - min_confidence
    - confirm_s
    - exit_gap_min_s
    - clear_slope
    - clear_s
  capture:
    pre_window_s: 15
    post_window_s: 5
    candidate_transitions: true
    predicate_trace: true
    negative_sampling: near_threshold

signals:
  enter_signal:
    all:
      - session.stage == race
      - vehicle.phase == racing
      - race_control.flag == green
      - gap_behind_s <= ${under_pressure.enter_gap_max_s}       # např. 3.0 s
      - feature.net_change_s >= ${under_pressure.min_closing_change_s} # např. 0.6 s / okno
      - feature.slope_s_per_s <= ${under_pressure.max_closing_slope}   # např. -0.04
      - feature.coverage >= ${under_pressure.min_coverage}      # např. 0.80
      - feature.confidence >= ${under_pressure.min_confidence}
      - feature.target_stable == true

open_when:
  held_for:
    seconds: ${under_pressure.confirm_s}                      # např. 3.0 s
    condition_ref: enter_signal

update_when:
  any:
    - gap_band changed
    - feature.net_change_s changed_by >= ${under_pressure.material_change_s}
  min_interval_s: ${under_pressure.update_min_interval_s}

close_when:
  any:
    - car_behind_id changed
    - vehicle.phase not_in [racing]
    - hero.in_pit == true
    - target.in_pit == true
    - held_for:
        seconds: ${under_pressure.clear_s}
        condition:
          any:
            - gap_behind_s >= ${under_pressure.exit_gap_min_s}
            - feature.slope_s_per_s >= ${under_pressure.clear_slope}

emits:
  started: HUNTED
  updated: HUNTED
  ended: null                  # fact expiry/context closes narrative state
narrative_kind: battle.pressure_behind
publishes_fact: battle.closing(car_behind_id, hero_id)
~~~

`enter_gap_max_s < exit_gap_min_s` je schema invariant. Doménový stav „under pressure“ tedy není vstupní boolean; je to aktivní potvrzený detector stav publikující `battle.closing(challengerBehind, hero)` s target identity, valid intervalem, confidence a evidence refs.

### 6.11 Vystavené tuning parametry

Každý laditelný parametr musí mít typ, jednotku, default, bezpečný rozsah a popis vlivu:

~~~yaml
under_pressure:
  trend_window_s:
    type: float
    unit: seconds
    default: 12.0
    min: 6.0
    max: 30.0
    effect: delší okno snižuje šum, ale zvyšuje detekční zpoždění
  min_closing_change_s:
    type: float
    unit: seconds
    default: 0.6
    min: 0.2
    max: 2.0
    effect: vyšší hodnota zvyšuje precision a snižuje recall
  confirm_s:
    type: float
    unit: seconds
    default: 3.0
    min: 1.0
    max: 10.0
    effect: delší potvrzení omezuje flapping, ale zvyšuje latency
~~~

Pravidla konfigurace:

- catalog obsahuje schválené defaults a constraints;
- deployment config smí pouze overrideovat označené knobs;
- cross-field validátor kontroluje vztahy jako enter/exit hysteresis, window ≥ confirm a interval ≥ tick;
- effective detector config se zmrazí při startu streamu, dostane version/hash a uloží se do NarrativeTape;
- změna souboru uprostřed streamu nesmí zpětně změnit význam probíhající occurrence;
- každý detector decision loguje input feature values, effective thresholds, coverage, předchozí/nový stav a reason code;
- nebudou vystaveny desítky redundantních vah, které nelze nezávisle interpretovat.

Každý trigger má povinnou tuning deklaraci:

| `tuning.policy` | Význam | Recording kontrakt |
| --- | --- | --- |
| `none` | přímý nebo stabilní trigger bez laditelných prahů | stačí běžný flow audit při zapnutém flow kanálu |
| `optional` | trigger je validovaný, ale lze sbírat další corpus pro recalibration | detailní windows se ukládají jen při povoleném tuning kanálu/allowlistu |
| `required` | experimentální nový nebo změněný trigger nesmí běžet bez dat nutných k ověření | startup sestaví capture plan; pokud jej config/storage neumí splnit, trigger se fail-soft zakáže a důvod se zapíše do health/logu |

`required` se používá pouze u `experimental=true` během branch-only shadow/kalibrační fáze nebo po material změně algoritmu/parameters. Do finálního release catalogu se detector promuje až s `optional|none`; tím defaultně vypnutý tape nikdy nevypne produkční rodinu. Trigger s `none` může mít provozní debounce/cooldown, ale nemá volné sportovní threshold knobs určené k fine-tuningu.

Parametry musí zůstat rozdělené podle odpovědnosti:

| Vrstva | O čem rozhoduje | Příklady parametrů |
| --- | --- | --- |
| Feature/Detector | zda sportovní stav skutečně nastal | window, min change, coverage, confirm, hysteresis |
| Story definition | jak event otevře, aktualizuje nebo zavře epizodu | guards, correlation, material bands, successors |
| StoryDirector | zda je právě hodnotné o eventu mluvit | priority, cadence, fatigue, silence pressure |
| Prompt/Realizer | jak volně realizovat již vybraná tvrzení | freedom, pattern pool, optional claims, temperature |

Parametr z nižší vrstvy nesmí být skrytě ovlivněn vyšší vrstvou. Například vysoká editorial priority nesmí snížit detector confidence threshold a volný prompt nesmí změnit `under_pressure` truth.

### 6.12 Replay fine-tuning prahů

První implementace smí použít odborně odhadnuté konzervativní defaults bez předchozího měřicího corpus. Defaults musí být versioned, v bezpečných ranges a označené `estimated`; složitý detector se nejprve ověřuje branch-only shadow během vývoje a do final cutoveru vstoupí jen po acceptance. Tape z následných testů vytvoří označená časová okna skutečných situací a oddělené sessions/tracks pro kalibrační a validační corpus. Pro parametry `θ` pak lze minimalizovat náklad:

~~~text
Loss(θ) = w_fp × false_positives
        + w_fn × false_negatives
        + w_delay × mean_detection_delay
        + w_flap × repeated_state_transitions
        + w_conflict × overlapping_exclusive_detectors
~~~

Pro live komentář má být zpravidla `w_fp > w_fn`: mlčení je levnější než nepravdivě ohlášený souboj. Report musí vedle loss uvádět precision, recall, `F_0.5`, median/P90 detection delay, flapping rate a výsledky po session/track type. Grid/random search nebo pozdější Bayesian optimization je offline tooling; live runtime pouze aplikuje odhadnutý nebo později validovaný parameter snapshot. Absence úvodního corpus neblokuje implementaci, pouze brání tvrdit, že první defaults jsou kalibrované.

Detekční pravda nesmí záviset na speech busy stavu, fatigue, prompt freedom ani LLM výsledku. Tyto faktory vstupují až do StoryDirector eligibility a skóre. Naopak detector může kombinovat více world-state os: session, vehicle phase, race control, identity, numeric features, coverage a temporal conditions.

## 7. Dějový model

### 7.1 StoryDefinition

StoryDefinition je deklarace možného typu epizody, nikoliv hotová věta.

~~~yaml
id: battle_ahead
kind: race
tape_channel: race.battle.closing

opens_when:
  accepted_event_kind: battle.pursuit

valid_while:
  all:
    - fact: battle.closing(hero, target) is current
    - fact: relation_epoch == episode.relation_epoch
    - vehicle.phase in [racing]

closes_when:
  any:
    - accepted_event_kind: position.pass_completed with same relation
    - accepted_event_kind: battle.won with same relation
    - fact: battle.closing(hero, target) is not current
    - occurrence_changed: true

preferred_successors:
  - battle.approach
  - battle.attack_range
  - battle.side_by_side
  - position.pass
  - battle.won

exclusive_with:
  - same_relation_in_another_battle_ahead_episode

priority:
  continuation_base: 58
  max_consecutive_beats: 3
  min_interval_s: 8

fatigue:
  semantic_half_life_s: 90

allowed:
  session_stage: [race]
  vehicle_phase: [racing]

beat_roles: [opening, update, outcome]
beat_definitions: [battle.pursuit, battle.approach, battle.attack_range, battle.side_by_side, battle.won]
~~~

### 7.2 Více hodnot a podmínkové výrazy

Všechna pole, kde dává smysl více hodnot, jsou množiny. Složitější podmínky používají `all`, `any` a `not`; prahy jsou typované komparátory a časové operátory:

~~~yaml
valid_when:
  all:
    - session.stage in [practice, qualifying]
    - vehicle.phase in [out_lap, timed_lap]
    - held_for:
        condition: gap_trend == decreasing
        seconds_gte: 8
    - confidence_gte: 0.90
    - not:
        any:
          - session.finished
          - hero.in_pit
~~~

Výrazy se kompilují do typovaných predikátů; runtime nesmí interpretovat libovolný kód z JSON.

### 7.3 EpisodeInstance

~~~python
@dataclass
class EpisodeInstance:
    episode_id: str
    definition_id: str
    scope: Literal["stream", "occurrence"]
    occurrence_id: SessionOccurrenceId | None
    lineage_id: str | None
    semantic_identity: tuple[str, ...]
    correlation_ids: tuple[str, ...]
    state: EpisodeState
    opened_at: float
    updated_at: float
    resolved_at: float | None
    resolution: str | None
    fact_ids: tuple[str, ...]
    material_revision: int
    spoken_beat_ids: tuple[str, ...]
    next_eligible_at: float
    last_spoken_beat_id: str | None
    continuation_priority: float
~~~

### 7.4 Lifecycle epizody

~~~text
dormant → candidate → active → suspended → active
                         ├──────────────→ resolved
                         └──────────────→ invalidated
~~~

- `candidate`: evidence ještě nesplnila confirmační okno;
- `active`: epizoda je fakticky platná;
- `suspended`: dočasně chybí coverage, ale identita se nezměnila;
- `resolved`: existuje doložený outcome nebo přirozené ukončení;
- `invalidated`: identita, occurrence nebo evidence se rozpadla bez oprávněného outcome claimu.

Episode lifecycle je nezávislý na tom, zda se něco odvysílalo.

`stream_lifecycle` a výslovně stream-routed pre-session `filler_single` pro `filler.lobby` mohou mít `scope=stream` a nullable occurrence/lineage. Lobby varianta smí použít jen stream-scope `broadcast.context(lobby)` a čerstvý `context.track_identity`; bez něj zůstane ticho. Všechny ostatní story templates jsou occurrence-scoped a obě identity vyžadují.

### 7.5 Typy beatů

| Beat role | Účel | Podmínka |
| --- | --- | --- |
| `opening` | představit nový děj | epizoda nově active a nebyla představena |
| `update` | sdělit materiální změnu | nová revision překročí definovaný práh |
| `outcome` | uzavřít odvysílaný nebo významný děj | doložené resolution |
| `recap` | použít historický fakt v nové session | explicitně vybraná historical evidence |
| `transition` | vysvětlit změnu session/restart | potvrzený timeline event |
| `filler` | hodnotná věta při nedostatku závodních beatů | filler opportunity a score threshold |

Ne každá epizoda má všechny role. `PERSONAL_BEST` je typicky single-shot outcome. Pursuit, qualifying attempt a pit cycle jsou vícebeatové.

### 7.6 Rozpad vybraných mini-příběhů

| Rodina | Opening | Update | Outcome/close |
| --- | --- | --- | --- |
| Pursuit | potvrzené stahování soupeře | nové gap/intensity pásmo | pass, trend reversed, target changed |
| Rear pressure | potvrzený tlak zezadu | gap/intensity revision | hero holds, position lost, target changed |
| Two-front | útok vpředu + tlak vzadu | materiální změna jedné strany | jedna relace se vyřeší |
| Qualifying attempt | target locked / timed lap | sector gain/loss, projection | valid lap, invalid lap, aborted |
| Pit cycle | pit entry | stopped/service/release | pit exit/outcome |
| Incident | confirmed incident/excursion | stalled/moving evidence | back under way, tow, unknown |
| Session chapter | intro/transition | významný recap | wrap/result/restart |
| Filler track state | outlap/inlap/parade/garage | zpravidla žádný | phase changed nebo race event |

Outcome musí být srozumitelný sám, pokud opening nebyl odvysílán. `closure debt` je bonus, nikoliv oprávnění vymyslet výsledek.

### 7.7 Vlastnictví parametrů eventu, příběhu, beatu a hrany

Parametry se nesmějí nahromadit do jednoho univerzálního beatu. Každá vrstva vlastní jiný typ rozhodnutí:

| Definice | Rozhoduje | Typické parametry |
| --- | --- | --- |
| Detector/EventDefinition | zda se událost fakticky stala | feature predicates, thresholdy, hystereze, confirmation, correlation |
| Event speech policy | jak dlouho a s jakou naléhavostí může event soutěžit o řeč | `tape_channel`, TTL, base priority, urgency, penalty coefficient |
| StoryDefinition | zda epizoda existuje a zůstává relevantní | open/update/resolve routing, semantic identity, `valid_while`, conflicts, continuation policy |
| BeatDefinition | jaký významový krok lze právě vyslovit | role, source, hard guards, claims, timing, allowed contexts, realization family |
| SuccessorEdge | jak lze pokračovat po odvysílaném beatu | target, relation, guard, preference bonus, expiry/material-revision barrier |

Navržený katalogový tvar:

~~~yaml
event_type: HUNTING
tape_channel: race.battle.closing
opportunity:
  ttl_s: 10                   # estimated live_story profile
  base_priority: 64
  urgency: story             # background | context | story | critical
  penalty_coefficient: 0.8
routes:
  - story: battle_ahead
    relation: opens           # opens | updates | resolves | conflicts | independent
    correlate_by: [occurrence_id, hero_id, target_id]

story:
  id: battle_ahead
  valid_while:
    all: [same_target, closing_or_attack_state, current_occurrence]
  allowed:
    session_stage: [race]
    session_phase: [green]
    vehicle_phase: [racing]
    broadcast_context: [on_track, replay, unknown]
  continuation:
    base_priority: 58
    max_consecutive_beats: 3
    min_interval_s: 8

beats:
  - id: battle.pursuit
    role: opening
    source:
      event: HUNTING
    eligible_when:
      all: [episode_active, opening_not_spoken, required_facts_current]
    timing:
      earliest_after_open_s: 0
      expires_after_revision_s: 10
    claims:
      required: [battle.closing(hero, target)]
      optional: [battle.closing.gap]
      forbidden: [pass_completed, predicted_pass]
    realization_family: pursuit_opening
    successors:
      - beat: pursuit.update
        relation: preferred
        preference_bonus: 6
        guard: material_revision_changed
      - beat: pursuit.outcome
        relation: closure
        preference_bonus: 12
        guard: episode_resolved
~~~

`session_stage`, `session_phase`, `vehicle_phase` a `broadcast_context` jsou samostatné osy. Beat nesmí obsahovat raw jméno OBS scény. `logic/` mapuje stabilní `SwitchState.mode`, nikoli scene name, na `on_track | garage | lobby | replay | transition | unknown`; výsledkovost zůstává v `session_phase`, nevymýšlí se z OBS scény. Pole má navíc policy `ignore | prefer | require`; většina závodních beatů používá `ignore` nebo `prefer`, aby výpadek OBS nezastavil komentář. `require` patří jen vizuálně svázanému beatu.

O tom, kdy beat zazní, rozhodují nejprve hard guards: current occurrence/lineage, platná epizoda, required facts, povolené session/vehicle/broadcast kontexty, TTL, cadence a conflicts. Teprve mezi platnými beaty rozhoduje score z priority, urgency, continuity, material change, closure, fatigue, penalty a staleness. Trigger threshold sportovní pravdy se nikdy nesmí přesunout do tohoto skóre.

První hodnoty se odvodí z master dat a označí `estimated`: `speak_priority` zachová relativní pořadí jako seed `base_priority`, `cooldown_s` se použije jako seed cadence/min-interval (nikoliv TTL), `editorial.repeat_weight` jako seed penalizačního koeficientu a dnešní hrany pouze jako návrhy successors čekající na guard audit. Jediné výchozí speech policy profily jsou:

| Profil | Priority | Urgency | Opportunity TTL | Penalty coefficient | Cadence scope/minimum |
| --- | ---: | --- | ---: | ---: | --- |
| `critical` | 90 | `critical` | 45 s | 0,25 | jednou na semantic outcome revision |
| `result` | 78 | `story` | 30 s | 0,50 | semantic identity / 8 s |
| `live_story` | 64 | `story` | 10 s | 0,80 | episode / 8 s |
| `transient` | 56 | `story` | 6 s | 1,00 | semantic identity / 12 s |
| `context` | 46 | `context` | 20 s | 1,00 | `tape_channel` / 45 s |
| `filler` | 24 | `background` | 12 s | 1,40 | silence impulse / `long_silence_s` |

Hodnoty jsou initial estimates, ne kalibrované konstanty; schema dovoluje priority 0–100, TTL 1–120 s a penalty 0–4. Cadence je samostatná story/beat vlastnost, nikoli odvozenina TTL. Každá effective hodnota se zapisuje do tape a ladí se po `tape_channel` podle kick→queued→selected→spoken funnelu, expiry rate, cadence a ruční relevance kontroly. Cílem není maximalizovat kick nebo spoken rate, ale najít přijatelný poměr relevantního komentáře a ticha.

## 8. Závodní a filler tok

### 8.1 Kontinuální event-driven běh

Narrative runtime je reducer nad kontinuálním proudem typovaných eventů, ne producent dávky budoucích komentářů. Minimální deterministické commands/events jsou:

- `STREAM_STARTED`, `STREAM_ENDED`;
- `SESSION_STARTED`, `SESSION_ENDED`, `SESSION_RESTARTED`; návrat na jiný/starší `SessionRef` je uspořádaná dvojice `SESSION_ENDED` + `SESSION_STARTED`, ne čtvrtý rewind event;
- `VEHICLE_PHASE_CHANGED` pro garage/outlap/timed lap/inlap/parade/racing;
- potvrzené závodní eventy z detektorů;
- `LONG_SILENCE_ELAPSED` z monotonic clocku;
- interní `PLAYBACK_ACCEPTED`, `SPEECH_COMPLETED`, `SPEECH_INTERRUPTED`, kde `PLAYBACK_ACCEPTED` se veřejně promítá jako `SPEECH_STARTED`.

Deterministický zde znamená, že typ, identita, pořadí a čas eventu vznikají z runtime stavu bez rozhodnutí LLM. Neznamená to povinně deterministickou větu: event může otevřít/uzavřít epizodu a vyvolat director pass, který zvolí authored beat, Qwen beat, nebo ticho.

Každý accepted command nese coherent immutable timeline/fact version. Actor nejprve atomicky posune své read-only projekce a epizody; autoritativní StreamTimeline/FactLedger tím nemutuje. Potom:

1. pokud je speech lane volná, director smí vytvořit právě jeden BeatPlan;
2. pokud právě probíhá generování, event může rozpracovaný beat invalidovat nebo preemptovat;
3. pokud právě probíhá řeč, nevytváří se čekající text — pouze se aktualizuje světový stav;
4. `SPEECH_COMPLETED/INTERRUPTED` vyvolá nový director pass nad nejnovějším stavem.

Runtime má dvě jasně odlišné bounded struktury. Jediný `NarrativeMailbox` serializuje external batches a interní worker/timer commands; není to druhá kopie V4 EventEnvelope subscription. Speakable eventy po redukci vytvoří nebo aktualizují položku v `EventOpportunityQueue`. Tato druhá struktura drží pouze význam, prioritu, životnost, penalizaci, correlation a `tape_channel`; nikdy hotovou větu, prompt ani BeatPlan. Během jedné řeči tak mohou některé mezistavy expirovat nebo být superseded, aniž se později odříkají.

Významná událost během řeči se přesto nesmí ztratit jen proto, že její edge už skončil. Reducer ji promítne do current/resolved `EpisodeInstance` a event opportunity s explicitním `expires_monotonic_ms`, resolution a material revision. Po dokončení řeči director arbitruje tento aktuální světový stav proti přirozeným pokračovatelům právě odvysílaného příběhu. Pass/result může zůstat krátce způsobilým self-contained outcome beatem; starý gap update expiruje. Jde o frontu významů, ne o commentary queue textů.

#### 8.1.1 Actor a async vlastnictví

`NarrativeRuntime` je jediná vlastněná async actor task a jediný zapisovatel narrative projection/episode/opportunity/exposure/director/speech-orchestration stavu. Autoritativní StreamTimeline, FeatureEngine windows a DetectorBank FSM zůstávají ve svých producentských vrstvách; actor dostává jejich immutable snapshoty a nikdy je zpětně nemutuje.

Commentary `EventSubscription` se zobecní nebo nahradí jedním bounded `NarrativeMailbox`, který zachová dnešní overflow/recovery vlastnosti. Je to jediný actor inbox: narrow fanout adapter do něj vkládá accepted batch/timeline/config commands a Qwen/TTS/timer workers do téže fronty vracejí completion commands. Dvě paralelní input/result queues s následným `select` jsou zakázané, protože by neměly jednoznačné pořadí. Overlay si ponechá vlastní subscription a beze změny přijímá V4 envelope.

- reducer a director pass jsou synchronní bounded výpočty bez `await` a bez I/O;
- Qwen, TTS a tape writer běží v samostatných vlastněných/cancellable workers;
- worker nikdy nemění narrative state přímo, pouze vrátí command s BeatPlan tokenem;
- právě jeden generation task a jedna committed/speaking utterance jsou povolené;
- timer nevytváří polling loop; jeden vlastněný silence deadline, jeden nearest-validity deadline a nejvýše jeden speech watchdog pouze vloží tokenizovaný command a lze je zrušit;
- shutdown nejprve zastaví ingress, zruší deadline/generation, ukončí nebo bounded počká na TTS, flushne tape do timeoutu a teprve potom zahodí actor state.

#### 8.1.2 Totální pořadí a overflow

Overlay `EventEnvelope.sequence` zůstává session-scoped wire identita. Jednotlivý accepted NarrativeEvent má pořadí `(fanout_stream_sequence, source_ordinal)`; context command nese fanout sequence a inclusive ordinal range, u pure fact/timeline batch null range. Actor při dequeue přidělí každému external/internal commandu monotonní `reducer_sequence`. Jeho `context_revision` je vždy dvojice `(timeline_revision,fact_view_revision)`, nikdy jeden zaměnitelný scalar. Reducer nepřerovnává pravdivostní eventy podle priority. Současné event/completion arrivals mají jako autoritativní pořadí právě zaznamenaný `reducer_sequence`. Replay reprodukuje toto pořadí; neslibuje bitově stejné live pořadí dvou skutečně souběžných OS callbacků, které ještě žádné pořadí neměly.

Protected lifecycle/reset/config/shutdown commands se nesmějí tiše zahodit. `APPLY_CONTEXT_BATCH` se nikdy nekoalescuje; coalescing je povolen jen pro stejnou generaci silence deadline a totožný recorder generation/status tape-health command. Pokud bounded mailbox ztratí context batch, explicitní recovery barrier:

1. zruší necommitnutý BeatPlan a generation task;
2. označí narrative state `degraded_recovery`;
3. obnoví current truth z latest immutable `TimelineSnapshot + FactView` projection a přeskočí na její revision;
4. neobnovuje ztracené opportunities jako domnělé eventy;
5. zapíše gap/overflow do health a tape a pokračuje fail-soft.

Upstream nejprve synchronně dokončí timeline redukci, FactLedger publication a EventManager arbitráž. Do actoru potom vloží jeden immutable `APPLY_CONTEXT_BATCH`, který obsahuje právě jeden koherentní `TimelineSnapshot`, jeden `FactView` a 0–64 ordered accepted `NarrativeEvent`. Každý event nese přesný `fact_view_revision`; jeho fact references musí v přiloženém view existovat a mít shodnou broadcast/stream/occurrence/lineage identitu. Nesoulad event odmítne a audituje, ale novější koherentní truth projection se přesto aplikuje. Raw telemetry ani `FeatureFrame` do NarrativeMailbox nevstupují. Batch bez eventu nevytváří planning impulse a smí pouze zavřít či invalidovat stav. Více než 64 accepted eventů z jedné upstream publikace se beze ztráty rozdělí do consecutive source-order batchů se stejnou immutable truth projection a vlastními external orders; každý neprázdný díl je samostatný planning impulse.

Protection není heuristika podle priority. NarrativeEvent má odvozené `delivery_class=protected` právě pro `phase=ended|result` nebo interní `STREAM_STARTED|STREAM_ENDED|SESSION_STARTED|SESSION_ENDED|SESSION_RESTARTED`; ostatní jsou ordinary. Celý context batch je protected právě při neprázdném `timeline.transition_reasons` nebo alespoň jednom protected eventu. Jeden snapshot může nést více současných boundary reasons v kanonickém reducer-effect pořadí, například run start před session start nebo old-occurrence end/supersede před new-occurrence start. Producer hodnotu nemůže libovolně zvolit a změna množiny/pořadí je schema/actor change, nikoli tuning.

Recovery barrier si při refreshi ponechá původní mailbox position, ale nahradí payload nejnovější koherentní projekcí a rozšíří loss range. Při redukci je tento skok explicitní; později dequeued starší context revisions a worker tokens jsou stale no-op. Replay používá stejný barrier payload a reducer order, takže nezávisí na OS timestampu.

EventOpportunityQueue má samostatnou odhadnutou kapacitu 128. Nejdříve odstraní expired/superseded, potom nejnižší urgency a effective score; při shodě eviktuje nejstarší `candidate_order`. Critical položku neeviktuje, dokud existuje necritical položka. Pokud jsou všechny položky critical, eviktuje nejstarší a povinně zapíše `evicted_capacity` — nikdy neblokuje race loop.

### 8.2 Závodní trigger

~~~text
telemetry → normalized facts → temporal detector → accepted event
→ update/open/resolve episode → beat opportunity
~~~

Event je pozitivní evidence. Event envelope zůstane transportním obalem, ale narrative runtime pracuje nad typovanými facts a episode identity, ne nad volným metrics slovníkem.

Každý event type deklaruje výchozí speech policy, jejíž efektivní hodnoty se při přijetí snapshotují do event opportunity:

~~~python
@dataclass(frozen=True)
class EventOpportunity:
    opportunity_id: str
    event_id: str
    event_type: str
    candidate_order: tuple[int, int]  # reducer sequence, source ordinal
    episode_id: str | None
    correlation_key: tuple[str, ...]
    tape_channel: str
    created_monotonic_ms: int
    expires_monotonic_ms: int
    base_priority: float
    urgency_class: str
    penalty_coefficient: float
    material_revision: int
~~~

`tape_channel` například `race.battle.closing`, `race.battle.pressure`, `race.pass`, `session.lifecycle` nebo `filler.track_state` určuje stabilní řez tape a agregací. Neurčuje pravdu eventu a kvůli overlay kompatibilitě se nepřidává do V4 wire envelope: přijímací adapter jej dohledá v immutable event taxonomy. Event catalog musí dále určit, zda event otevírá novou epizodu, aktualizuje nebo uzavírá korelovanou epizodu, konfliktuje s ní, nebo je vůči ní nezávislý. Relace se poznává deterministicky z `episode_id`, `correlation_key`, story-family routing rules a occurrence/lineage; embedding ani LLM do ní nevstupují.

Opportunity se odstraní jen explicitním stavem `consumed`, `expired`, `superseded` nebo `invalidated`. Neúspěšná realizace jednoho beatu ji automaticky nekonzumuje: suppressne pouze dvojici `(beat_id, episode_revision)`, takže lze vybrat jiný významově odlišný beat, dokud opportunity platí.

Přesný lifecycle je `pending → reserved → consumed` nebo `pending/reserved → expired | superseded | invalidated | evicted`. `reserved` znamená pouze probíhající BeatPlan attempt a neblokuje přijetí vyšší revision. Opportunity se stane `consumed` na backend-neutral `PLAYBACK_ACCEPTED`, který veřejný lifecycle publikuje jako `SPEECH_STARTED`. Jde o přesnou softwarovou hranici, nikoli o neověřitelný fyzický první audio frame: SuperTonic potvrzuje úspěšné přijetí `sd.play`, SAPI/eSpeak wrapper potvrzuje přijetí playback procesu/backendu. Rejection, generation timeout, stale commit nebo TTS failure před acknowledgement rezervaci uvolní a ponechá opportunity pending do TTL, ale stejný `(beat_id, episode_revision)` zůstane suppressed. Přerušení nebo chyba po acknowledgement již consumption nevrací; ExposureStore je zapíše s konzervativní plnou repetition weight, aby systém nezačal tutéž věc opakovat.

Nový závodní event nikdy tvrdě nepřerušuje již přijatý playback. Může pouze vyhrát následující arbitráž, pokud jeho opportunity do té doby neexpiruje. Cancel je dovolen jen pro `STREAM_ENDED`, session/run reset, explicitní vypnutí commentary, supersession, která zneplatní tvrzení právě mluveného beatu, a shutdown. Manual API speech live utterance nepreemptuje.

Novější `ACTIVE/UPDATE` stejného `(event_type, occurrence, correlation_key)` superseduje starší opportunity, pokud katalog výslovně neoznačí obě revision jako samostatné speakable outcomes. `RESULT`, změna identity a rozdílné outcome type se nikdy neslijí pouhou shodou story family.

### 8.3 Filler trigger

Filler není závodní event „nic se nestalo“. Je to plánovací příležitost:

~~~text
silence pressure dostatečný
AND není způsobilý hodnotnější race beat
AND session/vehicle phase povoluje konkrétní filler
AND existují čerstvé speakable facts
AND filler fatigue dovoluje další exposure
~~~

Filler zdroje:

- lobby/pre-session orientace;
- garage/not-on-track;
- out lap, in lap, parade/forming lap;
- stabilní practice/quali/race kontext;
- počasí pouze z revalidovaných faktů;
- historické srovnání z předchozí stage;
- dlouhé ticho během jinak platné, ale nevýznamné jízdy.

Pokud není dostatečně hodnotný fakt, výsledkem je ticho. Filler se před commitem vždy nechá přebít závodním beatem.

`LONG_SILENCE_ELAPSED` je deterministický lifecycle event od monotonic clocku. Silence clock běží pouze při `stream_active=true`, neběží během přijatého playbacku a je suspendovaný při shutdownu nebo neznámém OBS output stavu. Jeho origin je `STREAM_STARTED`, `SPEECH_COMPLETED`, `SPEECH_INTERRUPTED` nebo návrat ze suspendu, podle toho, co nastalo naposledy. První impuls tedy může vzniknout nejdříve `long_silence_s` po startu/obnovení audienčního okna.

Event znamená pouze nový plánovací impuls po dosažení prahu ticha. Není to mluvený beat ani závodní fakt a může skončit dalším tichem, pokud nevznikne validní filler opportunity. Po každém vyhodnocení bez `SPEECH_STARTED` se one-shot timer znovu vyzbrojí na `now + long_silence_s`; po startu řeči jej znovu založí až speech terminal event. Nevzniká kratší retry timer ani busy loop. Závodní/lifecycle event smí arbitráž vyvolat okamžitě bez čekání na silence timer.

### 8.4 Filler příklad

~~~yaml
id: qualifying_outlap_context
kind: filler
opens_when:
  all:
    - vehicle.phase == out_lap
    - silence_for_s >= 12
valid_while:
  vehicle.phase == out_lap
closes_when:
  any:
    - vehicle.phase == timed_lap
    - vehicle.phase == pit_lane
    - race_candidate.priority >= 50
priority:
  base: 15
facts:
  optional: [practice_best, previous_quali_attempt, attempt_target]
max_beats: 1
~~~

## 9. Eligibility, skóre a rozhodnutí

### 9.1 Hard gate

Kandidát se vůbec neskóruje, pokud neplatí:

~~~text
phase_allowed
AND occurrence_current
AND lineage_current
AND required_facts_available
AND confidence_sufficient
AND episode_valid
AND not_expired
AND not_conflicting
AND cadence_allowed
AND audience_allowed
~~~

Hard gate řeší pravdu a bezpečnost. Váhy nikdy nesmějí přehlasovat chybějící fakt.

### 9.2 Skóre

Počáteční model:

~~~text
score = base_priority
      + continuity_bonus
      + edge_preference
      + closure_urgency
      + material_change_bonus
      + silence_pressure
      - semantic_fatigue_penalty
      - pattern_fatigue_penalty
      - lexical_repetition_penalty
      - staleness_penalty
      - replacement_cost
~~~

`base_priority`, `continuation_base` a `selection_threshold` jsou konečná čísla v rozsahu 0–100; koeficienty a bonusy musejí být konečné a schema odmítne NaN/∞. `urgency` má pevné pořadí `background < context < story < critical`. Nejprve se odstraní kandidáti pod `selection_threshold`, potom se vybírá lexikograficky podle vyšší urgency a vyššího score. Úplný stabilní tie-break je: nižší `candidate_order=(origin_reducer_sequence, source_ordinal)`, `episode_id`, `beat_id`. Event získá ordinal uvnitř redukovaného batch; filler/timer používá ordinal 0; successor a jiný episode beat přebírá order poslední material revision své epizody. Pod prahem se zvolí ticho. Urgency ani score nikdy neobcházejí hard gate.

Počáteční koeficienty jsou přesné `estimated` defaults:

| Člen | Hodnota |
| --- | --- |
| `continuity_bonus` | +6 pro stejnou active episode, jinak 0 |
| `edge_preference` | +6 preferred, 0 allowed, +8 closure edge |
| `closure_urgency` | +12 pro doloženou resolution s dosud neodvysílaným outcome, jinak 0 |
| `material_change_bonus` | 0/3/6/10 pro catalog band `none/minor/material/major` |
| `silence_pressure` | pouze filler: 12 při silence impulse + lineárně nejvýše dalších 8 za jeden další `long_silence_s`; jinak 0 |
| `semantic_fatigue_penalty` | `8 × min(3, F_semantic)` |
| `pattern_fatigue_penalty` | `5 × min(2, F_pattern)` |
| `lexical_repetition_penalty` | `8 × max Jaccard` nad normalizovanými content-token sets nejméně repetitivní dostupné pattern card; 0 bez historie |
| `staleness_penalty` | `10 × clamp(age / TTL, 0, 1)`; successor používá svůj revision expiry místo event TTL |
| `replacement_cost` | pouze při precommit nahrazení building planu: `8 + 8 × clamp(elapsed / request_timeout, 0, 1)`; jinak 0 |

Fatigue používá `F(t)=Σ weight×2^(-(t-spoken_at)/half_life)`, kde completed i post-accept interruption/failure mají konzervativní weight 1.0. Semantic half-life je 90 s, pattern half-life 180 s. Lexical Jaccard před realizací pracuje s pattern-card signature po odstranění schváleného EN stopword setu; neznámý budoucí Qwen text se nikdy neskóruje zpětně. `continuation_base = max(0, base_priority-6)`, pokud StoryDefinition nemá explicitní hodnotu v rozsahu 0–100.

Eventová penalizace je definována zvlášť od obecné audience fatigue:

~~~text
channel_pressure(ch,S) = 6 × min(3,
    Σ 2^(-(now-started_at)/cadence_half_life(ch)))

event_penalty(e, S) = e.penalty_coefficient
                    × channel_pressure(e.tape_channel, S)

event_score(e, S) = score(candidate(e), S) - event_penalty(e, S)
~~~

`cadence_half_life` je `max(global_min_interval_s, numeric profile cadence minimum)`. Pro policy bez číselného minima je to její TTL; pro filler je číselným minimem aktuální `long_silence_s`. `channel_pressure` vychází pouze ze skutečných playback-accepted exposures. První konzervativní koeficienty jsou odhadnuté; tape poskytne data pro pozdější fine tuning. V4 wire priority/severity nejsou ve score a nesmějí se sem skrytě přičíst.

### 9.3 Arbitráž po beatu: event versus pokračování příběhu

Po `SPEECH_COMPLETED`, `SPEECH_INTERRUPTED` i po zahozeném pokusu sestaví director jedinou kandidátní množinu:

~~~text
C = valid_event_opportunities
  ∪ valid_natural_successors(last_spoken_beat, active_episode)
  ∪ other_valid_episode_beats
  ∪ valid_filler_opportunities
~~~

Aktivní příběh proto není automatický zámek, ale má vlastní dynamickou `continuation_priority`. Ta vzniká z `continuation_base`, preference successor hrany, aktuální naléhavosti epizody, material revision, closure debt a continuity bonusu, po odečtení fatigue a staleness. Nový event může:

- pokračovat ve stejné epizodě, pokud correlation/routing určí `updates` nebo `resolves`;
- přerušit ji a otevřít jiný příběh, pokud má vyšší urgency class nebo překročí continuation score o `switch_margin`;
- čekat do TTL, pokud nyní prohraje, ale zůstává platný;
- expirovat nebo být superseded bez odvysílání.

Pokud žádný event nevyhraje, director zkouší platné přirozené successors podle grafu a skóre. Pokud není ani platná opportunity, ani platný successor či jiný episode beat, výsledkem je ticho do dalšího eventu nebo silence triggeru. Tím je přesně určeno, co se děje po každém beatu, aniž by se předem tvořila další věta.

### 9.4 Fatigue

Exposure penalty se obnovuje jedinou half-life rovnicí shodnou s § 9.2:

~~~text
fatigue_i(t) = Σ exposure_weight_k × 2^(-(t - spoken_at_k) / half_life_i)
~~~

Oddělené registry:

- episode/semantic identity;
- story family;
- realization pattern;
- krátká posloupnost beat roles;
- skutečný text nebo jeho embedding;
- filler family.

V baseline score přímo vstupují pouze `F_semantic`, `F_pattern`, lexical Jaccard a event `channel_pressure` podle rovnic v § 9.2. Story-family, role-sequence a filler registry jsou auditní vstupy pro cadence/hard guards; nesmějí přidat skrytou nepojmenovanou penalizaci. Efektivní limit je `min(commentary.director.max_consecutive_story_beats, StoryDefinition.continuation.max_consecutive_beats)` a efektivní story interval je maximum global/profile/story minima. Counter počítá po sobě jdoucí playback-accepted beaty stejného `episode_id`; resetuje se jinou epizodou, fillerem nebo occurrence/stream resetem. Po dosažení limitu hard-gatuje další non-closing successor téže epizody, ale neblokuje doložený outcome/closure ani critical event.

V MVP lze ponechat dnešní deterministické lexical-tail porovnání. Embedding je volitelné P2 rozšíření pro měkkou lexical/semantic repetition penalty; nikdy není fact gate.

### 9.5 Preempce

- `planned/building`: vyšší race beat smí filler okamžitě nahradit;
- `verified`, ale necommitnutý: vždy znovu hard gate;
- `speaking`: závodní ani critical event nepřerušuje; cancel smí vyvolat jen stream/session/run invalidace, explicitní vypnutí commentary, supersession zneplatňující právě mluvený claim nebo shutdown;
- během `speaking` se nevytváří waiter s textem ani BeatPlanem; příchozí eventy pouze aktualizují stav a po uvolnění lane se plánuje znovu;
- session occurrence změna invaliduje všechny necommitnuté beaty starého occurrence.

### 9.6 Pokračování po beatu a po neúspěšné realizaci

Nevalidní LLM výstup není podnět k opravné smyčce. Pro stejný `beat_id` a `episode_revision` platí nejvýše jeden generační pokus:

~~~text
generation timeout/error
OR semantic verification failed
OR freshness commit failed
→ discard beat attempt
→ označit beat/revision jako neeligible do material revision/terminal/reset
→ pokud šlo o první dispatch planning cyklu, jednou vybrat jiný způsobilý beat
→ po druhém neúspěšném dispatchi ukončit cyklus tichem
~~~

- neposílá se repair prompt;
- negeneruje se jiná formulace stejného beatu;
- neprovádí se automatický deterministic fallback téhož beatu;
- failure nevytváří exposure ani fatigue, ale vytvoří revision-scoped attempt suppression, aby director netočil stejný kandidát;
- jiný beat musí sám projít hard gate; pořadí `preferred_successors` je preference, ne obcházení validity.

Attempt suppression není časový retry cooldown. Klíč `(beat_id, episode_revision)` zůstává blokovaný do material revision změny, terminal state opportunity/epizody nebo occurrence/stream resetu. Samotný nový director pass ani silence trigger jej neodemkne. Jeden explicitní planning impulse dostane `planning_cycle_id` a smí dispatchnout nejvýše dva různé BeatPlany: první volbu a jeden alternativní beat. Druhé selhání/replacement zapisuje `planning_cycle_exhausted` a výsledkem je ticho. Další accepted/lifecycle/silence event, accepted material revision nebo speech-terminal command může založit nový cyklus; pure FactView update nikoli. Limit je pevný interní invariant, ne další config knob.

Po úspěšném `speaking/completed` director provede arbitráž podle § 9.3. Pokud platnost epizody nebo jejích rozhodných faktů vypršela a není doložený outcome, nepokouší se příběh uměle uzavřít. Pokud zároveň není platná event opportunity ani jiný successor, čeká na nový závodní event nebo na nový silence trigger, který může vytvořit nezávislou filler opportunity.

Všechny intervaly platnosti jsou half-open: horní mez už neplatí. Actor vlastní jeden nearest-validity deadline pro opportunities, successor revisions a jediný BeatPlan; FactLedger publikuje time-expiry faktů jako fact-only context batch. Každý reducer command před svým vlastním efektem provede stejný sweep `deadline <= reduction_now`. Validity command pouze ukončí expired položky, zruší neplatný preaccept pokus a znovu vyzbrojí deadline; nikdy sám nevyvolá director ani alternativní beat. Pokud se jeho ordinary admission při plném mailboxu nezdaří, následující již queued command provede sweep a zapíše se `deadline_admission_skipped`.

## 10. BeatPlan a speech lifecycle

### 10.1 BeatPlan

~~~text
schemaVersion, planId, planningCycleId, cycleAttemptOrdinal,
beatId, episodeId, opportunityId?, candidateSource, beatRole,
streamEpoch, occurrenceId?, lineageId?, episodeRevision,
requiredClaims, optionalClaims, forbiddenClaimTypes, requiredFactIds,
realizationFamily, realizationPattern, realizationBackend, promptOptions,
language="en", styleCardId?, maxChars, maxSeconds,
plannedMonoMs, expiresMonoMs, sourceRefs, catalogHash, factViewRevision
~~~

Přesné typy, bounds a nullability jsou jedině v `docs/v2.0.0/schema-contracts.md`; tento seznam je záměrně stejný a nesmí se vyvíjet jako druhé schema.

BeatPlan neobsahuje mutable observer ani globální telemetry dump. Vzniká just-in-time pouze pro aktuální director pass; další beaty mini-příběhu se předem neplánují ani negenerují.

Nullable occurrence/lineage je dovolena pouze pro `stream.started` a přísnou stream-scope variantu `filler.lobby`, která váže pouze lobby context a track identity. Všechny ostatní session, race, bio a filler beaty musí být připnuty ke coherent occurrence.

### 10.2 Lifecycle jedné utterance

~~~text
planned → building → generated → verified → committed → speaking → completed
             ├──────────────→ rejected
             ├──────────────→ invalidated
             └──────────────→ replaced
verified ───────────────────→ stale
speaking ───────────────────→ interrupted
~~~

- `generated` znamená pouze, že LLM vrátil text;
- `verified` znamená, že text odpovídá BeatPlan;
- `committed` znamená, že BeatPlan je stále aktuální;
- fatigue se zapíše až při `speaking`.
- `rejected`, `invalidated` a `stale` jsou pro daný beat/revision terminální; director smí pokračovat pouze jiným způsobilým beatem.

## 11. Stavba textu

### 11.1 Realizační backend a dynamická volnost

| Backend | Popis | Použití |
| --- | --- | --- |
| `authored` | deterministická pattern realizace zvolená předem | explicitně nakonfigurované rodiny, kritické výsledky |
| `qwen_compiled` | Qwen dostane společný kontrakt, relevantní predikáty, fakta a dynamické prompt options | doporučený live režim |

Backend se volí před pokusem. Selhání `qwen_compiled` nepřepíná tentýž beat do `authored`; beat se zahodí podle § 9.6 a director hledá jiný beat.

Volnost Qwen není samostatný runtime mód. Je to součást immutable BeatPlan zvolená pro konkrétní beat:

~~~python
@dataclass(frozen=True)
class PromptOptions:
    freedom: Literal["tight", "balanced", "loose"]
    pattern_choice: Literal["fixed", "family_pool"]
    optional_claim_limit: int
    allow_clause_reorder: bool
    max_sentences: Literal[1, 2]
    temperature: float
    top_p: float
~~~

Profily:

- `tight`: fixed pattern, jen required claims, jedna věta a nízká sampling variance; pro výsledky, změny pozice a směrové relace;
- `balanced`: malý family pool, nejvýše jeden optional claim a omezená změna pořadí klauzí; běžný race commentary;
- `loose`: širší auditovaný lexikon, nejvýše dva optional claims a volnější cadence; pouze pro nekritický filler nebo recap s bohatými stabilními fakty.

Director vybírá profil deterministicky podle event family, priority, confidence, množství faktů, dostupného časového rozpočtu a repetition pressure. Konfigurace může profily po rodinách utáhnout nebo omezit, ale nesmí zvýšit volnost nad auditované maximum katalogu. `freedom` nikdy nepovoluje nové identity, čísla, vztahy, příčiny, výsledky ani predikce. Všechny profily procházejí stejným SemanticVerifierem a volba options se zapisuje do tape.

Krizová podmínka finální produkční aktivace: všechny rodiny povolí nejvýše `tight`; `balanced` se aktivuje jen pro rodinu se schváleným verifier corpus. `loose` zůstává vypnutý, dokud verifier prokáže přijatelný false-accept limit na samostatném holdoutu. Regexová kontrola jmen/čísel sama o sobě pro `loose` nestačí.

### 11.2 Prompt compiler

Prompt se skládá z:

1. společného role a fact-safety kontraktu;
2. definic pouze predikátů přítomných v required/optional claims;
3. rodinných antipatternů získaných z replay chyb;
4. `PromptOptions` pro tight/balanced/loose profil;
5. jednoho fixed patternu nebo malého auditovaného family poolu podle profilu;
6. přesného JSON semantic frame;
7. limitu TTS a output-only instrukce.

Do promptu se neposílají:

- všechny graph nodes;
- globální seznam povolených jmen a čísel;
- unrelated telemetry;
- texty jiných story families;
- staré komentáře jako zdroj faktů;
- více kandidátů v jednom requestu.
- plán dalších beatů nebo požadavek na celý mini-příběh.

Test s Qwen ukázal, že univerzální prompt s příklady všech rodin může přenést weather text do gap komentáře. Kompilace pouze relevantních pravidel tento cross-contamination odstranila.

### 11.3 Ověřený Qwen experiment

Lokální model `qwen3:4b-instruct-2507-q4_K_M`, resident, 2026-09-06:

| Metrika | Výsledek finálního compiled promptu |
| --- | ---: |
| Situace × bezpečné patterny | 8 × 4 |
| Výstupy | 32 |
| Ruční hard semantic pass | 32/32 |
| Role reversal | 0 |
| Invented name/number/event | 0 |
| Schema/meta leak | 0 |
| Unikátní formulace | 31/32 |
| TTFT median / P90 / max | 0,13 / 0,25 / 0,50 s |
| Total median / P90 / max | 0,53 / 0,86 / 1,04 s |

Úplně první cold request před zahřátím modelu v předchozí sérii trval 3,46 s. Výsledky jsou vývojová evidence, nikoliv produkční garance. Musí se zopakovat nad plným corpus, na cílovém Windows stroji a s TTS.

### 11.4 Latency budget

Navržený warm budget:

| Úsek | Cíl P95 |
| --- | ---: |
| Fact/episode update | ≤ 10 ms |
| Eligibility + scoring + BeatPlan | ≤ 10 ms |
| Qwen generation | ≤ 1 200 ms |
| Semantic verification | ≤ 100 ms pro deterministic family verifier |
| Freshness commit | ≤ 5 ms |
| Celkem před TTS synth | ≤ 1 350 ms |

Critical eventy mohou být předem směrovány do explicitního `authored` režimu. Pokud už byl beat směrován do Qwen a model není resident, překročí timeout nebo BeatPlan zestárne, tento pokus se zahodí; nesmí zdržet live event o další generativní nebo fallback pokusy.

### 11.5 Semantic verifier

Verifier ověřuje dvě množinové podmínky:

~~~text
claims(generated_text) ⊆ closure(required + selected_optional)
required_claims ⊆ claims(generated_text)
~~~

MVP vrstvy:

1. přesná jména, čísla, jednotky, P/S tokeny a technická TTS bezpečnost;
2. family-specific ordered relation parser nad schváleným lexikonem;
3. zakázané event/cause/prediction/magnitude claimy;
4. povinné claim IDs a role;
5. ambiguity → reject/discard, nikoliv tipování.

Budoucí NLI nebo claim-extractor model může přidat druhý pravděpodobnostní názor, ale nesmí sám přehlasovat hard identity/number/role gate. Druhý LLM request stejnému modelu není vhodný MVP verifier: zdvojnásobuje latenci a není nezávislou evidencí.

### 11.6 Freshness commit

Po validaci a bezprostředně před TTS se porovná:

- stream epoch;
- current occurrence id;
- active lineage id;
- episode id a state;
- episode material revision;
- hero order revision;
- target/relation identity;
- expires_at;
- critical conflicting events vzniklé během generování.

Fakticky správná, ale zastaralá věta se nesmí odvysílat.

## 12. Potřeba textů a využití dnešního obsahu

### 12.1 Inventura master baseline

`src/irswitch/commentary/data/sequence_graph.json` na baseline obsahuje:

| Položka | Počet |
| --- | ---: |
| Nodes | 54 |
| Edges | 24 |
| Pokryté event types | 50 |
| EN authored variants | 2 128 |
| CS authored variants | 2 128 (legacy, mimo cílový runtime) |
| Celkem legacy authored strings | 4 256 |
| Style cards | 9 |

Pro cílový anglický runtime je zdrojovým poolem pouze 2 128 EN variant. Českých 2 128 variant se neinventarizuje pro migraci, nevyžaduje se jejich parita a nový runtime je nesmí routovat. Problém anglických textů je jejich současný kontrakt: jedna node definice směšuje event match, phase/mode, prioritu, cooldown, fatigue policy, style cards, TTS limity, sloty a stovky hotových vět. Část vět navíc obsahuje hodnotící nebo příčinné zabarvení, které nemusí být doloženo vybranými fakty.

### 12.2 Co lze použít přímo

- TTS limity a validované SSML zásady;
- bezpečné jednoznačné authored critical/result patterny po proposition auditu;
- slot formattery pro časy, mezery a pozice;
- názvosloví event families;
- část krátkých patternů bez nepodloženého colour;
- EN stylistický materiál pro kuraci pattern katalogu;
- existující replay rejected/accepted texty jako kontrafaktuální test corpus.

### 12.3 Co nelze převzít bez auditu

- všechny authored variants jako automaticky fakticky bezpečné;
- věty obsahující `steady`, `close`, `fast`, `controlled`, příčinu, úmysl nebo budoucí outcome bez odpovídajícího claimu;
- současné style-card examples jako univerzální prompt obsah;
- globální allowed name/number seznam;
- graph edge jako důkaz, že předchozí epizoda skutečně zůstala aktivní;
- accepted event history jako náhradu active fact ledgeru.

### 12.4 Minimální nový realizační katalog

MVP nemusí nahradit 2 128 anglických vět stejným počtem. Variabilita vznikne kombinací bezpečných patternů, jmen, čísel, clause order a cadence.

Auditovaný cílový obsah pro jediný podporovaný jazyk, angličtinu, je rozepsán v `docs/v2.0.0/event-beat-disposition.md`:

| Skupina | Realization families | Sémantické BeatDefinition | EN patterny na beat | Minimum patternů |
| --- | ---: | ---: | ---: | ---: |
| Timing a pace | 7 | 12 | 4 | 48 |
| Battles | 6 | 8 | 4 | 32 |
| Position outcomes | 3 | 4 | 4 | 16 |
| Incidents/recovery | 4 | 5 | 4 | 20 |
| Pit cycle | 2 | 6 | 4 | 24 |
| Stream/session/context | 12 | 22 | 4 | 88 |
| Bio context | 1 | 1 | 4 | 4 |
| Filler families | 2 | 6 | 4 | 24 |
| **Celkem základní katalog** | **37** | **64** |  | **minimum 256 EN pattern cards** |

Číslo **64** vzniklo úplnou inventurou, ne umělým limitem. Původních 50 event types bylo pouze průnikem legacy graphu; union graphu, V4 catalog entries/fallbacks a samostatného `PACE_HUNT` obsahuje 60 identifikátorů. Současných 54 nodes se nepřekládá 1:1: aliases a visual-only eventy nemají beat, některé nodes jsou pouze rozdílné formulace, zatímco sector, incident, stage-specific intro/wrap/in-car, pit lane/release, restart a šest filler situací vyžadují samostatný význam. Nový beat je oprávněný pouze rozdílem required/forbidden claims, role, lifecycle, hard guard nebo successor chování; styl, emoce či jiná věta nový beat nevytváří.

První branch-only vývojový vertical slice může začít přibližně na **20–24 BeatDefinition** a 80–96 EN patternech; nejde o částečný merge ani produkční režim:

- pursuit/front pressure/two-front;
- pass a position change;
- lap/quali attempt;
- pit cycle;
- incident/recovery;
- session intro/restart/wrap;
- outlap/inlap/parade/garage filler;
- weather/field context.

Zmrazený baseline je nejméně čtyři enabled auditované EN pattern cards na beat, tedy **minimálně 256**. Jeden pattern není jedna výsledná věta; se sloty a povolenými clause/verb variantami vytváří mnohonásobně větší prostor. Dnešních 2 128 EN strings pravděpodobně obsahuje dost surového materiálu, ale každý pattern musí být označen required claims, forbidden claims a safe lexical transformations.

### 12.5 Převod dnešních vět

Každá současná věta projde offline klasifikací:

~~~text
SAFE_PATTERN
SAFE_AUTHORED_REALIZATION
STYLE_ONLY_FRAGMENT
UNSUPPORTED_COLOUR
AMBIGUOUS
REJECT
~~~

Automatická extrakce smí pouze navrhovat. Přijetí do live katalogu vyžaduje proposition-level audit a kontrafaktuální testy s prohozenými aktéry, pozicemi, polaritou a časem.

## 13. Komponenty cílového runtime

### 13.1 StreamTimeline

Vstupy: stream edge, iRSDK session reference, session key, session type, session time, connected.
Výstupy: stream epoch, occurrence, active lineage, transition/restart/rewind event.
Odpovědnost: jediný vlastník session identity a reset orchestrace.

### 13.2 FactLedger

Vstupy: normalized snapshots, detector evidence, timeline transitions.
Výstupy: immutable active/inherited/historical fact view a revisions.
Odpovědnost: jediný upstream vlastník scope, provenance, confidence, supersession a bounded summaries. NarrativeRuntime drží pouze poslední immutable `FactView` projection označenou verzí.

### 13.3 FeatureEngine

Udržuje bounded časová okna a počítá registry pojmenovaných typed features, například gap trend, net change, coverage a target stability. Vydává per-relation immutable FeatureFrame s process-global monotonním `frame_sequence`; duplicate/starší frame je v detectoru auditovaný no-op. Narrative `reducer_sequence` zde ještě neexistuje a nesmí být vstupem. FeatureEngine nezná speech ani LLM.

### 13.4 DetectorCatalog, DetectorBank a EventEmittery

Načítají validované predicate AST a tuning parametry, vlastní candidate/active/clearing lifecycle a publikují odvozené facts plus diskrétní edge eventy. Zůstávají autoritou sportovního významu; jednotlivý snapshot nevytváří trend.

### 13.5 NarrativeEventReducer

Serializuje deterministické lifecycle, race, long-silence a speech commands do jednoho konzistentního narrative transition. Timeline/Fact commands nahrazují jeho immutable projekce pouze vzestupnou verzí; reducer nevlastní producentské FSM. Smí držet bounded vstupní metadata, ale nikdy hotové věty, prompty ani budoucí BeatPlany.

### 13.5.1 NarrativeInputAdapter

Je stateless synchronní boundary adapter, nikoli další vlastník pravdy. Kompoziční `RaceRuntime` mu v jednom ticku předá již vytvořený immutable `TimelineSnapshot`, `FactView` a EventManagerem přijaté frozen V4 envelope v jejich accepted pořadí. Adapter z versioned registries pouze dohledá narrative kind, `tape_channel`, `delivery_class`, policy hash a typed fact references, ověří identitu/revision, lossless rozdělí více než 64 accepted eventů a přes `put_nowait` vytvoří `APPLY_CONTEXT_BATCH`. Nečte mutable `RaceObserver`, OBS klienta ani živý FactLedger a nesmí vytvářet/supersedovat facts či měnit EventManager rozhodnutí.

DTO `TimelineSnapshot`, `FactView`, `NarrativeEvent` a `NarrativeCommand` patří do úzkého neutrálního contracts modulu bez importu producentů nebo consumerů. `logic/`, `events/` a `commentary/` smějí importovat pouze tyto DTO; kompoziční wiring zůstává v dnešním runtime glue. Overlay nadále dostává původní frozen accepted batch a V4 wire, takže narrative atomický řez nemění jeho transport.

### 13.6 EventOpportunityQueue

Drží bounded, deterministicky seřazené speakable event opportunities. Každá položka nese event/correlation identity, `tape_channel`, effective priority, urgency class, TTL, penalty coefficient a terminal reason. Fronta neobsahuje text ani BeatPlan; po každém speech lifecycle eventu se znovu hodnotí proti successors aktivních epizod.

### 13.7 StoryCatalog

Načítá a validuje StoryDefinition. Neobsahuje tisíce hotových vět. Obsahuje opening/valid/close pravidla, allowed phases, priority policy, beat roles, successors, conflict groups a realization family.

### 13.8 EpisodeRegistry

Vlastní runtime EpisodeInstance, semantic identity, material revision, resolution a vazbu na occurrence. Odděluje světový lifecycle od speech lifecycle.

### 13.9 FillerOpportunityDetector

Na deterministický `LONG_SILENCE_ELAPSED` vyhodnotí vehicle/session phase a dostupné stabilní fakty a případně vytvoří nízkoprioritní beat opportunity. Nevyrábí falešný race event ani periodicky nepolluje director.

### 13.10 BeatPlanner

Vybere required/optional claims, beat role, temporal framing, self-contained outcome policy, TTS budget a expiry. Nikdy neposílá LLM celý fact ledger.

### 13.11 StoryDirector

Po eventu a jen při volné speech lane sbírá event opportunities, přirozené successors, ostatní episode beats a filler, aplikuje hard gate, continuation/switch policy, skóre, preempci a stabilní tie-break. Vytvoří nejvýše jeden just-in-time BeatPlan nebo rozhodne pro ticho.

### 13.12 ExposureStore

Eviduje pouze skutečné audience exposure: semantic identity, family, pattern, text, started/completed/interrupted timestamps. Poskytuje decaying fatigue a novelty penalty.

### 13.13 RealizationCatalog a PromptCompiler

Mapují realization family + pattern + `PromptOptions` na anglické predicate semantics, safe paraphrases, anti-patterns a případnou předem zvolenou authored realizaci. `locale` není dimenze katalogu; na vstupu je pevně validováno `en`.

### 13.14 SurfaceRealizer

Rozhraní pro authored a Qwen implementaci. Realizační režim je součást BeatPlan a během jednoho pokusu se nemění. Qwen I/O je fail-soft, cancellable/timeout bounded a neběží v async race loopu.

### 13.15 SemanticVerifier

Vrací explicitní claim-level verdict a kódy, nikoliv jedno neprůhledné similarity číslo. Style warning ani hard semantic failure nesmí spouštět retry nebo repair; nevyhovující beat attempt se zahodí a director vybírá jiný beat.

### 13.16 CommitGate

Atomicky porovná BeatPlan token se současným timeline/episode/fact stavem. Jedině jeho `committed` dovolí TTS.

### 13.17 SpeechWorker

Zachová právě jednu in-flight utterance, TTS backend, ducking, lifecycle callbacks a hard interrupt. Nemá waiter ani frontu připravených vět. Start je bounded `tts.start_timeout_s`, accepted playback BeatPlan `max_seconds` a cancellation `tts.stop_timeout_s`; všechny používají tokenizovaný actor watchdog. Stop timeout token karanténuje, označí TTS unavailable a zakáže další speech do `COMPONENT_HEALTH_CHANGED(ready)` s vyšší backend generation po explicitním config-rebuild preflightu; stale callback ani periodický retry backend neoživí. Completion/interruption vrací event reduceru pouze lifecycle event; nový text se případně vytvoří až novým director passem.

### 13.18 NarrativeTape a ReplayEvaluator

Zaznamenává raw rozhodné vstupy nebo odkazy, fact revisions, timeline transition, episode transition, všechny kandidáty se score breakdownem, BeatPlan, prompt family/pattern, model latency/tokens, verifier claims, commit verdict a TTS exposure.

### 13.19 TapePolicyCompiler a TapeWriter

`TapePolicyCompiler` spojí globální recording config s `tuning.policy` a capture požadavky jednotlivých triggerů. Vytvoří immutable `CapturePlan` a startup diagnostics. `TapeWriter` asynchronně zapisuje versioned records, hlídá priority záznamů, rotaci, retenci, kompresi a drop counters. Obě komponenty jsou fail-soft a nesmějí blokovat race loop.

## 14. Rozdílový návrh proti masteru

### 14.1 Reuse matice

| Dnešní komponenta | Rozhodnutí | Cílová změna |
| --- | --- | --- |
| V4 `EventEnvelope`, accepted stream, audiences | zachovat beze změny jako overlay/public transport | narrative adapter z envelope + story/context payloadu vytvoří versioned interní `NarrativeEvent`; narrative fields se nepřidávají do overlay wire |
| `AsyncEventFanout`, immutable freeze | zachovat pro overlay V4 | commentary subscription nahradit jediným NarrativeMailbox; nevkládat do overlay batch narrative DTO |
| `RacePipeline`/`RaceRuntime` composition | rozšířit | po synchronním timeline/fact/EventManager kroku zavolat stateless NarrativeInputAdapter se třemi immutable vstupy; adapter nevlastní truth |
| dnešní commentary queue/waiter | odstranit | ponechat pouze bounded event-opportunity metadata; jedna in-flight utterance a po completion nový director pass |
| `SessionCoordinator` | sloučit | část nového `StreamTimeline` |
| `RunClock` | rozšířit/sloučit | rewind debounce zachovat, epoch zasadit do occurrence |
| `StreamNarrativeFsm` | rozdělit | timeline transition facts vs. beat planning |
| `StreamMemory` | nahradit | typed lineage-aware `FactLedger` + summaries |
| `StoryHistory` | rozdělit | accepted event window a samostatný ExposureStore |
| raw/event observer výpočty | rozdělit | společný FeatureEngine pro typed values, windows, coverage a quality |
| event detektory/FSM | zachovat a migrovat | DetectorBank s predicate AST, hysterezí, correlation identity a typed evidence/facts |
| dnešní DEBUG/replay zápis | rozdělit | provozní log oddělit od channel-based NarrativeTape; přidat CapturePlan, schema, rotaci a drop policy |
| `sequence_graph.json` | migrační zdroj | rozdělit StoryCatalog a RealizationCatalog; adapter pouze během branch vývoje |
| `GraphNode` | rozdělit | story policy, beat policy, realization policy, TTS policy |
| `GraphEdge` | rozšířit | preferred, closure a forbidden successor s guards |
| `SequenceGraphRuntime` | významně zachovat | scoring/fatigue jádro nad BeatCandidate místo node |
| `MiniStoryRegistry` | rozšířit/přejmenovat | `EpisodeRegistry` s více aktivními epizodami a lineage |
| `CommentaryMicroplan` | nahradit v2 | jeden just-in-time typed BeatPlan bez canonical text jako truth nebo budoucích beatů |
| `composer.build_skeleton` | rozdělit | BeatPlanner + authored realizer + dynamický PromptCompiler |
| `polish.py` | rozdělit | Qwen transport, prompt compiler a semantic verifier |
| `validator.py` | zachovat technickou část | TTS/SSML validation oddělit od semantic claims |
| `anti_repeat.py` | zachovat jako MVP | připojit pattern/semantic exposure; embedding volitelně |
| `CommentaryDirector/Consumer` | ztenčit | orchestrace nad timeline/episodes/beats, ne druhý fact owner |
| `ProcessTtsSink`, SuperTonic, ducking | zjednodušit | jedna in-flight řeč, žádný prepared waiter, backend acknowledgement a command-based terminal states |
| replay evaluator a DEBUG tape | rozšířit | claim-level a timeline evidence |

Názvový a významový kontrakt je zmrazen takto:

- existující `events/event_catalog.py` zůstává mapou event type → overlay presentation state; nový obecný `EventCatalog` se nevytváří;
- `events/event_taxonomy.py` vlastní canonical event type, audience a právě jeden `tape_channel`; lookup se provede při tvorbě `NarrativeEvent`, ne mutací V4 envelope;
- `events/detector_catalog.py` vlastní pouze sportovní detector/feature definice;
- `commentary/narrative_catalog.py` vlastní EventSpeechPolicy, StoryDefinition, BeatDefinition a SuccessorEdge;
- `EventEnvelope.priority` je transportní/event salience pro accepted-stream/overlay politiku;
- `EventEnvelope.expiresAt` je wire/presentation expiry;
- `EventOpportunity.base_priority`, `penalty_coefficient` a `expires_monotonic_ms` jsou oddělená commentary scheduling data. Žádné z těchto polí se nesmí implicitně kopírovat z wire priority/expiry.

`NarrativeEvent` je commentary-internal immutable DTO. Nese původní `event_id/sequence/type/phase/correlation`, narrative occurrence a lineage reference, resolved `tape_channel`, typed fact/evidence references, přesný `fact_view_revision` a policy revision. V4 envelope zůstává jediným overlay wire payloadem a regresní fixture musí před/po refaktoru zůstat byte-semantically shodná.

### 14.2 Navržené moduly

Názvy jsou návrhové a mohou se během implementace upravit bez změny kontraktu:

~~~text
src/irswitch/logic/stream_timeline.py
src/irswitch/contracts/narrative.py
src/irswitch/events/facts.py
src/irswitch/events/features.py
src/irswitch/events/detector_catalog.py
src/irswitch/events/detectors.py
src/irswitch/commentary/episodes.py
src/irswitch/commentary/input_adapter.py
src/irswitch/commentary/event_reducer.py
src/irswitch/commentary/event_opportunities.py
src/irswitch/commentary/story_catalog.py
src/irswitch/commentary/beat.py
src/irswitch/commentary/beat_planner.py
src/irswitch/commentary/realization_catalog.py
src/irswitch/commentary/prompt_compiler.py
src/irswitch/commentary/semantic_verifier.py
src/irswitch/commentary/realizer.py
src/irswitch/commentary/exposure.py
src/irswitch/commentary/tape.py
src/irswitch/commentary/tape_policy.py
~~~

Transport a service glue zůstávají v dnešních vrstvách. `commentary/` nesmí sahat do mutable `RaceObserver`; dostává immutable snapshots/tokens.

### 14.3 Datové soubory

~~~text
src/irswitch/commentary/data/story_catalog.json
src/irswitch/commentary/data/realization_catalog.json
src/irswitch/race/data/detector_catalog.json
src/irswitch/commentary/data/tape_schema.json
src/irswitch/commentary/data/sequence_graph.json   # legacy během migrace
~~~

Story catalog neobsahuje natural-language facts. Realization catalog neobsahuje detekční prahy sportovní pravdy. Detector catalog obsahuje pouze schválené typed algoritmy, predicate AST, parameters a constraints; deployment overrides zůstávají v hlavní konfiguraci.

## 15. Realizační kroky

### Fáze 0 — kontrakty a charakterizace masteru

- zmrazit master event/node inventory a relevantní replay tapes;
- definovat versioned tape schema, stream manifest, oddělené `flow`, `llm_eval`, `detector_tuning` kanály a povinný eventový `tape_channel`;
- zavést config řízenou rotaci/retenci a změřit objem pro minimal/normal/full;
- připravit minimální syntetické/charakterizační fixtures a counterfactual minimal pairs;
- označit první detector defaults jako konzervativní odhady; úvodní měřicí corpus není vstupní podmínka implementace;
- zavést docs-only TDD exception pro tento návrh; runtime fáze už test-first.

Exit: stabilní datové/schema kontrakty, charakterizované master chování a funkční recorder; kalibrace nad reálnými daty může následovat po prvních testech.

### Fáze 1 — StreamTimeline ve shadow režimu

- zavést SessionOccurrence, parent lineage a transition reasons;
- převzít session-key a rewind debounce;
- emitovat deterministické stream/session start/end/restart/rewind eventy;
- publikovat shadow timeline vedle dnešních resetů;
- otestovat všechny přítomné stage kombinace, restart každé stage, Race→Qualifying a návrat do Practice;
- potvrdit reconnect ≠ restart.

Exit: shadow lineage vždy odpovídá očekávané větvi a nemění produkční komentář.

### Fáze 2 — FactLedger a inheritance

- zavést AtomicFact, scopes, status, evidence refs a revisions;
- vytvořit adapter ze současných RaceState/EventEnvelope;
- implementovat active ancestor view a historical query;
- testovat, že superseded Q/R fakta neproniknou do nové větve;
- přidat bounded summaries a eviction tests.

Exit: každý vybraný fact je dohledatelný k occurrence a evidenci.

### Fáze 2A — FeatureEngine a definované detektory

- zavést typed FeatureDefinition registry, bounded windows, quality a coverage;
- zavést bezpečný predicate AST bez evaluace libovolného kódu;
- převést nejprve `UNDER_PRESSURE` a `CLOSING` do candidate/active/clearing FSM;
- emitovat STARTED/UPDATED/ENDED pouze na stavové nebo material-revision hraně;
- vystavit validované knobs s units, ranges, cross-field invariants a effective config hash;
- přidat každému triggeru `tuning.policy` a capture requirements;
- zkompilovat CapturePlan; `required` detector bez splnitelného recording kontraktu fail-soft zakázat;
- po prvních testech vytvořit replay labels a baseline pro precision, recall, `F_0.5`, detection delay a flapping;
- ve shadow režimu porovnat nové eventy s dnešními detektory bez změny komentáře.

Exit: ze stejných snapshots a parameter snapshot vznikne bitově stejné pořadí detector transitions; žádný single braking sample neotevře potvrzený pressure event.

### Fáze 3 — StoryCatalog a EpisodeRegistry

- vytvořit schema a parser StoryDefinition;
- migrovat vertical slice: pursuit, pressure, two-front, pass, position, quali attempt, pit, incident, session transition, filler;
- podporovat více současně aktivních epizod;
- oddělit episode lifecycle od speech lifecycle;
- přidat material revision, cadence, conflict a resolution reason.
- zavést bounded EventOpportunityQueue s TTL, priority, urgency, penalty coefficient, correlation a terminal reasons;

Exit: replay dokáže otevřít, aktualizovat a uzavřít epizody bez generování textu.

### Fáze 4 — BeatPlanner a director shadow scoring

- zavést BeatCandidate/BeatPlan a hard eligibility;
- adaptovat dnešní scoring a fatigue;
- sjednotit race a filler kandidáty;
- sjednotit arbitráž queued event opportunity versus přirozený successor aktivního příběhu;
- implementovat deterministickou relation routing a `switch_margin`;
- vynutit jeden just-in-time BeatPlan pouze při volné speech lane;
- během řeči aktualizovat jen facts/episodes a po speech eventu replanovat; nevytvářet prepared waiter;
- ve vývojové větvi logovat legacy vs. nový výběr bez změny audia; tento dočasný dual path nesmí zůstat ve finálním v2 cutoveru;
- kalibrovat thresholdy z replaye.

Exit: každé nové rozhodnutí má score breakdown a důvod select/silence/reject.

### Fáze 5 — RealizationCatalog a authored mode

- auditovat první 64–80 EN patternů z dnešních textů;
- implementovat authored deterministic surface realizer jako předem volený režim, ne jako post-failure fallback;
- během interního řezu zachovat dočasný legacy authored comparison path pro dosud nemigrované families; není to fallback nevalidního Qwen beatu a před final PR se odstraní;
- validovat všechny patterny vůči typed claims a TTS limitům.

Exit: vertical slice funguje bez Ollama a nevytváří nepodložený claim.

### Fáze 6 — Compiled Qwen realizer

- implementovat relevant-only PromptCompiler;
- implementovat auditované `tight`, `balanced` a `loose` PromptOptions a deterministickou policy jejich výběru;
- one-output request, resident warm-up, bounded timeout;
- uložit prompt version/family/pattern/options do tape;
- Qwen failure zahodí beat attempt a vrátí řízení directoru pro výběr jiného beatu;
- stejný beat/revision má nejvýše jeden pokus, bez repair a fallback smyčky.
- jeden planning cyklus smí dispatchnout nejvýše první beat a jednu významově odlišnou alternativu; další failure čeká na nový explicitní impuls.

Exit: replay corpus splní fact safety, coverage a latency gates.

### Fáze 7 — SemanticVerifier a commit gate v2

- oddělit technical TTS validator od semantic verifieru;
- implementovat family claim parser a claim subset/coverage kontroly;
- rozšířit story token o occurrence, lineage a episode revision;
- před TTS znovu posoudit target, relation, order, expiry a conflicts.

Exit: žádný stale nebo významově neplatný generated text nedosáhne TTS v replay testech.

### Fáze 8 — úplná migrace katalogu

- migrovat zbývající event families po malých skupinách;
- kurátorovat minimálně 256 enabled EN pattern cards, čtyři pro každý z 64 beatů;
- převést stávající variants na pattern/authored/style/reject třídy;
- přidat anglickou poslechovou QA;
- v novém runtime odmítnout jiný locale než `en`; legacy CS větev zůstane izolovaná jen do odstranění starého enginu.

Exit: všech 50 relevantních event types má explicitní story/beat/authored coverage nebo zdokumentovaný visual-only status.

### Fáze 9 — atomický breaking cutover

- dokončit všech 60 event-identifier dispositions a odstranit dočasné branch-only shadow/legacy větve;
- spustit Windows/iRSDK/OBS/Ollama/SuperTonic test nad výsledným jediným v2 runtime;
- porovnat audio, tape a obraz a uzavřít všechny blocking issues evidencí z konkrétního branch commit SHA;
- připravit config/API migration note a zálohu poslední v1 konfigurace;
- otevřít jediný human-reviewed PR do `master` s `semver:major` a `BREAKING CHANGE:`;
- rollback je návrat na poslední v1 release/binary + v1 config backup, nikoliv runtime přepínač rodiny.

## 16. Testovací strategie

### 16.1 Timeline unit tests

- každý povolený session subset v kanonickém pořadí;
- přesné deterministické STREAM/SESSION start/end/restart/rewind eventy;
- P/Q/R same-session restart;
- R→Q, R→P, Q→P rewind;
- restart po finish i před green;
- stale sample a krátký rewind bez resetu;
- disconnect/reconnect stejného key;
- nová subsession a track change;
- parent lineage po několika rewindech.

### 16.2 Fact tests

- scope inheritance po každém přechodu;
- current vs. historical vs. superseded;
- Q2 nesmí zdědit current Q1/R1;
- R2 po rewind dědí P1+Q2;
- revalidate facts nejsou automaticky current;
- unknown/NaN/sentinel handling;
- bounded eviction zachová aggregates.

### 16.3 Feature a detector tests

- přímé edge eventy mají deduplikaci a přesné source sequence;
- trend používá správné jednotky, okno, buckety, coverage a correlation identity;
- jeden braking/noise spike neaktivuje `UNDER_PRESSURE`;
- dlouhý významný closing trend splní confirmation a emituje právě jeden STARTED;
- update vzniká jen při material band/revision změně a respektuje minimum interval;
- enter/exit hystereze neflappuje kolem jednoho prahu;
- target change uzavře starou a případně založí novou detector instanci;
- `unknown`, stale a nedostatečná coverage neprojdou jako true;
- `all/any/not` a temporal operátory fungují pro kombinace session, vehicle, race-control, identity a feature states;
- invalid units, ranges a cross-field parameter vztahy odmítne schema;
- replay se stejným config hash vytvoří stejný event stream.

### 16.4 Episode tests

- opening/update/outcome thresholds;
- více aktivních epizod a conflicts;
- target identity change;
- suspend/resume vs. nový příběh;
- outcome bez odvysílaného openingu;
- occurrence reset invaliduje správné instance;
- episode resolution během Qwen inference.
- generation/verification/commit failure vyřadí stejný beat/revision a dovolí jiný eligible successor;
- po vypršení `valid_while` se bez outcome čeká na nový race nebo silence trigger.
- korelovaný event aktualizuje/uzavírá správnou epizodu; nezávislý event ji omylem nepřebírá.

### 16.5 Director tests

- hard gate před scoringem;
- race beat porazí filler;
- ticho pod thresholdem;
- closure bonus bez porušení faktů;
- fatigue až po speaking;
- decaying semantic/pattern penalties;
- deterministic tie-break;
- během speaking nevznikne BeatPlan, prompt ani připravená utterance;
- eventy během speaking aktualizují epizody a po completion se plánuje jen z nejnovějšího stavu;
- mezilehlý zastaralý event se po completion nedočte jako připravená věta;
- event opportunity má deterministické TTL, priority, penalty coefficient a terminal reason;
- naléhavější event přebije successor podle urgency/`switch_margin`, méně naléhavý čeká pouze do TTL;
- bez platného eventu pokračuje přirozený successor; bez obou vznikne ticho;
- neúspěch beatu nekonzumuje opportunity, ale stejný beat/revision se znovu nepokusí;
- `LONG_SILENCE_ELAPSED` je one-shot/rearmed a nevytváří busy loop.

### 16.6 Text a verifier tests

Povinné minimal pairs:

- A closes B / B closes A;
- P13 / P31;
- position gain / loss;
- lead / trail;
- static gap / decreasing gap;
- pass / attack / side-by-side;
- completed lap / completed race;
- current / historical / predicted;
- dry / no rain / sunny;
- Richard + Wright jako dvě identity;
- EN inflexe, artikly a spoken numbers;
- jiný locale než `en` se do nového runtime neroutuje;
- tight/balanced/loose mění pouze auditovaný povrch, ne množinu dovolených tvrzení;
- sampling options i výsledný prompt odpovídají hodnotám uloženým v BeatPlan.

### 16.7 Replay a live acceptance

- raw-input replay testuje detekci i narrative flow;
- accepted-event replay testuje director/realizer izolovaně;
- tape channel/detail matice ukládá právě očekávané record types;
- každý event má validní katalogový `tape_channel` a replay reprodukuje per-channel kick/queue/selection/expiry/spoken počty;
- `none/optional/required` trigger policy kompiluje správný CapturePlan;
- `required` detector bez povoleného nebo zapisovatelného capture se fail-soft zakáže a ostatní runtime pokračuje;
- writer overload zahazuje sampling records před povinnými transitions a vytváří `drop_notice`;
- rotace, retence, restart po neúplném souboru a komprese neblokují event loop;
- replay odmítne nebo explicitně označí nekompatibilní schema/config/catalog hash;
- minimal/normal/full recording má změřený bytes/min a CPU/latency overhead;
- VOD audit používá skutečný `tts_final`, nikoliv jen selected candidate;
- live test měří event-to-building, TTFT, total generation, commit, TTS start a completion;
- restart/rewind se během live testu provede pro každou přítomnou stage.

## 17. Acceptance criteria cílového runtime

### Session a historie

- [ ] Přítomné stage vždy respektují Practice → Qualifying → Race.
- [ ] Restart vytváří nový occurrence a nemaže stream history.
- [ ] R→Q zachová Practice ancestor a superseduje staré Q/R pro current truth.
- [ ] Nový Race po rewind dědí správnou aktivní lineage.
- [ ] Reconnect bez důkazu nevytváří restart.

### Detektory a spouštěče

- [ ] Přímé a lifecycle eventy jsou deterministické, deduplikované a auditovatelné.
- [ ] Komplexní event může kombinovat více typed state, feature a temporal predicates.
- [ ] Doménový stav under-pressure vzniká jen přes potvrzený `battle_behind_v1` lifecycle a fakt `battle.closing(challengerBehind, hero)`, nikdy přímým commentary assignmentem.
- [ ] Každý derived fact/event nese correlation identity, occurrence, confidence, coverage a evidence refs.
- [ ] Enter/exit hystereze, confirmation a material update interval brání flappingu a event stormu.
- [ ] Effective parameters mají schema, units, ranges, config version/hash a jsou reprodukovatelné replayem.
- [ ] Release report uvádí precision, recall, `F_0.5`, detection delay a flapping po session/track type.

### Fakticita a aktuálnost

- [ ] 0 materiálních false accepts v release corpus.
- [ ] 0 role reversals, invented identities, positions, numbers a unsupported outcomes.
- [ ] 0 stale utterances po occurrence/lineage/target change.
- [ ] Každý spoken claim má fact/evidence refs.
- [ ] Upstream false fact je v tape rozlišitelný od LLM hallucination.

### Tok děje

- [ ] Vícebeatová epizoda má nejvýše jeden opening a jeden outcome.
- [ ] Update vzniká pouze na material revision a cadence gate.
- [ ] Outcome je samostatně srozumitelný.
- [ ] Filler se neplete do aktivního kritického děje.
- [ ] Ticho je možné a generický filler není vynucen.
- [ ] Po nevalidním LLM výstupu se stejný beat/revision znovu negeneruje a director může zvolit jiný eligible beat.
- [ ] Po vypršení epizody bez doloženého outcome runtime čeká na nový race nebo silence trigger.
- [ ] Stream/session/speech/long-silence změny vstupují do režie jako deterministické eventy.
- [ ] Speakable eventy mají bounded opportunity queue s TTL, prioritou, urgency, penalty coefficient a terminal reason.
- [ ] Po každém beatu soutěží event opportunities s platnými successors; relation a switch jsou deterministicky vysvětlitelné.
- [ ] Bez platného eventu či successor beatu vznikne ticho.
- [ ] Během řeči nevzniká fronta textů; po completion se rozhoduje z aktuálních opportunities/episodes, ne z fronty připravených vět.

### Výkon

- [ ] Warm Qwen generation P95 ≤ 1,2 s na cílovém stroji; timeout zahodí beat bez retry téhož tématu.
- [ ] Planner + scoring P95 ≤ 20 ms.
- [ ] Žádné blocking I/O v async race loopu.
- [ ] Existuje nejvýše jedna in-flight utterance a žádný prepared waiter.
- [ ] Všechny registry jsou bounded.

### Provoz

- [ ] LLM/TTS/OBS/iRSDK chyba nikdy neshodí main loop.
- [ ] Tape obsahuje úplný timeline→fact→episode→beat→text→commit→audio řetězec.
- [ ] Každý event record má právě jeden validní `tape_channel` a per-channel cadence/kick-rate metriky.
- [ ] Tape lze přes config vypnout nebo zapnout po nezávislých kanálech a úrovních detailu.
- [ ] Každý trigger deklaruje `tuning.policy: none|optional|required` a capture requirements.
- [ ] `required` tuning evidence se nikdy tiše neztratí; nemožnost capture trigger viditelně deaktivuje.
- [ ] Tape má bounded async writer, rotaci, retenci, drop priority a měřený overhead.
- [ ] Stream manifest obsahuje build/schema/catalog/config/model hashes a parameter snapshot IDs.
- [ ] Finální build neobsahuje runtime legacy/shadow přepínač; rollback postup obnoví poslední v1 binary a config backup.
- [ ] Nový runtime emituje pouze EN a nepodporovaný locale má explicitní fail-soft policy.

Poznámka: 0 chyb v malém corpus není matematický důkaz nulového rizika. Release report musí uvést velikost a složení corpus, ne pouze procento.

## 18. Rizika a mitigace

| Riziko | Mitigace |
| --- | --- |
| Přespříliš komplikovaný mega-FSM | ortogonální session/vehicle/race-control/speech/episode osy |
| Historie pronikne do current truth | occurrence + lineage + fact scope hard gate |
| Prahy se přeučí na jednu trať/session | session/track-group split, holdout replay a config hash report |
| Kombinované podmínky vytvoří event storm | detector FSM, hystereze, material bands, min update interval a bounded event rate |
| Full tape zahltí disk nebo CPU | oddělené kanály, detail levels, allowlist, negative sampling, bounded writer, rotace a retence |
| Writer přestane ukládat required tuning data | prioritní records, `drop_notice`, health stav a fail-soft deaktivace pouze dotčeného detectoru |
| Tape bez verzí nepůjde reprodukovat | stream manifest, schema/catalog/build/config/model hashes a immutable parameter snapshot |
| Univerzální prompt přenese cizí příklad | compile only relevant predicate/family rules |
| Qwen bude pouze drahá šablona | A/B authored vs. qwen mode; Qwen musí prokázat poslechovou hodnotu |
| Validator vytvoří opakovanou failure smyčku | jeden pokus na beat/revision, attempt suppression, další výběr musí být jiný beat |
| Stará věta se ozve po změně děje | BeatPlan expiry + commit gate v2 |
| Filler zaplaví stream | ticho, vyšší filler fatigue, nízká priority, one-beat limit |
| Event opportunity queue se změní na opožděný komentář | krátké family TTL, supersession, bounded capacity a commit-time freshness |
| Continuity uzamkne komentář ve starém příběhu | společná arbitráž, urgency classes a auditovaný `switch_margin` |
| Pattern katalog bude příliš drahý | kurace z 2 128 existujících EN strings, vertical-slice rollout |
| Embedding/NLI přidá dependency a latenci | není součást MVP hard gate; volitelný adapter až po měření |
| Reset shodí souběžné komponenty | jediný timeline owner, immutable tokeny, fail-soft reset hooks |

## 19. Observabilita

### 19.1 Provozní log versus NarrativeTape

Provozní log slouží obsluze aplikace: start/stop, warning, error a health. `NarrativeTape` je strukturovaný, versioned a replayovatelný záznam pro ověření chování. Tape se nesmí realizovat jako tisíce DEBUG řádků v běžném logu a jeho detail nesmí určovat globální log level aplikace.

Tape má tři nezávislé kanály:

| Kanál | Účel | Minimální obsah |
| --- | --- | --- |
| `flow` | ověření toku streamu a příběhu | lifecycle/race/silence events, facts, episode transitions, candidates, selection, discard, speech |
| `llm_eval` | ověření realizace a validátoru | BeatPlan, semantic frame, prompt version/options, completion, latency/tokens, verifier claims, commit a skutečný spoken text |
| `detector_tuning` | kalibrace triggerů a features | parameter snapshot, input window/ref, feature values, coverage, predicate trace, candidate/active/clearing transitions a negatives |

Kanály lze zapínat samostatně. Například produkční audit může mít jen úsporný `flow`, zatímco validační session zapne `flow,llm_eval,detector_tuning`.

Každý event record navíc povinně nese jeden katalogový `tape_channel`. Je ortogonální k výše uvedeným účelovým kanálům: `flow` říká, proč record ukládáme, zatímco například `race.battle.closing` říká, ke kterému eventovému toku patří. Díky tomu lze po channelu měřit detector kick, queue, selection, expiry a speech cadence bez parsování event names. Neznámý `tape_channel` je schema/catalog chyba a event se nesmí tiše zařadit do obecného bucketu.

### 19.2 Navržený configurační kontrakt

Názvy keys jsou návrhové; implementační work item stanoví konzervativní odhadnuté defaults, které se po testech mohou versionovaně změnit:

~~~ini
[commentary.tape]
enabled = false
channels = flow
detail = normal                 # minimal | normal | full
output_dir = recordings/commentary
rotate_mb = 64
keep_files = 8
compress_rotated = true
flush_interval_ms = 500

[commentary.tape.flow]
candidate_detail = selected_and_rejected
tape_channel_allowlist = *

[commentary.tape.llm_eval]
capture_prompt = hash           # none | hash | full
capture_completion = true

[commentary.tape.detector_tuning]
trigger_allowlist = under_pressure,closing
negative_sample_interval_s = 5
near_threshold_margin = 0.15
capture_input_windows = true
~~~

Hlučnost a objem řídí současně `channels`, `detail`, allowlist, negative sampling a rotace. STARTED/UPDATED/ENDED, errors, discards a required-tuning evidence se nesmějí náhodně samplovat. Pravidelná negativní/background evidence se samplovat smí.

### 19.3 Trigger-driven capture plan

Při načtení catalogu sestaví `TapePolicyCompiler` efektivní capture plan z globální konfigurace a `tuning` vlastností triggerů:

~~~text
CapturePlan(d) = combine(
    tape.enabled,
    enabled_channels,
    detail,
    trigger_allowlist,
    d.tuning.policy,
    d.tuning.parameters,
    d.tuning.capture
)
~~~

Pravidla:

- `none`: trigger nikdy nevynutí high-volume feature windows;
- `optional`: detailní tuning capture vznikne pouze při zapnutém kanálu a povoleném triggeru;
- `required`: plán musí obsahovat effective parameters, pre/post window, feature frame, predicate trace, všechny detector transitions a definované negative samples;
- released production catalog smí obsahovat pouze `none|optional`; `required` je povolen jen pro detector označený `experimental=true`, který operátor explicitně zapnul;
- required detector se aktivuje až po úspěšném recorder preflightu. Ztráta zapisovatelnosti za běhu vyvolá `CAPTURE_UNAVAILABLE`, deterministicky ukončí jeho active facts/events reasonem `required_capture_lost` a zakáže pouze tento detector; main loop a ostatní detektory pokračují;
- změna detector algorithm version nebo material parameter schema vrátí policy do `required`, dokud ji nová evidence nepromuje;
- výsledný plan, catalog versions, git/build version a všechny config hashes patří do stream manifestu.

Plný parameter snapshot se zapisuje jednou do manifestu a dostane `parameter_snapshot_id`. Jednotlivý detector record nese tento odkaz a relevantní použité hodnoty/prahy. Tím je tape úplný, ale neopakuje celý config v každém ticku.

Kick-rate funnel má pevné hranice. `kick` je pouze detector FSM přechod do `active` před EventManager arbitráží; jde o transition, ne o požadavek zavést nový `*_STARTED` V4 event identifier. Candidate tick ani near-threshold sample se jako kick nepočítá. `accepted` je publikace EventManagerem, `queued` vznik EventOpportunity, `selected` rezervace BeatPlanu a `started` playback acknowledgement. Read-only `DetectorObservation` tape tap se proto nachází mezi DetectorBank/EventEmitterem a EventManagerem. Do NarrativeRuntime vstupují jen accepted NarrativeEventy; potlačený kandidát nikdy neotevře ani nereviduje speakable epizodu, ale nezastaví nezávislou FactView aktualizaci, která smí existující stav zavřít či invalidovat.

### 19.4 Co se ukládá a kdy

`detector_tuning` používá malý bounded pre-trigger ring pro tunable feature samples. Ring se flushne při candidate/active/clearing transition, near-threshold negative sample nebo explicitní marker události. `post_window_s` se doplní následnými samples. Nemá se ukládat celý raw tick stream, pokud jej konkrétní trigger nepotřebuje.

Základní typy records:

- `stream_manifest`: schema/build/catalog/model/config versions a hashes;
- `input_sample` nebo `input_window_ref`: pouze fields potřebné daným features;
- `feature_frame`: hodnoty, units, quality, coverage a evidence refs;
- `detector_decision`: predicate tree s true/false/unknown, prahy, transition a reason;
- `event_opportunity`: event ref, `tape_channel`, TTL, priority, urgency, penalty coefficient, queue/terminal state a reason;
- `narrative_decision`: facts, episodes, event/successor kandidáti, jejich relace, hard-gate reasons a score breakdown;
- `llm_attempt`: BeatPlan, prompt metadata/obsah dle configu, completion, latency, tokens a verifier;
- `speech_exposure`: committed text, backend playback acceptance (`SPEECH_STARTED`), completion/interruption/failure;
- `drop_notice`: počet a typ záznamů zahozených při writer overload nebo I/O chybě.

Tape writer je samostatná vlastněná async task s bounded record queue. Tato technická fronta neobsahuje připravené věty a není commentary queue. Nikdy neblokuje race loop. Record priority je odvozená `sample|normal|critical`: periodic negatives/background; běžný flow/LLM detail; lifecycle/reset/gap/health/speech terminal/verifier reject a všechna required-tuning evidence. Incoming sample se při plné frontě zahodí; normal nejdřív eviktuje nejstarší sample, jinak se zahodí; critical eviktuje nejstarší sample, potom normal. All-critical overflow se zapíše do bounded `TapeLossAccumulator` mimo queue a degraduje recorder. Accumulator drží pouze registry-bounded counts a first/last time/reducer ranges, při první možnosti vytvoří critical `drop_notice` a vždy vstoupí do traileru/operational error path. Ztráta required evidence navíc fail-soft deaktivuje pouze příslušný experimental detector.

### 19.5 Retence a reprodukovatelnost

- JSONL/kompaktní versioned record schema musí být čitelné bez běžícího LLM;
- rotace a maximální retence jsou povinné; komprese rotated souborů smí použít stdlib;
- každý record má process identity, nullable broadcast/stream epoch, monotonic timestamp, purpose a record priority; reducer sequence má jen actor-ordered record a occurrence/lineage patří do typovaného payloadu tam, kde existují;
- citlivá nebo nepotřebná raw pole se nezapisují; capture je allowlist-based;
- replay musí umět ověřit config/catalog hash a explicitně označit nekompatibilní schema;
- ruční ground-truth labels se ukládají jako samostatný sidecar, nemění immutable původní tape.

### 19.6 Decision record

Každé director rozhodnutí musí být vysvětlitelné minimálně těmito poli:

~~~json
{
  "streamEpoch": 3,
  "occurrenceId": "race:2",
  "lineageId": "P1/Q2/R2",
  "episodeId": "battle_ahead:hero:page:7",
  "episodeRevision": 4,
  "triggerEvent": "HUNTING",
  "tapeChannel": "race.battle.closing",
  "candidateOrigin": "event_opportunity",
  "relationToPreviousEpisode": "updates",
  "beatRole": "update",
  "eligible": true,
  "score": {
    "base": 64,
    "continuity": 6,
    "material": 10,
    "eventPenalty": -3,
    "fatigue": -6,
    "staleness": 0,
    "final": 71
  },
  "requiredSwitchMargin": 8,
  "requiredFactIds": ["relation:17", "gap:91"],
  "realizationFamily": "battle.closing",
  "realizationPattern": "reels_in",
  "realizationBackend": "qwen_compiled",
  "promptOptions": {
    "freedom": "tight",
    "patternChoice": "fixed",
    "optionalClaimLimit": 0,
    "maxSentences": 1,
    "temperature": 0.2,
    "topP": 0.8
  },
  "generationMs": 530,
  "verification": "accepted",
  "commit": "current",
  "speech": "completed"
}
~~~

### 19.7 Agregované metriky

Agregované metriky:

- lifecycle/race/silence event counts a event-to-director latency;
- per-`tape_channel` detector kick, queued, updated, selected, consumed, expired, superseded a spoken counts/rates;
- per-`tape_channel` event→speech latency, cadence intervals, queue age a důvody, proč event prohrál se successor beatem;
- detector precision/recall, detection delay, flapping, unknown/coverage rejects a effective config hash;
- event a episode coverage;
- opening/update/outcome counts;
- selected/silence/rejected/replaced/stale;
- eventy přijaté během speaking a počet mezistavů správně přeskočených při replanu;
- event-versus-continuation decisions, story switches a použitý `switch_margin`;
- výběr tight/balanced/loose profilů a verifier výsledky po profilu;
- verifier kódy a ručně potvrzené false accept/reject;
- filler share a repetice;
- Qwen TTFT/total/cold a discard reasons;
- age at commit a age at TTS start;
- restarty/rewindy a invalidované položky;
- orphan outcomes a stories bez closure;
- cross-session historical claim usage.

## 20. Config a API dopad

Tento planning dokument runtime ani veřejný config nemění, ale finální v2.0.0 má explicitně breaking config/API kontrakt. Public config surface je před implementací uzavřen na tyto skupiny:

Přesné typy, defaults, ranges, jednotky, apply boundaries, migrační tabulka a HTTP golden examples jsou zmrazeny v branch-only dokumentu [`v2.0.0/public-contracts.md`](v2.0.0/public-contracts.md). Tato sekce je jeho architektonický souhrn; při rozporu blokuje implementaci a oba dokumenty se musejí znovu sjednotit v #235.

| Sekce | Keys |
| --- | --- |
| `[commentary]` | `enabled`, `max_utterance_s`, `driver_name`, `driver_nickname`, `tone_source` (`none | heart_rate`) |
| `[commentary.director]` | `selection_threshold`, `switch_margin`, `global_min_interval_s`, `long_silence_s`, `opportunity_capacity`, `active_episode_capacity`, `resolved_episode_capacity`, `decision_capacity`, `max_consecutive_story_beats`; NarrativeMailbox zůstává pevný invariant 64/56+7+1 |
| `[commentary.llm]` | `enabled`, `base_url`, `model`, `timeout_s`, `max_tokens`, `warmup`, `max_profile` |
| `[commentary.tts]` | `backend`, `voice`, `rate`, `steps`, `audio_device`, `duck_input`, `duck_ratio`, `duck_fade_ms` |
| `[commentary.detectors]` | `profile`; pouze catalogem exportované overrides používají `[commentary.detector.<id>]` |
| `[commentary.tape]` a podsekce | keys přesně podle § 19.2 včetně `tape_channel_allowlist` |

Catalog defaults vlastní per-event TTL/priority/urgency/penalty, story continuation/switch policy, cadence a allowed contexts. Tyto hodnoty se nekopírují do globálního INI. Deployment override smí existovat pouze pro pole označené `exposed=true` s typem, units, range a cross-field validací.

Breaking migrace nahradí `commentary.use_hr_emotion` explicitním `tone_source`; odstraní globální `commentary.cooldown_s`, `sector_speak*`, `session_briefs`, `stream_start`, `gap_hunt_tts_*`, `llm_polish`, `llm_*`, celou `[commentary.scheduler]` a `[commentary.graph_runtime]`. Odpovídající význam se přesune do nových sekcí nebo katalogu; `llm_max_attempts` nemá náhradu, protože kontrakt je právě jeden attempt. Starý key vyvolá konkrétní migration warning, ale v paměti se automaticky nepřekládá: commentary pro tuto config generation zůstane disabled, zatímco scene-switch služba pokračuje. Neplatný v2 commentary config stejně nastaví commentary health `disabled_invalid_config` a zbytek aplikace pokračuje.

Reload policy:

- event taxonomy, ID/units schema, detector/story/beat/realization catalog, kapacity a detector parameters jsou immutable pro stream epoch; změna je `restart_required` nebo platí až od příštího `STREAM_STARTED`;
- tape enable/detail/allowlist/retention se může změnit atomicky na record boundary a vytvoří novou config generation;
- LLM endpoint/model/timeout/profile cap a TTS device/voice se mohou změnit až pro příští BeatPlan/utterance; in-flight práce doběhne nebo se explicitně zruší podle lifecycle policy;
- každý applied config generation a hash se zapisuje do tape; souborový hot reload bez `ConfigUpdate` je zakázaný.

### 20.1 Veřejné commentary API v2

Stávající route names mohou zůstat, jejich payload je breaking a vždy nese `schemaVersion: commentary-runtime/2`:

- `GET /api/commentary/status`: runtime/health, fixed language `en`, timeline identity, speech state, queue depths, active/resolved counts, catalog/config hashes, recorder/model/detector status a per-`tape_channel` counters;
- `GET /api/commentary/decisions?limit=N`: bounded newest-first decision records se score, relation, source opportunity/successor, terminal reason a tape channel;
- `POST /api/commentary/validate`: localhost+CSRF offline validační request `{text, beatId, factBindings}`; nikdy nemění live state;
- `POST /api/commentary/speak`: localhost+CSRF manual EN TTS test přes stejnou speech lane, nikdy nepreemptuje live utterance a nezapisuje narrative exposure; actor admission používá pouze process-local one-shot latch s pevným 1 000ms timeoutem a atomic abandon, takže zamítnutý/timeout request později nepromluví;
- `GET /api/commentary/assignments` se ve v2 odstraní; planning/text-assignment endpoint není runtime contract.

`GET /health` zůstává overall-service health a commentary degradace jej sama nemění na HTTP failure. Přidá pouze bounded komponentní summary `commentary.status/reason`; detail zůstane v `/api/commentary/status`. Implementace musí současně aktualizovat `API.md`, `CONFIG.md`, `config/config.example.ini` a dashboard/test page.

## 21. Docs impact

**Updated docs:**

- `docs/commentary_narrative_runtime_spec.md` — nový cílový návrh;
- `docs/v2.0.0/README.md` — úplný issue/dependency index pro realizaci v2.0.0;
- `docs/v2.0.0/design-freeze-audit.md` — předimplementační konflikty, uzavřená rozhodnutí a blocking artifacts;
- `docs/v2.0.0/event-beat-disposition.md` — úplná branch-only matice 60 identifikátorů, 54 legacy nodes a 64 cílových beatů;
- `docs/v2.0.0/public-contracts.md` — přesné branch-only config defaults/ranges, migrace a HTTP golden payloads;
- `docs/v2.0.0/actor-transition-contract.md` — přesný branch-only actor/mailbox/speech/reset/shutdown přechodový kontrakt;
- `docs/v2.0.0/schema-contracts.md` — přesné branch-only DTO/version/identity/tape/reason kontrakty;
- `docs/v2.0.0/fact-feature-registry.md` — uzavřený branch-only registr faktových predikátů, skalárů/jednotek, feature IDs, claim allowlistů a `tape_channel` taxonomie;
- `docs/v2.0.0/detector-catalog-freeze.md` — přesný branch-only katalog temporal/composite matematiky, odhadnutých rozsahů, hystereze a two-front identity;
- `docs/v2.0.0/realization-verifier-contract.md` — přesný branch-only controlled-EN/verifier kontrakt pro všech 37 realizačních rodin;
- `docs/v2.0.0/vertical-slice-fixtures.md` — dvacet osm branch-only očekávaných decision/reducer/speech scénářů;
- `docs/v2.0.0/final-pr-exclusion-manifest.md` — povinný seznam planning/temporary položek odstraněných před PR do masteru;
- `README.md` — odkaz na v2.0.0 implementační index;
- `COMMENTARY_ENGINE.md` — odkaz na návrh, současný engine zůstává current-behavior autoritou.

Tyto planning změny existují pouze ve v2 vývojové větvi. Úplný seznam je v `final-pr-exclusion-manifest.md`; finální breaking PR je nesmí přenést do `master` a odstraní i manifest samotný a dočasné odkazy z `README.md`/`COMMENTARY_ENGINE.md`. Trvalá rozhodnutí se v PR projeví pouze implementací, testy, migration note a aktualizovanou dokumentací skutečného v2 chování.

**Pending při implementaci:**

- `COMMENTARY_ENGINE.md` — přepsat až po aktivaci nového runtime;
- `CONFIG.md` + `config/config.example.ini` — nové keys/defaulty a migrace;
- `API.md` — povinně pro breaking commentary API v2 z § 20.1;
- replay/VOD test dokumentace — acceptance evidence každé migrované rodiny.

**Docs: no change pro planning commit:** build/deploy a VR setup. Finální v2 PR musí BUILD_AND_DEPLOY znovu posoudit podle výsledného balení/modelových prerequisites.

## 22. TDD výjimka tohoto work itemu

**TDD-exception:** jde o docs-only specifikaci bez runtime změny.
**Verification:** kontrola proti `master@0ce75d4`, inventura graph assets, kontrola odkazů a konzistence datových/lifecycle kontraktů.
**Risk:** návrh může podcenit konkrétní iRSDK reset signal nebo live latenci.
**Mitigace:** branch-only shadow timeline, raw-input replay, explicit unknown, předem volený authored režim pro kritické rodiny a povinný Windows/iRSDK/OBS acceptance před atomickým cutoverem.

## 23. Follow-up — formální graf a 3D mapa beatů

Tato část má dvě úrovně závaznosti:

- matematické vztahy v § 23.1–23.5 a základní loader kontroly z § 23.6 jsou cílový blocking kontrakt refaktoru;
- samostatný reportovací analyzátor, 3D projekce a editor v § 23.7–23.8 jsou následné offline nástroje.

### 23.1 Stav a deterministický event reducer

Stav runtime v logickém čase `t`:

~~~text
S_t = (T_t, F_t, E_t, Q_t, X_t, A_t)

T = poslední immutable stream/session timeline projection a active lineage
F = poslední immutable FactView projection
E = EpisodeRegistry
Q = bounded EventOpportunityQueue
X = ExposureStore
A = speech stav + attempted beat/revision set
~~~

Každý typovaný event `e_t` provede jediný deterministický přechod:

~~~text
S_(t+1) = R(S_t, e_t)
~~~

Pro stejný počáteční stav a stejně seřazené commands musí `R` vytvořit stejný stav. LLM není součástí `R`; pouze realizuje význam již vytvořeného BeatPlan. Externí accepted order je `(fanout_stream_sequence, source_ordinal)` a actor zaznamená celkový `reducer_sequence`, takže shodný timestamp nevytvoří nejednoznačné replay pořadí.

Pokud `speech_state != idle`, reducer aktualizuje `T/F/E/X`, ale director nevytváří další BeatPlan. Po `SPEECH_COMPLETED` nebo `SPEECH_INTERRUPTED` platí:

~~~text
next_plan = D(S_latest), ne D(S_at_previous_speech_start)
~~~

Tím je formálně vyloučena fronta připravených vět. `Q` uchovává pouze speakable význam eventu a jeho scheduling metadata:

~~~text
q = (event_ref, episode_ref, correlation_key, tape_channel,
     created_at, expires_at, priority, urgency_class,
     penalty_coefficient, material_revision, terminal_state)
~~~

Pro každý `q ∈ Q_t` musí platit bounded capacity a právě jeden terminální důvod `consumed | expired | superseded | invalidated | evicted`. Overflow nesmí blokovat reducer; eviction policy chrání critical urgency a vždy vytváří audit record.

### 23.2 Formální graf definic

Story catalog tvoří orientovaný typovaný property graph:

~~~text
G = (V, E)

v ∈ V = BeatDefinition + vlastnosti story family, role a context
e ∈ E = (source, target, edge_type, guard, preference)
edge_type ∈ {preferred, allowed, closure, forbidden}
guard: S → {true, false}
~~~

Episode je runtime instance definice, nikoliv další statická věta v grafu. Hrana vyjadřuje možnost návaznosti, ne příkaz bezpodmínečně promluvit.

Množina platných následníků beatu `b` ve stavu `S`:

~~~text
Succ(b, S) = {
  v | existuje (b, v, type, guard, preference) ∈ E
      kde type ∈ {preferred, allowed, closure}
      AND guard(S)
      AND Eligible(v, S)
      AND neexistuje aktivní (b, v, forbidden, forbidden_guard, _)
          pro které forbidden_guard(S)
}
~~~

### 23.3 Způsobilost, validita a výběr

Hard eligibility je konjunkce booleovských predikátů:

~~~text
Eligible(b, S) =
    phase_allowed(b, S)
AND occurrence_current(b, S)
AND lineage_current(b, S)
AND required_facts_available(b, S)
AND confidence_sufficient(b, S)
AND episode_valid(b, S)
AND not_expired(b, S)
AND not_conflicting(b, S)
AND cadence_allowed(b, S)
AND audience_allowed(b, S)
AND (beat_id, episode_revision) NOT IN attempted(S)
~~~

Kandidátní množina a výběr:

~~~text
C_event(S) = {candidate(q) | q ∈ Q AND opportunity_valid(q, S)}
C_successor(S, b_prev) = Succ(b_prev, S)
C_other(S) = {b | Eligible(b, S)
                  AND source_guard(b, S)
                  AND b není successor ani event candidate}

C_raw(S, b_prev) = dedupe(C_event ∪ C_successor ∪ C_other,
                          key=(beat_id, episode_id, episode_revision))

EffectiveScore(b,S) = EventScore(source_opportunity(b),S)  for event-backed candidate
                    = ContinuationScore(b,S)              for successor candidate
                    = Score(b,S)                          otherwise

C_threshold(S) = {b ∈ C_raw | EffectiveScore(b, S) >= selection_threshold}

P(S) = best candidate in C_threshold that continues the focused episode
       through a successor edge or event relation updates/resolves;
       NONE when no such candidate exists

Admit(b, P, S) = true                                      if P = NONE
               = true                                      if b continues P's episode
               = true                                      if urgency(b) > urgency(P)
               = EffectiveScore(b,S) >= EffectiveScore(P,S)+director.switch_margin otherwise

C_ok(S) = {b ∈ C_threshold | Admit(b, P(S), S)}

sort_key(b) = (-urgency_rank(b), -EffectiveScore(b,S),
               candidate_order(b).reducer_sequence,
               candidate_order(b).source_ordinal,
               episode_id(b), beat_id(b))

b* = candidate with lexicographically minimum sort_key

Select(S) = b*       pokud C_ok(S) není prázdná
          = SILENCE  jinak
~~~

Focused episode je epizoda posledního playback-accepted narrative beatu, pokud stále existuje a je active/resolved se speakable closure; ostatní EpisodeRegistry položky nejsou implicitně „current story“. `source_guard` vyžaduje skutečný event/silence impulse, material revision nebo explicitně povolený active-episode beat; pouhá existence BeatDefinition nesmí sama vyrábět řeč. Při deduplikaci stejného beatu/revision se zachová nejstarší `candidate_order`, nejvyšší urgency/score a všechny source refs; nevzniknou dva attempts. Při shodě urgency a skóre platí pevný tie-break: nižší `candidate_order=(origin_reducer_sequence, source_ordinal)`, potom lexikograficky nižší `episode_id` a `beat_id`. Skóre z § 9.2 ovlivňuje pouze pořadí již způsobilých kandidátů; nemůže změnit `Eligible=false` na pravdu. `replacement_cost` se odečítá pouze od challenger kandidáta, který chce zrušit právě building precommit plan; nikdy nesnižuje focused continuation nebo už committed utterance.

Pro event opportunity `q` a successor `b_s`:

~~~text
EventScore(q, S) = Score(candidate(q), S)
                 - q.penalty_coefficient × ChannelPressure(q.tape_channel, S)

ContinuationScore(b_s, S) = continuation_base(episode(b_s))
                          + edge_preference(b_prev, b_s)
                          + material_change_bonus + closure_urgency + continuity_bonus
                          - fatigue - staleness

SwitchToEvent(q, b_s, S) =
    relation(q, episode(b_s)) ∈ {updates, resolves}
 OR urgency(q) > urgency(b_s)
 OR EventScore(q, S) >= ContinuationScore(b_s, S) + director.switch_margin
~~~

Pokud `relation(q, active_episode) ∈ {updates, resolves}`, event patří do pokračovací množiny a nepotřebuje switch margin; stále však musí projít hard gate, threshold a běžné pořadí proti jiným pokračováním. Pro `independent` nebo `conflicts` zahajuje či přepíná příběh pouze přes urgency/margin pravidlo. Funkce `relation` je katalogová a korelační, nikoliv vektorová. Když event nevyhraje, zůstává v `Q` jen do TTL a může soutěžit v dalším director passu.

Validita časového tvrzení musí zahrnout také coverage. Pro predicate `p`, okno `Δ` a minimální coverage `c_min`:

~~~text
HeldFor(p, Δ, t) =
    coverage([t-Δ, t]) >= c_min
AND p(sample) platí pro všechny použitelné samples v okně
~~~

Chybějící nebo stale coverage vrací `unknown`, nikoliv `true`.

### 23.4 Lineage a množiny faktů

Pro occurrence `o` na aktivní lineage `L`:

~~~text
Current(o) = {f | f.occurrence = o AND f.status = current}

Inherited(o, L) = {
  summary(f) | f.occurrence ∈ Ancestors(o, L)
               AND f.scope dovoluje dědění
               AND f.status != superseded
}

Speakable(o, L) = Current(o) ∪ Inherited(o, L) ∪ ExplicitHistoricalClaims(o, L)
~~~

Occurrence ze superseded větve není členem `Ancestors(o, L)`. Historický fakt proto smí vstoupit do BeatPlan pouze přes explicitní historical/recap claim, nikdy implicitně jako current truth.

### 23.5 Jazyková volnost, validace a podobnost

Nechť `L(C)` je množina všech anglických utterances, jejichž tvrzení jsou přesně povolena claim frame `C`. Dynamické prompt profily smějí rozšiřovat pouze povrchovou množinu:

~~~text
A_tight(C) ⊆ A_balanced(C) ⊆ A_loose(C) ⊆ L(C)
~~~

Změna `temperature`, `top_p`, pattern poolu nebo clause order tedy nesmí rozšířit claim frame. SemanticVerifier nadále vyžaduje:

~~~text
claims(text) ⊆ closure(required ∪ selected_optional)
required ⊆ claims(text)
~~~

Embedding může vytvořit pouze měkkou penalizaci podobnosti:

~~~text
repeat_penalty(text, H) =
    λ × max_(h ∈ recent_spoken(H)) max(0, cosine(embed(text), embed(h)))
~~~

Tato hodnota se smí odečíst od skóre nebo použít pro výběr patternu. Nesmí rozhodovat o fakticitě, směru vztahu ani validitě successor hrany.

Deterministický replay se dělí na dvě úrovně. Reducer/director/authored pattern selection musí ze stejného tape a catalog/config hash vybrat stejný beat i pattern; pseudonáhodná volba používá seed odvozený ze `stream_epoch + opportunity_id + beat_id + episode_revision`, ne process-global RNG. Qwen text se pro decision replay neregeneruje: použije se zaznamenaná completion. Samostatný model eval může request zopakovat, ale kvůli backend/hardware nondeterminismu porovnává claim verdict a latency distribuci, nikoliv byte-identický text. Tape proto vždy nese model identifier/digest, prompt hash/content policy, sampling options, případný seed a skutečnou completion.

### 23.6 Statická matematická validace grafu

Blocking `NarrativeCatalog` loader musí bez nové dependency kontrolovat minimálně:

- dosažitelnost všech beatů z deklarovaných deterministic/race/silence triggerů;
- orphan nodes a nechtěné dead ends;
- strongly connected components bez terminal/exit hrany;
- cykly bez cadence, expiry nebo material-revision bariéry;
- splnitelnost edge guardů nad konečnými doménami session/vehicle/role stavů;
- současně splnitelné konfliktní/exclusive beaty;
- existenci self-contained outcome cesty;
- maximální branching factor a bounded path exploration;
- coverage event family → episode → beat → realization pattern;
- replay path coverage včetně restartů, rewindů a silence triggerů.

Referenční integrita, reachability, terminal/exit hrana každé SCC a cadence/expiry/material bariéra cyklu jsou release-blocking. Složitější splnitelnost guardů a kontrafaktuální enumerace mohou používat samostatný offline `StoryGraphAnalyzer`; jeho absence nesmí omluvit dangling edge, orphan beat nebo neomezený runtime cyklus. Pro složité guardy lze později použít SAT/SMT adapter, ale první verze má preferovat vyčerpávající enumeraci malých typovaných domén a nepřidávat produkční dependency.

### 23.7 3D projekce a runtime trace

3D mapa je projekční funkce, nikoliv runtime rozhodnutí:

~~~text
P: V → R³

P(v) = (
  narrative_progress(v),
  story_family_coordinate(v),
  session_context_layer(v)
)
~~~

- osa X: opening → update → outcome a úroveň v condensation DAG;
- osa Y: story family nebo kurátorovaná/embeddingová tematická blízkost;
- osa Z: lobby/practice/qualifying/race context layer;
- barva: beat role;
- velikost: base priority;
- průhlednost: runtime eligibility/fatigue;
- styl hrany: preferred/allowed/closure/forbidden;
- animovaná stopa: skutečná posloupnost vybraných beatů pro occurrence/lineage.

Další vlastnosti, například vehicle phase, confidence, prompt freedom nebo required facts, patří do filtrů a detailu uzlu; nesmějí být násilně stlačeny do tří souřadnic. Embedding může pomoci pouze s layoutem osy Y nebo detekcí podobných uzlů. Geometrická vzdálenost v 3D nesmí sama vytvořit successor ani obejít guard.

### 23.8 Follow-up realizační krok

Po stabilizaci StoryCatalog a replay formátu:

1. vytvořit read-only `StoryGraphAnalyzer` s JSON/CLI reportem;
2. přidat CI kontroly reachability, dead ends, trap cycles, guard conflicts a coverage;
3. exportovat statický projection payload bez vazby na live loop;
4. vytvořit interaktivní 3D viewer s filtry session/family/role;
5. umět nad mapou přehrát NarrativeTape a zvýraznit active lineage, selected, discarded a skipped beaty;
6. případný editor smí navrhnout změnu katalogu, ale výstup vždy znovu projde schema a graph analyzátorem.

Acceptance follow-upu:

- stejný katalog vytváří deterministický validační report;
- žádný nezdokumentovaný unreachable node ani neukončitelná SCC;
- viewer přesně reprodukuje replay path a restart/rewind lineage;
- změna 3D layoutu nemění runtime rozhodnutí;
- analyzer/viewer není produkční dependency a jeho chyba neovlivní main loop.

## 24. Krizová kontrola proveditelnosti

### 24.1 Verdikt

Návrh je technicky proveditelný na současném Python/aiohttp/pydantic základu bez nové produkční databáze nebo ML dependency. Vývoj proběhne inkrementálně a test-first v jediné v2 větvi, ale dodání je atomický breaking cutover. Do `master` nepůjdou dílčí family migrace, dual runtime ani planning docs. Dočasný shadow/legacy comparison je povolen pouze uvnitř větve a před finálním PR musí zmizet.

První implementaci neblokuje chybějící měřicí corpus. Odhadnuté konzervativní prahy jsou přijatelné, pokud jsou označené, versioned a opt-in/shadow. Data z prvních testů potom slouží ke kalibraci. Implementaci naopak blokuje nejasný datový kontrakt nebo vlastnictví stavu: bez stabilní identity, hodin, units, unknown semantics a dependency direction by vznikly dvě konkurenční pravdy.

### 24.2 Kritické podmínky před production aktivací

| Oblast | Stav na masteru | Nutný krok |
| --- | --- | --- |
| Session/stream vlastnictví | rozdělené mezi `logic/`, overlay SessionCoordinator, RunClock a narrative FSM | jeden `logic/StreamTimeline`, definovaná precedence OBS/iRSDK a transition reasons |
| Session plan/order | raw `SessionInfo.Sessions[]` je dostupný, ale `SessionContext` drží jen current track/roster | typovaný seznam přítomných supported stages pro preview/lineage; neodvozovat chybějící stage |
| Stream-before-session | OBS může být active dřív než vznikne coherent SessionRef | explicitní stream-scope stream-lifecycle nebo přísný lobby filler s nullable occurrence; žádná syntetická session ani obecný filler bez faktů |
| Vehicle phase | `on_pit_road`, track surface, speed a parade SessionState existují; in/out-lap je dnes lokální heuristic v RaceObserver | jeden versioned VehiclePhase classifier s unknown/hysteresis a immutable projection |
| Broadcast context | `SwitchState.mode` rozlišuje lobby/garage/race/replay/loading | čistý mapovací DTO z `logic/`; žádná raw OBS scene name ani mutable state read v commentary |
| Gap feature | přibližný fractional-distance × hero lap-time odhad; 3s regrese | versioned estimator, quality/invalidation kontrakt; první odhad může zůstat `estimated_v1` |
| Trigger schema | část detektorů má vlastní hardcoded/config FSM | typed feature registry, predicate AST, correlation identity a společný lifecycle |
| Speech lane | ProcessTtsSink drží in-flight + jeden waiter a generuje uvnitř workeru | odstranit waiter, přidat atomické `try_start`, completion event a replan z aktuálního stavu |
| TTS hang/cancel | backend callback není garantovaný | tokenizované start/playback/stop watchdogs, bounded process/audio cancel a quarantine bez pádu main loopu |
| Tape | eventově orientovaný overlay tape; commentary/LLM detail závisí na DEBUG | samostatný channel-based NarrativeTape, povinný `tape_channel`, CapturePlan a bounded writer |
| Semantic verifier | převážně regex/lexikon family checks | controlled-EN parser pro všech 37 families; production nejprve pouze `tight`, každá nerozpoznaná významová fráze je reject |
| Data/context extras | weather, SoF, roster, flags, incident aftermath, timing a HR už mají fail-soft extractory/FSM | přesunout výstup do typed facts; volitelné/missing zdroje znamenají ineligible beat, ne implementační blok |
| Nepodporovaná pravda | fyzický první audio sample, oficiální post-race classification a obecné pochopení volné EN nejsou spolehlivě k dispozici | nejsou runtime claimem; používat software playback acceptance, observed finish a controlled EN |
| Runtime evidence | šest eventových tapes, přibližně 5,6 MB; ne kontinuální trendová data | lze začít bez nich, ale testovací rollout musí zapnout tuning capture |
| Live výkon | Qwen změřen lokálně, nikoliv celý Windows/Ollama/TTS řetězec | end-to-end TTFT, generation, synth, audio-start a resource-contention acceptance |
| Test prostředí | project test extra existuje; worktree používá ověřený sdílený venv nebo vlastní reproducible venv | před prvním runtime commitem uložit baseline suite výsledek a stejné prostředí používat pro charakterizační testy |

### 24.3 Nutné architektonické opravy

Původní pracovní názvy `race/timeline.py`, `race/detectors.py` a `race/episodes.py` nerespektovaly plně vrstvy projektu. Cílové vlastnictví je:

- `logic/stream_timeline.py`: stream chapters, session occurrence a lineage;
- `events/features.py`: interpretace immutable RaceState snapshotu, číselné features, windows a quality;
- `events/facts.py` + `events/detectors.py`: sportovní facts, detector FSM a candidate/typed eventy;
- `commentary/episodes.py`: pouze řečový/narativní svět a beat continuity;
- `commentary/tape.py`: narrative/LLM/tuning records, nikoli rozšíření private overlay tape.

Je nutné zavést malé neutrální schema kontrakty nebo dependency injection tak, aby `events/` neimportovalo commentary a `commentary/` nečetlo mutable RaceObserver. Jinak se refaktor rozpadne na kruhové importy a dvojí reset hooks.

### 24.4 Nejtěžší technická místa

1. **Přesná session lineage:** reconnect, loading, SessionNum změna a SessionTime rewind mají částečně stejné symptomy. Transition precedence a debounce musejí být jediným zdrojem pravdy.
2. **Gap a target identity:** dobrý trend nad špatnou nebo přepnutou gap metrikou dává přesvědčivě chybný event. Každé okno musí patřit stejné target identity a occurrence.
3. **No-queue speech:** odstranění waiteru je proveditelné, ale musí zůstat bounded EventOpportunityQueue a current/resolved episode state s krátkou family TTL. Jinak se během dlouhé řeči ztratí pass nebo finish; ukládá se význam světa a scheduling metadata, nikoliv připravená věta.
4. **Semantic verification:** úplná významová kontrola volné angličtiny není spolehlivě řešitelná několika regexy. Tight controlled realization je proveditelná; balanced/loose vyžadují rozšířenou auditovanou rodinnou gramatiku a výrazně větší verifier corpus. Druhý model smí být offline eval signál, nikdy autoritativní live fact gate.
5. **Recorder backpressure:** required tuning capture a zásada „main loop nikdy nespadne“ jsou v napětí. Řešení je prioritní bounded writer a deaktivace pouze dotčeného experimentálního detectoru, nikoliv synchronní disk I/O.
6. **Konfigurační exploze:** pokud každý beat a detector dostane desítky vah, systém nebude laditelný. Vystavují se pouze interpretovatelné knobs; ostatní zůstávají versioned catalog defaults.
7. **Post-beat arbitráž:** bez explicitní priority pokračování by runtime buď mechanicky dokončoval zastaralý příběh, nebo jej každý nový event rozbil. Jedna kandidátní množina, urgency class, `switch_margin` a deterministická event↔episode relation jsou proto nutnou součástí runtime, ne volitelný polish.
8. **Stream scope bez session:** OBS lifecycle může být pravdivý bez iRSDK occurrence. Vynucení non-null occurrence by vedlo k falešné session nebo ztrátě stream opening; null je proto povolen pouze explicitně stream-scoped DTO.
9. **Volitelné zdroje:** HR, weather, roster/SoF nebo přesný opponent nejsou vždy dostupné. Jejich absence nesmí degradovat celý runtime ani vytvořit obecnou náhradní větu; hard gate pouze vyřadí závislý beat.

### 24.5 Chybějící prerequisity

Pro zahájení implementace jsou nutné:

- schválit canonical event/feature/fact IDs, units, clocks, `candidate_order`, `tape_channel` namespace a unknown semantics;
- schválit vlastnictví modulů a dependency direction z § 24.3;
- definovat schema versioning a migration policy pro detector/story/realization catalog a tape;
- definovat `try_start`/busy/completion kontrakt speech lane a thread-safe návrat eventu do reduceru;
- rozhodnout první gap estimator (`estimated_v1` lze převzít) a explicitní invalidation cases;
- definovat typovaný current weekend session plan a VehiclePhase projection nad již dostupnými raw vstupy;
- převést weather/SoF/flags/aftermath/HR na immutable facts bez čtení mutable RaceObserver z commentary;
- zmrazit interní vertical slice a jeho branch-only comparison hranici;
- připravit test extra prostředí a charakterizační testy masteru.

Pro první produkční aktivaci navíc:

- nasbírat testovací tape až z implementovaného recorderu a ručně označit problematické úseky;
- doložit family-specific detector a verifier report;
- změřit diskový objem a CPU overhead každého tape profilu;
- změřit Windows live latenci včetně Ollama, SuperTonic/SAPI, duckingu a souběhu s OBS/iRacing;
- otestovat restarty/rewindy, výpadek Ollama, plný disk, pomalý disk a shutdown během generování/TTS.

3D viewer, embeddings, SAT/SMT a automatická optimalizace parametrů nejsou prerequisity runtime.

### 24.6 Odhad náročnosti

Odhad je v engineer-weeks pro jednoho zkušeného vývojáře a zahrnuje implementaci, unit/replay testy a dokumentaci; kalendářní čekání na testovací sessions je zvlášť:

| Celek | Odhad |
| --- | ---: |
| Schema + NarrativeTape + config/rotation/replay základ | 2–3 týdny |
| StreamTimeline, occurrence/lineage a fact views | 2–4 týdny |
| FeatureEngine + první 2–3 temporal/composite detektory | 2–4 týdny |
| EpisodeRegistry + just-in-time director + odstranění waiteru | 3–5 týdnů |
| PromptCompiler + tight Qwen + verifier + commit gate | 3–5 týdnů |
| První obsahová vertikála a poslechová QA | 1–2 týdny |
| Windows/live hardening a rollout | 2–4 týdny |

Část prací lze překrýt, ale bez subteamu je realistický první produkční vertical slice přibližně **8–12 engineer-weeks**. Plná migrace všech relevantních rodin je přibližně **18–28 engineer-weeks** plus kalendářní čas testovacích streamů. Nejistota je zhruba ±40 %, nejvíce kvůli session reset edge cases, kvalitě gapu, semantic verifieru a live TTS/Ollama integraci.

### 24.7 Potřeba dalších textů

Není nutné předem vygenerovat tisíce nových vět ani dlouhé příběhy. Runtime generuje právě jeden beat just-in-time. Hlavní obsahová práce není počet hotových vět, ale audit významových kontraktů.

Pro první vertical slice je potřeba přibližně:

- 8–12 story families;
- 20–24 BeatDefinition kontraktů (opening/update/outcome/transition/filler) pro branch-only vertical slice;
- 80–96 enabled auditovaných EN pattern cards (minimálně čtyři na každý slice beat) plus jeho prompt instructions;
- 10–25 authored EN utterances pro předem určené critical/lifecycle beaty;
- 20–50 adversarial/minimal-pair testů na směrovou nebo číselnou family, celkem řádově 300–700 eval cases.

Většinu patternů a authored lines lze kurátorovat z dnešních 2 128 EN variant. Nové texty budou nutné pouze tam, kde dnešní věty obsahují nepodloženou příčinu/barvu, nemají self-contained outcome, nebo chybí nový session/rewind/tape stav. Odhad čistě nově napsaných vět pro vertical slice je **10–30**, nikoliv stovky. Plný v2 baseline má hard minimum **256 enabled auditovaných pattern cards** (4 × 64); další disabled kandidáti mohou zůstat v kurátorském corpus, ale nepočítají se do release coverage.

LLM eval corpus není produkční copy. Jde o testovací vstupy a očekávané claim verdicts; může být částečně syntetický a musí obsahovat prohozené aktéry, polarity, pozice, stale fakta a forbidden outcomes.

### 24.8 Doporučený první interní řez

První branch checkpoint nemá zahrnout celý graf. Není samostatně releasovatelný do `master`; doporučený rozsah:

- lifecycle: stream/session start/end/restart;
- jeden přímý event: lap/SF crossing;
- jeden temporal story pair: `CLOSING` a `UNDER_PRESSURE`;
- jeden jednoznačný outcome: position change nebo pass;
- jeden `LONG_SILENCE_ELAPSED` filler;
- pouze EN a `tight` prompt profile;
- NarrativeTape `flow + llm_eval + detector_tuning` pro vybrané detektory;
- dočasný branch-only legacy comparison pro nemigrované families.

Tento řez ověří timeline, kombinované podmínky, epizodu, no-queue chování, Qwen, verifier, TTS i tuning tape bez nutnosti migrovat všech 60 event identifiers.

### 24.9 Go/no-go brány

Implementace může začít s odhadnutými thresholds až po design-freeze gate. Finální atomický cutover je `GO` pouze když:

- event stream je deterministicky replayovatelný se stejným config/catalog hash;
- žádný single braking sample nebo target swap nevytvoří potvrzený pressure event v charakterizačních scénářích;
- no-queue test prokáže replan z current episode state a zachování významného outcome;
- tight LLM corpus nemá material false accept; false reject pouze zahodí beat;
- required tape evidence se neztrácí tiše a recorder overhead splní stanovený budget;
- live Windows event→audio latency je změřena a při timeoutu systém zůstane tichý/fail-soft;
- poslední v1 release/binary a config backup byly ověřeny jako downgrade rollback; finální v2 build neobsahuje per-family legacy přepínač.

`NO-GO` je zejména nejednoznačná lineage, neauditovatelný trigger, chybějící target correlation, loose-only verifier, blocking recorder nebo dvě komponenty vlastnící stejnou pravdu.
