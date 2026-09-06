# Dokumentace irswitch — mapa pro lidi i modely

**Čti tohle dřív, než začneš grepovat `src/`.** Po změně kódu **stejnou složku zase aktualizuj** (skill `dokumentace`, `/docs-keeper`). Tichý skip není OK — buď page, nebo `Docs: no change (reason …)`.

Tato složka je **architektonický index**: co který modul dělá, kde končí jeho pravomoc, kam tečou data, a co je teprve v otevřených PR (není na `master`).

Není to náhrada kontraktů. Klíče INI, HTTP payloady a release proces zůstanou v existujících souborech — odkazy jsou dole.

## Pořadí čtení

1. [Jak číst](jak-cist.md) — pravidla pravdy, co sem nepatří
2. [Architektura](architektura.md) — vrstvy, runtime smyčky, datové toky
3. [Stav dokumentace vs kód](stav.md) — `master` vs otevřené PR
4. Doména, na které pracuješ (tabulka níže)
5. Až potom kód; grep až když index nestačí

In-flight změny **nejsou** v kódu na `master`. Než něco navrhneš v `race/`, `events/` nebo `commentary/`, otevři [inflight/README.md](inflight/README.md).

## Rychlý lookup (příznak → dokument)

| Chci změnit / pochopit | Čti | Nesahaj sem napřed |
| --- | --- | --- |
| Přepínání OBS scén, debounce, cooldown, override, GARAGE vs LOBBY | [domeny/logic.md](domeny/logic.md), [domeny/iracing.md](domeny/iracing.md) | `overlay/`, `events/` |
| `DrivingMode`, `SwitchState` | [domeny/runtime.md](domeny/runtime.md), [domeny/logic.md](domeny/logic.md) | Event Engine |
| iRSDK telemetrie, sentinely, extractory | [domeny/iracing.md](domeny/iracing.md) | `logic/` (žádné SDK volání) |
| OBS WebSocket, scény, stream start/stop | [domeny/obs.md](domeny/obs.md) | `logic/` (žádná policy v clientovi) |
| HTTP/WS API, dashboardy, `/health` | [domeny/server.md](domeny/server.md), [API.md](../../API.md) | `logic/` přímo z handleru |
| Overlay HUD, V3/V4, tape, WS `/ws/overlay` | [domeny/overlay.md](domeny/overlay.md) | Scene switcher |
| Battle / lap / pit eventy, arbitration | [domeny/events.md](domeny/events.md) | `iracing/` (žádná interpretace) |
| TTS, sequence graph, director | [domeny/commentary.md](domeny/commentary.md) | HUD render |
| RaceState, gapy, sektory | [domeny/race.md](domeny/race.md) | Scene switcher |
| BLE tep, sysinfo, LHM | [domeny/bio.md](domeny/bio.md), [domeny/system.md](domeny/system.md) | `iracing/` |
| INI klíče, hot-reload | [domeny/config.md](domeny/config.md), [CONFIG.md](../../CONFIG.md) | — |
| YouTube title / OAuth | [domeny/oauth-youtube.md](domeny/oauth-youtube.md) | Scene switch |
| Overlay copy / i18n HUD | [domeny/i18n.md](domeny/i18n.md) | `i18n.py` dashboard stringy |
| Testy, CI, release | [domeny/testy-ci.md](domeny/testy-ci.md) | — |
| Otevřené PR (observers, narrative) | [inflight/README.md](inflight/README.md) | Implementace na `master` |

## Domény (`src/irswitch/`)

| Doména | Balík | Dokument |
| --- | --- | --- |
| Runtime / entry | `main.py` | [domeny/runtime.md](domeny/runtime.md) |
| iRacing extraction | `iracing/` | [domeny/iracing.md](domeny/iracing.md) |
| OBS client | `obs/` | [domeny/obs.md](domeny/obs.md) |
| Scene switcher | `logic/` | [domeny/logic.md](domeny/logic.md) |
| HTTP glue | `server/` | [domeny/server.md](domeny/server.md) |
| Overlay runtime | `overlay/` | [domeny/overlay.md](domeny/overlay.md) |
| Event Engine | `events/` | [domeny/events.md](domeny/events.md) |
| Commentary / TTS | `commentary/` | [domeny/commentary.md](domeny/commentary.md) |
| Race interpretation | `race/` | [domeny/race.md](domeny/race.md) |
| Sampling | `sampling/` | [domeny/sampling.md](domeny/sampling.md) |
| Heart rate (BLE) | `bio/` | [domeny/bio.md](domeny/bio.md) |
| Sysinfo | `system/` | [domeny/system.md](domeny/system.md) |
| Config load | `config.py`, `config_reload.py` | [domeny/config.md](domeny/config.md) |
| Dashboard i18n | `i18n.py` | [domeny/i18n.md](domeny/i18n.md) |
| YouTube OAuth | `oauth.py` | [domeny/oauth-youtube.md](domeny/oauth-youtube.md) |
| Util | `util/` | [domeny/util.md](domeny/util.md) |
| Web UI | `web/` | [domeny/web.md](domeny/web.md) |

Souborová mapa: [mapa-souboru.md](mapa-souboru.md).

## Kontrakty (nemnožit sem)

| Téma | Autorita |
| --- | --- |
| INI klíče a defaulty | [CONFIG.md](../../CONFIG.md) + `config/config.example.ini` |
| REST / WebSocket | [API.md](../../API.md) |
| Jak spustit / dashboard URL | [README.md](../../README.md) |
| EXE / služba | [BUILD_AND_DEPLOY.md](../../BUILD_AND_DEPLOY.md) |
| Semver / Release PR | [RELEASE_POLICY.md](../../RELEASE_POLICY.md) |
| Verze v `/health` | [VERSIONING.md](../../VERSIONING.md) |
| Commentary produkt (graf, TTS) | [COMMENTARY_ENGINE.md](../../COMMENTARY_ENGINE.md) |
| VR widget | [VR_SUPPORT.md](../../VR_SUPPORT.md), [RACELAB_VR_SETUP.md](../../RACELAB_VR_SETUP.md) |
| Cursor rules / skills | [.cursor/README.md](../../.cursor/README.md) |

Spec/plány v `docs/` (overlay V4 sizing, commentary assignments, admin spec) **nejsou runtime pravda**, pokud příslušná doména neřekne opak. Viz [jak-cist.md](jak-cist.md).

## In-flight (otevřené PR)

Stav k dokumentaci: [stav.md](stav.md). Detail:

- [#179 observers decoupling](inflight/pr-179-observers-decoupling.md) — draft do `master`, **nemergovat** před joint testem
- [#181 narrative observers](inflight/pr-181-narrative-observers.md) — stacked na #179, **ne do `master`**
- [#162 upload-artifact v7](inflight/pr-162-dependabot.md) — CI závislost

Na `master` **neexistuje** `EventFanout`, `SpeechScheduler`, `RaceObserver`, `race/flags.py`. Hledáš-li je grepem na aktuálním checkoutu a nic, je to správně — jsou na větvích výše.
