# Track Excursion — aktivní vývojový test (#216)

Základ: `master` (current-signal subset). Nová cesta je napojená v kódu;
samotná úprava pracovního stromu nerestartuje ani neaktualizuje běžící Windows službu.

## Co skutečně běží

`RaceState → TrackExcursionDetector → RaceObserver → RacePipeline → CommentaryConsumer
→ graph v3 / Director → MiniStory commit → TTS`.

Detektor je nativní časový reducer v `events/scenarios/track_excursion.py`. Používá společný
kontrakt `EpisodeScope` / `ScenarioBeat`, ale **nespouští návrhové JSON scénáře ani obecný
`ScenarioEngine`**. Převod kompletního složeného scénáře do datové definice zůstává další práce.
Změna JSON v `docs/scenarios/` tedy zatím nemění detekci. Naproti tomu texty, selektory a hrany
se načítají ze skutečného `commentary/data/sequence_graph.json` (verze 3).

Jeden příběh má stabilní `parentStoryId` a `episodeId`; každá fáze má vlastní `correlationId`.
Rozsah identity obsahuje session, run epoch a jezdce. Přijatá událost `TRACK_EXCURSION` je pouze
pro komentář, nepřidává HUD kartu. Stávající HUD wire payload zůstává zachovaný.

| Fakt / beatId | Nutný důkaz | Co lze říci |
| --- | --- | --- |
| `offtrack` | předtím platný vzorek na trati; OffTrack souvisle 0,2 s; mimo boxy; tow = 0 | „Vyjel mimo trať.“ |
| `stopped` | během epizody rychlost ≤ 1 m/s po 0,35 s, povrch na/mimo trati, tow = 0 | „Po vyjetí mimo trať auto zastavilo.“ |
| `track_rejoined` | OnTrack souvisle 0,2 s, mimo boxy, tow = 0 | „Vrátil se na trať.“ |
| `motion_restored` | OnTrack a rychlost ≥ 2,5 m/s souvisle 0,6 s | „Po vyjetí mimo trať už znovu jede po trati.“ Epizoda zůstává otevřená pro S7a pace. |
| `tow_started_race` | kladný tow timer v režimu RACE | „Po vyjetí mimo trať začal odtah.“ |
| `pit_return_observed` | OnPitRoad a pit surface souvisle 0,2 s | „Po vyjetí mimo trať se vrátil do boxů.“ |
| `pace_loss_sustained` | po `motion_restored`; rychlost / frozen dist-bin < 0,55 po 4 s a ≥ 8 % kola | „Pokračuje výrazně pomaleji.“ Bez poškození. |
| `normal_running_resumed` | po `motion_restored`; poměr ≥ 0,85 po 4 s a ≥ 8 % kola | „Tempo je zase zpátky.“ Uzavírá epizodu. |

Chybějící rychlost není nula. Chybějící tow timer nepotvrzuje „netáhne se“. Body incidentů
nejsou potřeba pro začátek vyjetí. U rychlostních hran jsou úmyslně různé prahy a časové výdrže;
nevyhodnocuje se počet snímků. Duplicitní/starší čas se ignoruje, mezera vzorků > 1 s,
neplatná identita, nevyhovující kvalita či stáří > 500 ms ruší kontinuitu.
Neznámý povrch trvající 1 s epizodu také ruší; nové potvrzené
vyjetí po již potvrzeném návratu dostává nové ID epizody. Epizoda po 90 s
bez podporovaného konce tiše expiruje. Timeout není potvrzený návrat ani ukončení závodu.
Hodnota confidence 1,0 znamená splnění tohoto pravidla, **ne empiricky kalibrovanou přesnost**.

Obnovení pohybu epizodu **neuzavírá**. Odtah, návrat do boxů, obnovené lokální tempo
(`normal_running_resumed`) nebo timeout 90 s ji uzavřou. `track_rejoined` sám ještě ne.
Chybějící dist-bin, start/cíl pás (prvních/posledních 5 % kola) nebo poměr mezi 0,55 a 0,85
znamená abstain, ne vymyšlený závěr. `pace_loss_sustained` není poškození, limp ani oprava.

## Režimy a kompatibilita

```ini
[race_scenarios]
mode = active

[overlay]
session_tape = true
```

`active` je nový **vývojový default**, schválený uživatelem pro zapojení a následné vyhodnocení.
Na rozdíl od původního plánu se nečeká na dokončení historického replay korpusu. Režim lze
přenačíst konfigurací; přepnutí ruší lokální stav detektoru.

- `active`: nový detektor publikuje, starý `IncidentAftermathFsm` netiká. Starý `INCIDENT`
  zůstává v transportu, ale jeho řečová větev `points` hlásí pouze **přírůstek bodů**, ne kontakt.
- `shadow`: nový detektor pouze zapisuje diagnostiku; publikuje starý aftermath.
- `legacy`: nový detektor neběží. Obnoví se původní detekce, ne odstraněné zavádějící texty.
- Neplatná hodnota konfigurace: warning a `legacy`.

Master přepínač `[commentary] enabled` se nemění a bez něj není řeč. Nastavení
`[commentary.graph_runtime] mode` je nezávislé; nová fakta se vybírají i při jeho `legacy`.
V `active` graph režimu navíc funguje skórování návaznosti podle společného rodiče.

