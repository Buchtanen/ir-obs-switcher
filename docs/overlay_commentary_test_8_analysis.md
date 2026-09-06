# Video test 8 — analýza recordings, komentáře a overlaye

Datum: 2026-09-05. Stav: technická analýza dokončena, přímá kontrola VOD obrazu a zvuku blokována oprávněním prohlížeče. Opravy zatím nejsou implementované.

VOD: [oSGIMZ7lV5A](https://www.youtube.com/live/oSGIMZ7lV5A).
Navazuje [plán oprav](overlay_commentary_test_8_fix_plan.md).

## Zdroje a meze důkazů

Recordings jsou na originu ve větvi `codex/fix-overlay-commentary-test-7`, commit `1bf783e67c935c40235df687dfe991ea5f8953b9`. Proti místnímu HEAD `005bbb6c4fb630475a09bf775b878fc5803d80fc` obsahuje tento commit pouze tři nové tapes; zdrojový kód je shodný. Header uvádí verzi `1.3.0`, nikoli runtime commit, takže identita skutečně spuštěného binárního sestavení není samotným headerem prokázána.

| Tape v `recordings/` | Mode / sessionId | Řádků | Rozsah `t_stream` |
| --- | --- | ---: | --- |
| `overlay-20260905T174747Z-0-0.jsonl` | PRACTICE / `0:0` | 2 287 | 00:27.008–12:44.600 |
| `overlay-20260905T180005Z-0-1.jsonl` | QUALIFYING / `0:1` | 1 234 | 12:45.088–18:18.102 |
| `overlay-20260905T180539Z-0-2.jsonl` | RACE / `0:2` | 3 520 | 18:18.519–38:04.829 |

Celkem analyzováno všech 7 041 JSONL řádků. Jazyk EN, `pit_wall_dark`, V4 renderer zapnut. Pro orientaci ve VOD používat `t_stream`, nikoli `t_session`. Stream origin v těchto třech souborech se liší přibližně o 55 ms; nenacházím zde reset streamových hodin mezi sessions. Závod obsahuje skutečný `run_reset` v 20:35.657 kvůli přetočení session času a dvě zelené: 20:06.278 a 22:22.575. Druhá formace tedy není automaticky duplicitní chyba.

Video nebylo přímo zhlédnuto ani přepsáno. První web fetch selhal; browser následně dvakrát odmítl přístup z důvodu oprávnění, podruhé po novém uživatelském pokynu. Níže uvedené časy jsou odkazy podle tape hodin, bez vizuálně potvrzeného offsetu YouTube. Logy aplikace, efektivní konfigurace a status snapshoty nebyly součástí těchto tří souborů.

`commentary.action=spoken` s důvodem `spoken` nebo `spoken_deferred` zaznamenává kandidáta před dokončením LLM/TTS. **Není to důkaz, že daná věta zazněla.** `reason=tts_final` vzniká po návratu backendu s `result.spoken` bez chyby. Je to silnější důkaz přehrání, ale stále nejde o poslech finálního OBS mixu; přerušené/částečné řeči nelze prostým počítáním těchto řádků úplně rekonstruovat.

## Výsledek

Uživatelský feedback o nefunkčních připravených příbězích a opakované fatal hlášce je podložený. Problém není jediný zastavený timer: současně selhává diagnostika generátoru, obnova po vyčerpání pokusů, stabilita vstupních faktů a některé přechody editorial stage. Živý komentář má samostatné problémy s faktickým zadáním a validací.

| Metrika | Practice | Qualifying | Race | Celkem |
| --- | ---: | ---: | ---: | ---: |
| Prepared diagnostické řádky | 12 | 4 | 46 | 62 |
| Prepared `transport` | 11 | 0 | 12 | 23 |
| Prepared `generated`, ale `acceptedTexts=[]` | 1 | 4 | 34 | 39 |
| Přijaté prepared texty v tapes | 0 | 0 | 0 | 0 |
| LLM polish operace | 28 | 5 | 47 | 80 |
| `ok` | 11 | 1 | 21 | 33 |
| `retry_exhausted` | 16 | 4 | 25 | 45 |
| `fallback_timeout` | 1 | 0 | 1 | 2 |
| `tts_final` | 8 | 1 | 13 | 22 |
| Z toho fatal hlášky | 2 | 0 | 2 | 4 |

Prepared má 37 různých planId a 21 situationId. Všech 62 řádků postrádá stage (`null`). Žádný prepared text není doložen jako přijatý ani přehrávaný; `generated` nelze považovat za počet úspěšných odpovědí modelu. Obsah pole `acceptedTexts` je přítomen, nikoli vynechán kvůli INFO úrovni.

U živého polisheru je úspěšnost technické validace 41,25 %. Celkem 47/80 operací skončilo odmítnutím/timeoutem, při 132 pokusech podle attempt counterů. Není zde `fallback_error`. Souběžné použití stejného modelu pro live i prepared může přispívat k latenci, ale tapes neprokazují konkrétní vytížení serveru. Medián latence operace je 1,46 / 1,87 / 1,66 s; maxima 13,16 / 2,36 / 12,02 s.

## 1. Prepared buffer a opakované LLM failure

### A. `transport` neznamená prokázaný výpadek spojení — potvrzená chyba diagnostiky

`src/irswitch/commentary/prepared_filler.py:784` dekóduje `choices[0].message.content` jako JSON, očekává přesné schema i dlouhé planId. JSON parse, chybějící pole, `plan_mismatch`, HTTP chyby a ostatní výjimky skončí ve stejném `except Exception` v koordinátoru (`:682`) jako `transport`.

Reprodukce s generátorem vyhazujícím `ValueError('plan_mismatch')` vyprodukovala dva řádky `transport`. **Nelze doložit, zda 23 produkčních chyb způsobilo HTTP, neplatné JSON, zkrácení odpovědi nebo neshodné planId.** Live polisher od modelu odpovědi dostával; globálně nedostupný LLM proto není dostatečné vysvětlení.

Generovací request (`:1505`) chce standardně pět variant po 2–5 větách plus JSON obálku a echo planId, přičemž minimum výstupního rozpočtu je 360 tokenů. Nevyžaduje strukturovaný výstup přes provider kontrakt a nezaznamenává `finish_reason` ani odmítnutou prepared odpověď. Riziko příliš malého rozpočtu/JSON formátu je významná hypotéza, nikoli prokázaná příčina všech 23 chyb. Některé uzly mají navíc jen čtyřsekundový limit na variantu; to musí být sladěno s počtem vět.

### B. Zrušení se vydává za generování — reprodukováno

V `_generate()` (`:661`) po `CancelledError` stále běží `finally`. `error` zůstane `None`, `valid=[]`, a při nezměněném coordinator epoch se započítá attempt a emituje `generated`. Běžné odstranění plánu při `reconcile()` coordinator epoch nezvyšuje.

Reprodukce: spustit čekající generátor, počkat na začátek, odebrat plán a vyčkat na jeho cancel → přesně `action=generated, reason=null, acceptedTexts=[]`. Stejný záznam může vzniknout při úspěšně dekódovaném prázdném seznamu. Tapes obě příčiny nerozliší. U přechodů session a rychlých změn pořadí je rušení velmi pravděpodobné.

### C. Po vyčerpání rozpočtu není časovaná obnova — reprodukováno

`note_attempt()` (`:376`) nastaví `generation_complete` po dvou pokusech. `need_generation()` (`:333`) pak plán trvale přeskočí. Sto dalších `reconcile()` se stejným plánem v reprodukci nespustilo další pokus; stav zůstal `fatal`. Nový pokus vyžaduje odstranění/změnu plánu nebo reset, nikoli návrat zdravého LLM.

Je to také vědomě testované původní chování: `test_coordinator_stops_top_up_after_attempt_budget`. Chybí však oddělení konečného rozpočtu jednoho pokusu o naplnění od pozdějšího zotavení služby. Zvýšení počtu rychlých retry tuto mezeru neřeší. Plný buffer navíc rotuje existující varianty přes exposure countery; nemá samostatný cyklus nahrazování odvysílaných textů. V tomto testu se k rotaci ani nedostal.

### D. Scheduler nevyužije volný slot — reprodukováno, dopad na tuto jízdu nezměřen

`_schedule()` (`:649`) používá `break` pro `slots<=0` **i** pro už běžící planId. Je-li první seřazený plán právě rozpracovaný, neprojde k dalšímu plánu, i když je volná kapacita. Reprodukce s limitem 2 a dvěma požadovanými plány ukázala jen 1 inflight úlohu. Tapes neobsahují slot occupancy, takže rozsah dopadu na test 8 nelze spočítat.

### E. Practice/Qualifying přeskočí příběhové fáze — reprodukováno

`src/irswitch/race/editorial_stage.py:172` vyhodnotí `item.green or item.session_state == 4` dříve než obsluhu P/Q lobby, přípravy a výjezdového kola. Reprodukce s připojenou Practice, `session_state=4`, jezdcem mimo auto a na pit road ihned skončí v `LIVE_SESSION`, `next_stage=SESSION_CONCLUSION`.

To odpovídá začátku obou P/Q tapes: stav 4 je už v header/field datech, ale místo úvodů se připravuje budoucí závěr Practice. V `add_stage()` není prepared větev pro `LIVE_SESSION`; to je záměr současného graph plánu, nikoli zapomenutý univerzální filler. Souvislé příběhy během jízdy patří do dosud neimplementovaného [#220](https://github.com/Buchtanen/ir-obs-switcher/issues/220). Oprava bufferu sama nenahradí tento chybějící rozsah.

### F. Výsledek po dojezdu používá měnící se live position — silně doloženo

`build_prepared_filler_plans()` přebírá `race.class_position`; tato hodnota přes `race/context.py` pochází ze snapshotu živého pořadí. `confirmed` se odvozuje od `player_finished or session_finished`, tedy od stavu dojezdu, nikoli od samostatného důkazu stabilní výsledkové klasifikace. `add_conclusion()` pak tuto pozici váže do required factů a mění result band.

Po FINISH kandidátovi v 35:57.320 drží field `officialClassPosition=30`, zatímco `classPosition/liveClassPosition` postupně kolísají P30 → P29 → … → P16 → … → P25. Například 36:54.61 P24, 36:56.33 P23, 36:58.51 P22. Krátce po těchto změnách přicházejí prázdné `generated` pro odcházející plán. Od dojezdu je 28 výsledkových prepared záznamů (18 rear-third, 10 middle-third) a dva bridge záznamy, bez přijatého textu.

Reprodukce se stejným session/run a `player_finished=True` mění při P25 → P20 nejen planId, ale i uzel rear-third → middle-third. Komentář v kódu, že výsledek nevzniká z měnící se live position, tedy neodpovídá chování. Samotné oficiální P30 v tape neprokazuje definitivní publikovaný výsledek: oprava musí určit zdroj a potvrzení, nikoli pouze slepě přepnout na jiné pole.

### Čtyři fatal hlášky

Backend reportuje přehrání v `t_stream` 630,693; 679,101; 1140,999; 1286,778 s — přibližně 10:31, 11:19, 19:01 a 21:27. První a druhá patří do Practice, třetí do první formace, čtvrtá po run resetu.

Fatal counter se zvětšuje při každém přechodu do `FATAL`; příznak oznámení se resetuje i při návratu READY/DEGRADED. Změna plánů/stage může způsobit novou epizodu bez skutečného zotavení modelu. Současný kontrakt „jednou za epizodu“ tedy může dávat opakované hlášky v jednom streamu. Tapes nezapisují health transitions ani fatalEpisode, proto nelze zpětně spolehlivě přiřadit všechny přechody. Čtvrtá hláška po novém běhu není sama o sobě porušením dedupe stejného běhu.

## 2. Živý komentář: data, pravdivost a kadence

Oprava testu 7 funguje v důležitém bodě: nevalidní polish v `tts.py:436` ukončí kandidáta a nečte authored skeleton. Důsledkem 58,75% neúspěšnosti LLM operací je málo skutečně doložené řeči. Nevydávat text z optimistického `spoken` řádku za slyšený fallback a nevracet automatické čtení skeletonu jako opravu.

Sémantická kvalita zůstává problém i u `ok`:

- HUNTING request opakovaně obsahuje jen `closing_on: Gosselin` a obecnou action. `microplan.actor_roles` má target, ale chybí hero. Výstup pak udělá z Gosselina aktivního pronásledovatele. Podobně Wright v backendovém finálním textu kolem 28:14. `_microplan_data()` (`polish.py:811`) přidá driver jen tehdy, pokud je v actor_roles; composer hero roli odvozuje pouze z dostupného `hero_name` bindingu.
- `_role_violations()` (`polish.py:560`) chytá úzký vzor „Name is closing…“, ale výstup s „Name’s on the move… closing…“ projde. Přítomnost jména a slova closing není důkaz správného směru vztahu.
- `SESSION_PREVIEW` přidává `Qualifying` do `other_drivers`, protože tento seznam vzniká ze všech `allowed_names` bez typovaného rozlišení. Přesný request je v quali tape u 12:47.49. Vyžadovaná session informace se tím mění v matoucí osobní jméno.
- Přijaté position-loss texty přidávají rozporné směry gapu bez zdrojového důkazu: při P26 jednou „gap widens“ (23:43), jindy „gap is closing fast“ (27:03). Samotná ztráta pozice neurčuje trend mezery.
- Finální text o leader change kolem 05:52/06:09 obsahuje wheels spinning / tail sliding; incident +2 kolem 16:17 opakuje „two“ a nenese srozumitelné vysvětlení incidentových bodů. Atmosféra přebíjí fakta. Toto je audit zaznamenaného textu, nikoli prozodie.

Finálního přehrání je doloženo 22, z toho čtyři technická oznámení. To neznamená 22 kompletních zvukových segmentů VOD: existují také interrupted lifecycle řádky. Přijaté `ok` rovněž není rovno odvysílané větě; kandidáta může mezitím zneplatnit nová událost.

## 3. Overlay: zlepšení lifecycle, ale omezená viditelnost do rendereru

V Practice vznikne TARGET_LOCKED v 08:52.884 a seznam je prázdný v 09:14.31. V Race je 37 snapshotů pro 14 nepřekrývajících se battle correlationIds; všechny mají následné vyprázdnění. První Cross 23:19.779 → 23:21.56; poslední Gosselin 35:27.16 → 35:30.20. Zdrojové battle příběhy tedy nezůstávají viset až do konce záznamu. Časté nové Gosselin epizody s krátkým trváním vysvětlují fragmentaci; dlouhodobá kontinuita je backlog #220.

**Důležitá mez:** `race/runtime.py:1131` nahrává `manager_v2.active_stories_v4()`, nikoli finální kombinaci source stories + TTS leases z `overlay/consumer.py:280`. Tape snapshot tedy není úplný autoritativní důkaz výsledné obrazovky OBS. Z dřívějšího stručného průběžného sdělení „snapshoty odstraňují karty“ se nesmí odvodit úplný vizuální PASS. Uživatelský feedback o nezůstávajících kartách je s daty konzistentní; zhlédnutí a finální WS snapshot jsou stále potřebné pro celkové potvrzení.

Taktéž `miniStory` v event envelope není totéž co připravený několikavětý příběh: označuje lifecycle živého eventu. Jeho přítomnost v tape nevyvrací selhání prepared bufferu.

## 4. Ověření kódu

Na místním kódu shodném s auditovanou origin větví prošlo 128 existujících testů:

```sh
.venv/bin/python -m pytest -q tests/test_prepared_filler.py tests/test_prepared_graph_contract.py tests/test_commentary_microplan.py tests/test_commentary_polish.py
# 83 passed
.venv/bin/python -m pytest -q tests/test_editorial_stage.py tests/test_overlay_tape.py
# 23 passed
.venv/bin/python -m pytest -q tests/test_n12_consumers.py
# 22 passed
```

Dále provedeno pět cílených reprodukcí proti nezměněnému runtime: cancelled→generated, plan_mismatch→transport + neobnovení po 100 reconciliacích, nevyužitý druhý slot, P/Q state 4 přeskočí intro, změna výsledkového plánu po dojezdu. Reprodukční skript a výstup jsou při tomto auditu v `/tmp/video-test-8/reproduce.py` a `reproductions.txt`; vstupní origin tapes ve stejné složce. Tyto dočasné soubory nejsou trvalou součástí repozitáře.

Zelené existující testy neznamenají vyřešené nalezené chyby: některé výslovně kodifikují jednorázové vyčerpání a jiné kontrolují jen syntetické validní generátory. Nutné nové regresní scénáře stanoví navazující plán.

## Otevřená ověření

1. Přímé zhlédnutí VOD, poslech OBS mixu a ověření přesného offsetu vůči `t_stream`.
2. Raw prepared response / HTTP status / finish reason pro rozlišení 23 chyb.
3. Runtime commit, efektivní modelové limity a health/occupancy během generování.
4. Finální WS snapshot po TTS lease redukci a stav rendereru při completed/interrupted/rejected/reset.
5. Zdroj skutečně potvrzeného výsledku a jeho scope po dojezdu.

Do jejich doplnění nelze tvrdit, že bylo provedeno úplné audiovizuální přezkoumání nebo že konkrétní provider chyba je definitivní root cause.
