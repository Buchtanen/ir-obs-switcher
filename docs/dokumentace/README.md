# Dokumentace irswitch — mapa pro lidi i modely

**Čti tohle dřív, než začneš grepovat `src/`.** Po změně kódu **stejnou složku zase aktualizuj** (skill `dokumentace`, agent `docs-keeper`). Tichý skip není OK — buď page, nebo `Docs: no change (reason …)`.

> **Větev `codex/commentary-story-flow-spec`:** tato složka je **tenký index** (README, [jak-cist.md](jak-cist.md), [domeny/testy-ci.md](domeny/testy-ci.md), branch delta [domeny/server.md](domeny/server.md) + [domeny/events.md](domeny/events.md) pro #273/#284 runtime status (identity + speech/language/components + decisions ring), [inflight/](inflight/README.md)). Řádky tabulky níže, které odkazují na `architektura.md`, `stav.md`, `mapa-souboru.md` nebo většinu ostatních `domeny/*.md`, **na této větvi neexistují** — to není shipped drift, ale záměr. v2 narrative moduly (#239–#284 atd.) hledej v [inflight/](inflight/README.md) a [docs/v2.0.0/](../v2.0.0/README.md); nepiš je do `domeny/commentary.md` jako master pravdu.

Tato složka je **architektonický index** aktuálního `master`: co který modul dělá, kde končí jeho pravomoc, kam tečou data. Otevřená práce je jen v [inflight/](inflight/README.md).

Není to náhrada kontraktů. INI, HTTP a release zůstanou v souborech dole.

## Pořadí čtení

1. [Jak číst](jak-cist.md) — vrstvy pravdy
2. [Architektura](architektura.md) — dva pipeline, N12 fan-out
3. [Stav](stav.md) — co je na `master` teď
4. Doména z tabulky
5. Až potom kód

## Rychlý lookup

| Chci změnit / pochopit | Čti | Nesahaj sem napřed |
| --- | --- | --- |
| OBS scény, debounce, cooldown, GARAGE vs LOBBY | [logic](domeny/logic.md), [iracing](domeny/iracing.md) | `overlay/`, `events/` |
| `DrivingMode`, `SwitchState` | [runtime](domeny/runtime.md), [logic](domeny/logic.md) | Event Engine |
| iRSDK telemetrie, sentinely | [iracing](domeny/iracing.md) | `logic/` (žádné SDK volání) |
| OBS WebSocket, stream start/stop | [obs](domeny/obs.md) | policy v clientovi |
| HTTP/WS, `/health`, admin, GR | [server](domeny/server.md), [API.md](../../API.md) | `logic/` z handleru |
| Overlay HUD, V4, tape | [overlay](domeny/overlay.md), [V4 spec](../../assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec.md) | scene switcher |
| Battle / lap / pit, arbitration, fan-out | [events](domeny/events.md) | interpretace v `iracing/` |
| TTS, sequence graph, director | [commentary](domeny/commentary.md) | HUD copy |
| RaceState, observer, gapy | [race](domeny/race.md) | scene switcher |
| BLE tep, sysinfo, LHM | [bio](domeny/bio.md), [system](domeny/system.md) | `iracing/` |
| INI, hot-reload | [config](domeny/config.md), [CONFIG.md](../../CONFIG.md) | — |
| YouTube title | [oauth](domeny/oauth-youtube.md) | scene switch |
| HUD copy / overlay i18n | [i18n](domeny/i18n.md) | dashboard `i18n.py` |
| Testy, CI, release | [testy-ci](domeny/testy-ci.md) | — |
| Agent `/flow`, větev, PR, Cloud vs repo rules | [jak-cist](jak-cist.md), [Cursor README](../../.cursor/README.md), `.cursor/rules/10-task-flow-defaults.mdc` | Cloud `cursor/` prefix jako default |
| v2 narrative runtime (tato větev) | [v2.0.0](../v2.0.0/README.md), [implementation-handover](../v2.0.0/implementation-handover.md), [inflight § #284 NarrativeRuntime](inflight/README.md#284-narrative-runtime-lookup), [§ golden-health identity](inflight/README.md#284-273-golden-health-identity-slice-lookup), [§ golden-health speech](inflight/README.md#284-273-golden-health-speech-slice-lookup), [§ golden-health decisions](inflight/README.md#284-273-golden-health-decisions-slice-lookup) ([lookup table #239–#284](inflight/README.md#implementation-lookup-239284-branch-only)) | master `domeny/commentary.md` jako shipped v2 |
| Wave G #274 race-outcome family map (closeout, open PR) | [race-outcome-migration.md](../v2.0.0/race-outcome-migration.md), [inflight § #274](inflight/README.md#274-race-outcome-family-map-slice-8-lookup), [events branch delta](domeny/events.md#race-outcome-migration-map-contractsrace_outcome_family_mappy) | `domeny/events.md` as shipped map truth; `mapa-souboru.md` (absent on branch) |
| Wave G #275 timing family map (CLOSED) | [timing-family-migration.md](../v2.0.0/timing-family-migration.md), [inflight § #275](inflight/README.md#275-timing-family-map-slice-8-lookup), [events branch delta](domeny/events.md#timing-family-migration-map-contractstiming_family_mappy) | `domeny/events.md` as shipped map truth; live `FAMILY_ROUTE` flip |
| Wave G #276 ops family map (slice 2 open) | [ops-family-migration.md](../v2.0.0/ops-family-migration.md), [inflight § #276 slice 2](inflight/README.md#276-ops-family-map-slice-2-lookup), [events branch delta](domeny/events.md#ops-family-migration-map-contractsops_family_mappy) | `domeny/events.md` as shipped map truth; live `FAMILY_ROUTE` flip |
| `/health` `commentary` + `/api/commentary/runtime` status (#273 subset: identity, speech, components) | [server](domeny/server.md), [events](domeny/events.md), [API.md](../../API.md) | grep `src/` místo indexu |
| Otevřená práce | [inflight](inflight/README.md) | jako by už bylo na master |

## Domény (`src/irswitch/`)

| Doména | Balík | Dokument |
| --- | --- | --- |
| Runtime / entry | `main.py` | [runtime](domeny/runtime.md) |
| iRacing extraction | `iracing/` | [iracing](domeny/iracing.md) |
| OBS client | `obs/` | [obs](domeny/obs.md) |
| Scene switcher | `logic/` | [logic](domeny/logic.md) |
| HTTP glue | `server/` | [server](domeny/server.md) |
| Overlay runtime | `overlay/` | [overlay](domeny/overlay.md) |
| Event Engine | `events/` | [events](domeny/events.md) |
| Commentary / TTS | `commentary/` | [commentary](domeny/commentary.md) |
| Race interpretation | `race/` | [race](domeny/race.md) |
| Sampling | `sampling/` | [sampling](domeny/sampling.md) |
| Heart rate | `bio/` | [bio](domeny/bio.md) |
| Sysinfo | `system/` | [system](domeny/system.md) |
| Config | `config.py`, `config_reload.py` | [config](domeny/config.md) |
| Dashboard i18n | `i18n.py` | [i18n](domeny/i18n.md) |
| YouTube OAuth | `oauth.py` | [oauth-youtube](domeny/oauth-youtube.md) |
| Util | `util/` | [util](domeny/util.md) |
| Web UI | `web/` | [web](domeny/web.md) |

Souborová mapa: [mapa-souboru.md](mapa-souboru.md).

## Kontrakty (nemnožit sem)

| Téma | Autorita |
| --- | --- |
| INI klíče | [CONFIG.md](../../CONFIG.md) + `config/config.example.ini` |
| REST / WS | [API.md](../../API.md) |
| Start / GR URL | [README.md](../../README.md) |
| EXE / služba | [BUILD_AND_DEPLOY.md](../../BUILD_AND_DEPLOY.md) |
| Semver / Release PR | [RELEASE_POLICY.md](../../RELEASE_POLICY.md) |
| Verze v `/health` | [VERSIONING.md](../../VERSIONING.md) |
| Commentary produkt | [COMMENTARY_ENGINE.md](../../COMMENTARY_ENGINE.md) |
| V4 canvas | [overlay_v4_layout_sizing_motion_spec.md](../../assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec.md) |
| Pit Wall packy | [PIT_WALL.md](../../assets/overlay/themes/docs/PIT_WALL.md) |
| Golden V4 | [GOLDEN_V4.md](../../src/irswitch/web/overlay/GOLDEN_V4.md) |
| Cursor | [.cursor/README.md](../../.cursor/README.md) |

Žádné TUI. Žádný `/vr-status`. Operator UI je `/gr-status` + `/admin`. Overlay je OBS Browser Source.