Při obsazeném TTS smí nový scénář podržet jednu aktuální hlášku i bez globálního
`scheduler.defer_enabled`. Novější fáze nahrazuje starší nevyřčenou fázi; nebuduje se fronta
všech kroků. Hrany dovolují také přímé root → closure/terminal. Již mluvená fáze se kvůli
novému vývoji nepřerušuje. FINISH má stále vyšší redakční prioritu. Selhání detektoru je
lokálně zachyceno a zaznamenáno; v active se nezapíná zároveň druhý publisher.

## Co zatím tvrdit neumíme

Smyk, hodiny, kontakt s konkrétním autem/bariérou, minutí brzdného bodu, vyhýbací manévr,
poškození, zázračné zachycení, dojíždění na opravu ani ESC/reset do
boxů v Practice/Qualify. Z návratu do boxů **nevyplývá oprava ani stisk ESC**.
Lokální pace-loss/resume (S7a) mluví jen o tempu vůči frozen dist-bin mapě, ne o poškození.
Všechny tyto příčiny/následky zůstávají neznámé; nejsou vydávány za hotové klasifikátory.

„Incident“ a české tvary jsou zakázané mimo dva výslovně číselné legacy uzly. Root vyžaduje
slovník off-track / track limits / mimo trať. Pravidlo platí pro autorské texty, skladbu,
kontrolu LLM výstupu i finální TTS text. LLM chyba může způsobit ticho; sama o sobě nemění fakt.

## Co je v logu

Při zapnuté session tape se i na INFO zapisují, **jen když je tape soubor otevřený**
(iRacing connected v Practice/Qualify/Race). Bez hry se nezapisuje nic.

- `type=race_scenario`: změny kategorií vstupního důkazu, detekované fáze a invalidace;
  `scenarioMode`, `parentStoryId`, `beatId`, důvod, povrch, rychlost, tow, časy.
  Nezapisuje se každá změna rychlosti ani každý telemetry tick. Idle disconnect bez
  otevřené epizody negeneruje ani `observation_changed`.
- `type=commentary`, `eventType=TRACK_EXCURSION`: rozhodnutí, dostupné graph skóre a TTS
  lifecycle s ID. Process TTS navíc zapisuje `tts_requested`, `tts_result` včetně finálního
  textu a výsledku; SuperTonic přidá `playback_requested` po syntéze a čekání na duck fade.

`speaking` / `tts_requested` není přesný akustický začátek. `playback_requested` označuje
požadavek na přehrání, ne potvrzení z OBS. Přesný soulad se zvukem ověří video. Další
komentáře a LLM request/response zůstávají DEBUG-only. Pro kompletní triáž použij DEBUG;
pro základní detekce a nové TTS fáze stačí INFO.

Session soubor je `recordings/overlay-<utc>-<subsession>-<session>.jsonl`. Řádky mají společné
`t_stream`, `t_session` a monotónní časy. Při porovnávání neplést video/stream clock se session time.

## Evidence pack (živý poslech)

TDD-exception: tento checkout nemůže řídit iRacing ani poslouchat v OBS CEF.
Náhrada: video + session tape + identita níž. Syntetické pytesty nedávají precision/recall.

Zaznamenat **spolu** (jeden poslech = jeden balík):

1. `git rev-parse HEAD` a `git status -sb` (dirty tree ano/ne).
2. `GET http://127.0.0.1:17321/health` → `version`, `status`, `checks.iracing`, `checks.obs`.
3. Overlay cache z `/overlay/` HTML (`?v=` musí sedět s `OVERLAY_ASSET_VER`).
4. Konfigurace: `[race_scenarios] mode` (chybějící sekce = default `active`),
   `[commentary] enabled=true`, `[overlay] session_tape=true`.
5. Session tape `recordings/overlay-<utc>-<subsession>-<session>.jsonl` — soubor se otevře
   jen při connected Practice/Qualify/Race. Idle disconnect bez otevřené pásky
   nezapisuje `race_scenario` ani INFO.
6. Video stejné relace (OBS VOD / local capture).

## Průběh ručního testu

1. Nasadit pracovní strom (editable `irswitchd.exe` nebo rebuild) a **restartovat** službu.
   Ověřit health + overlay `?v=` + config výše. OBS Browser Source → Refresh cache.
2. Na bezpečném testovacím kole: krátký off-track bez bodů → návrat v pohybu.
3. Další pokus: off-track → zastavení → návrat; zopakovat s komentátorem zrovna uprostřed věty.
4. Po obnovení pohybu: jet dál výrazně pomalu přes několik úseků vs vrátit tempo. Má zaznít
   pace-loss nebo recovered pace, ne poškození.
5. V odpovídajícím testu ověřit Race odtah a Practice/Qualify návrat do boxů. Nemá zaznít
   neprokázaná oprava, kontakt nebo ESC.
6. Vyzkoušet výpadek, změnu run/jezdce a normální nájezd do boxů bez předchozího off-tracku.
   Bez starého příběhu se nesmí objevit jeho závěr.
7. Uchovat evidence pack z oddílu výše.
8. Pro každý `parentStoryId` porovnat: vizuální hranice děje → detekce → výběr → finální řeč.
   Zapsat správné/chybné/chybějící fáze, zpoždění, potlačení a konkrétní důvod. Teprve z těchto
   označení vyhodnotit precision/recall a latence; samotné syntetické testy tyto metriky nedávají.

Lokálně: `.venv/bin/python -m pytest tests/test_track_excursion_live.py tests/test_overlay_tape.py -q`.
Testovací TTS nevytváří skutečný zvuk. Původní tape k videu Test 7 13:44 zde není; jeho přesnost
a časování nejsou tímto testem ověřeny.
