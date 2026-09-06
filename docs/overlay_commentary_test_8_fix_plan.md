# Video test 8 — plán nutných oprav

Datum: 2026-09-05. Stav: návrh k implementaci; runtime ani konfigurace tímto auditem nejsou změněny. Důkazy a limity jsou v [analýze testu 8](overlay_commentary_test_8_analysis.md).

## Cíl a pořadí

Obnovit přípravu použitelných textů, stabilizovat jejich životnost a teprve nad tím rozšiřovat dlouhé navazující příběhy. Zachovat prioritu živých událostí a bezpečné odstranění overlay karet. Neobnovovat nevalidní skeleton fallback a neřešit absenci obsahu globálním snížením validace.

Závislosti: [#217](https://github.com/Buchtanen/ir-obs-switcher/issues/217) prepared graph, [#218](https://github.com/Buchtanen/ir-obs-switcher/issues/218) pořadí, [#220](https://github.com/Buchtanen/ir-obs-switcher/issues/220) budoucí příběhová kontinuita. Tento plán neoznačuje jejich otevřené požadavky za implementované. Před implementací zařadit jednotlivé opravy pod odpovídající issue s AC a dev diary; tento dokument je lokální návrh, nebyl publikován jako nový issue/PR.

## P1. Diagnostika a korektní životnost generovací úlohy

Soubory: `src/irswitch/commentary/prepared_filler.py`, `src/irswitch/overlay/tape.py`, `src/irswitch/commentary/consumer.py`, příslušné testy.

- Rozlišit HTTP status, connection error, timeout, response envelope, invalid JSON, truncated response, schema mismatch, plan mismatch, empty variants, rejected variants, duplicate-only a cancelled/stale.
- `CancelledError` nesmí započítat neúspěšný modelový pokus ani emitovat úspěch. Dokončení odložené staré úlohy nesmí aktualizovat health/error nové generace ani stejného znovuzavedeného planId.
- Úspěch měřit počtem skutečně vložených variant; validní odpověď pro už neaktuální plán je stale drop, nikoli naplnění bufferu.
- V `_schedule()` odlišit vyčerpanou kapacitu (`break`) od už spuštěného plánu (`continue`).
- Zapsat stage, generation/request identity, current/next, attempt, latency, requested/accepted/merged counts, cancel reason, health transition a fatalEpisode. HTTP metadata a bezpečné kódy do běžné diagnostiky; raw modelový obsah pouze do explicitního DEBUG evidence režimu. Nikdy auth hlavičky nebo tokeny.

AC:

- [ ] Cancel produkuje právě jednu cancel diagnostiku a žádný generated/failed attempt.
- [ ] Každý injected provider failure má odlišitelný kód; žádná JSON chyba není `transport`.
- [ ] Dva požadované plány skutečně obsadí dva dostupné sloty i při prvním už inflight.
- [ ] Recreate stejného planId během cancel nezmění novému plánu attempts/health.
- [ ] Každý generated záznam má `mergedCount>0`, jinak je označen empty/stale/duplicate.

Ověření: deterministické async unit testy a lokální HTTP fake pomocí stávajícího aiohttp; cancellation race s bariérami, žádné náhodné sleeps. Z této změny nejprve získat skutečnou příčinu prepared provider failures.

## P1. Zotavení bufferu a smlouva s generátorem

Soubory: prepared coordinator/generator, `overlay/settings.py`, config parser a testy kontraktu.

- Oddělit omezený attempt budget jednoho kola generování od časované obnovy po přechodném problému. Použít monotonic cooldown/backoff s horním limitem a vlastníkem úloh, bez busy loopu. Limity musí platit i při změnách plánů, aby churn neobcházel ochranu serveru.
- Zachovat použitelné varianty při dočasném selhání top-up; oddělit current-stage readiness od prefetch readiness.
- Pro opakované fatal hlášky sledovat skutečnou failure episode služby/scope. Změna plánů bez reálné obnovy current bufferu nesmí sama znovu oznámit stejný výpadek; nový run/session musí mít výslovně definovanou politiku.
- Výstupní rozpočet odvodit od počtu a délky variant i JSON režie. Především číst `finish_reason`; nezvyšovat naslepo všechny limity.
- Prověřit strukturovaný JSON režim na skutečném provideru. Pokud není podporován, použít otestovaný explicitní kontrakt. Kontext plánu držet na straně klienta, nepodmiňovat použitelnost textu zbytečným přesným opisem dlouhého hashe bez rozhodnutí, zda je to potřebné.
- Povolit postupné skládání batchů do stávajícího minima; neměnit default `variants_min=3` jen kvůli absenci diagnostiky. Počet vět musí odpovídat krátkým node TTS limitům.
- Vyjasnit, zda po odvysílání stačí rotace variant, nebo je žádoucí nový obsah. Současný buffer řeší rotaci; regenerace potřebuje samostatný deterministický budget a ochranu před opakováním.

AC:

- [ ] Při neměnných faktech a selhání prvních dvou pokusů se buffer po cooldownu automaticky zotaví bez restartu.
- [ ] Při trvalém selhání je počet requestů časově omezený; existující ready texty zůstanou použitelné.
- [ ] Přechod stage během výpadku nezpůsobuje opakované oznámení stejné epizody; reset policy je testovaná.
- [ ] Zkrácený/neplatný JSON je přesně diagnostikován; částečné batch doplnění nevytváří falešné ready.
- [ ] Žádné provider volání neblokuje hlavní smyčku; stop/reset zruší všechny vlastněné úlohy.

Ověření: fake clock pro cooldown, scripted provider failure→recovery, valid/empty/partial/truncated/envelope response matice, active/legacy reload a shutdown. Následně stejný scénář se skutečným modelem, zaznamenat request/response metadata a latenci. Hodnoty nových intervalů určit podle měření; přesné klíče/defaulty před implementací uzavřít v config kontraktu.

## P1. Editorial stage pro Practice/Qualifying

Soubory: `race/editorial_stage.py`, `race/runtime.py`, `tests/test_editorial_stage.py`, integrační consumer testy.

- Oddělit Racing state závodu od obecného state 4 v Practice/Qualifying. Pro P/Q vyhodnotit in-car, pit, out-lap a připravenou intro chain před přechodem do LIVE_SESSION.
- Race green zachovat jako okamžitou prioritní událost, která může přerušit dlouhý prepared text.
- Pro každou větev specifikovat current i next-stage a jasnou příčinu přeskočení, pokud fyzický vývoj intro předběhne.

AC:

- [ ] Practice připojená ve state 4 mimo auto nezruší lobby intro jen kvůli tomuto stavu.
- [ ] P/Q přechod lobby → in-car → out-lap → timed running je dosažitelný i při state 4.
- [ ] Už probíhající race po připojení nečeká na opožděné intro; green zůstává nadřazený.
- [ ] Všechny stage přechody a plány jsou diagnosticky dohledatelné.

Ověření: integrační sled vstupů odpovídající začátku obou P/Q tapes, nejen unit test přímého `build_prepared_filler_plans()` s ručně dosazenou stage.

## P1. Stabilní výsledková fakta a ochrana proti churn

Soubory: `race/context.py`, `race/runtime.py`, výsledková paměť/session end, `commentary/prepared_filler.py`; napojit na práci #218.

- Zavést oddělený výsledkový snapshot se zdrojem, session/run/class scope, confirmation a revizí. `player_finished` znamená dojezd, nikoli potvrzení pořadí.
- Výsledkový uzel nesmí dostávat průběžné live class_position. Po potvrzení číst scoped snapshot; při chybějícím důkazu vybrat `result_unconfirmed`. Skutečnou opravu publikovaného výsledku řešit novou result revision.
- Zmrazit ostatní required výsledková fakta. U optional live údajů určit material threshold a stabilizační okno; nevkládat rychle kolísající data do výsledkového identity hashe.
- Rozlišit změnu relevantního faktu od kosmetické/vedlejší změny. Nepřehrávat starý text se zastaralým required faktem pod záminkou stabilizace bufferu.

AC:

- [ ] Replay konce testu 8 s live P30→P16→P25 nemění potvrzený výsledkový plán.
- [ ] Samotný checkered/finish bez výsledkového důkazu nevytvoří „confirmed result“.
- [ ] Nová skutečně potvrzená klasifikace vytvoří přesně jednu revizi a invaliduje starou řeč.
- [ ] Session/run reset nepřenese výsledek do jiné session; next-stage prefetch zůstává omezený.

Ověření: field sekvence 35:57–38:05, delayed result confirmation, missing official result, multiclass, result correction, reset. Ke zjištění skutečného finálního pořadí doplnit výsledkový zdroj; P30 z aktuální tape samo nestačí.

## P1. Faktický kontrakt živého komentáře

Soubory: `commentary/composer.py`, `microplan.py`, `polish.py`, `speech_hero.py` a jejich testy.

- Vždy předat jednoznačného aktéra a protistranu jako role. Chybějící hero binding nesmí nechat soupeře jedinou pojmenovanou postavou věty; použít explicitní referenci na sledovaného jezdce bez vymyšleného jména.
- Session name, trať, tým a driver mají typované sloty. `Qualifying` nesmí vzniknout v `other_drivers`.
- Validovat vztah subjekt→děj→objekt, nikoli jen přítomnost jména/slovesa. Přidat přesné negativní případy z tapes včetně přivlastňovacího „Name’s on the move…“.
- Změna pozice bez gap trendu nesmí vyvolat closing/widening tvrzení. Styl nesmí přidávat smyk, wheelspin ani další nepozorované jevy.
- Rozpočty a znovupokusy omezit podle relevance události; neúspěšný kandidát musí uvolnit TTS a overlay lifecycle tak jako po opravě testu 7.

AC:

- [ ] Všechny doložené záměny HUNTING rolí, session-as-driver a nepodložené gap směry jsou odmítnuté nebo správně vyjádřené.
- [ ] Správné věty stejného významu zůstávají přijímané v EN i CS; nesnižuje se globálně validator threshold.
- [ ] `retry_exhausted`/timeout nejsou přečteny jako skeleton; nejvyšší platný čekající kandidát pokračuje.
- [ ] Replay 80 zachycených polish operací vytvoří report false accepts/false rejects; `ok` se neprezentuje jako skóre faktické správnosti.

Ověření: paired positive/negative testy actor roles, typed facts, endpoint fixture s pořadím událostí, skutečný model nad reprezentativními anonymními i jmennými daty. Ruční věcný audit přijatých vět a poslech zůstávají výstupním gate.

## P2. Overlay a připravenost dalšího video testu

Soubory: `overlay/consumer.py`, `overlay/tape.py`, `race/runtime.py`; renderer měnit pouze při konkrétním reprodukovaném problému.

- Doplnit DEBUG záznam finálního snapshotu po sloučení source stories a speech leases. Rozlišit producer source snapshot a skutečně odeslaný WS snapshot.
- Propojit selected → building → accepted → committed → speaking → completed/interrupted/rejected se storyId a eventId; `tts_final` nyní nemá tyto identity.
- Zachovat equal-sequence adoption, terminal removal, fresh EXIT metadata a cache version invariants opravené v testu 7.
- Přímým VOD poslechem ověřit fatal časy, delší tiché úseky, přerušené věty a výsledný OBS mix. Ověřit overlay i při selhání LLM a po restartu závodu.

AC:

- [ ] Každý terminal/rejected/reset lifecycle odstraní související lease ve finálním WS snapshotu i v rendereru.
- [ ] Záznam určí, který text byl jen vybrán a který backend skutečně přehrál.
- [ ] VOD potvrzuje odchod karet; při nezměněném výsledku nevznikají falešné změny result karty.

## P2. Navazující minipříběhy během živé session

Implementovat podle již otevřeného #220 a dokumentů `race_story_continuity_spec.md`, `race_story_continuity_implementation_plan.md`, `race_story_sequence_graph_plan.md`. Nespojovat absenci této funkcionality s nefunkčním již existujícím pre-race/result bufferem.

Předpoklady: opravena identita pořadí a aktérů, bounded generátor, výsledková paměť a měřitelné lifecycle. Potom přidat časově souvislé battle příběhy a historii session; nepřidávat prázdný univerzální LIVE_SESSION filler jako náhradu skutečných faktů.

## Dokumentace, konfigurace a dokončení

V tomto auditu vznikají pouze analýza a plán. TDD výjimka: dokumentační návrh bez změny chování, ověřený čtením tapes, pěti reprodukcemi a 128 existujícími testy.

Při implementaci:

- `COMMENTARY_ENGINE.md`: recovery, fatal episode, actor roles, připravený vs live obsah a skutečný playback lifecycle.
- `API.md`: diagnostické kódy, health, stage, counts, result source a nové snapshot identity; additive tape kompatibilita a verze dle rozsahu.
- `CONFIG.md` + `config/config.example.ini`: pokud se přidají recovery intervaly nebo změní generační rozpočet/defaulty, uvést přesné klíče, rozsahy a migraci. Nesmí vzniknout skrytá změna významu stávajícího attempt budgetu.
- `docs/commentary_prepared_active_test.md`: provider failure/recovery, P/Q state4, immutable finish a playback evidence.
- `docs/prepared_graph_completion_plan.md`: rozlišit strukturálně dokončený manifest od dosud neověřené runtime kvality.

Výstupní gate: regresní testy jednotlivých oprav; integrační session sled; controlled provider failure/recovery; lokální replay; nový celý Practice→Qualifying→Race video test se zachovanými tapes, efektivním configem, runtime commit identitou, DEBUG health/snapshot evidence a poslechem. Teprve tento balík může uzavřít audiovizuální AC. Bez nových závislostí.
