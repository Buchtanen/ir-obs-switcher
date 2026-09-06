# Mapa souborů

Kořen runtime: `src/irswitch/`. Testy: `tests/test_*.py`. Web: `src/irswitch/web/`.

Hledej podle tabulky, ne full-repo grep napoprvé.

## Entry a config

| Soubor | Role |
| --- | --- |
| `main.py` | CLI, `run_service`, `main_loop`, OAuth startup |
| `config.py` | Parse INI → `AppConfig` |
| `config_reload.py` | Live vs restart-required keys |
| `models.py` | `DrivingMode`, `SwitchState` |
| `oauth.py` | YouTube OAuth token store |
| `i18n.py` | Stringy GR/admin dashboardu (ne overlay HUD) |

## `iracing/`

| Soubor | Role |
| --- | --- |
| `reader.py` | `pyirsdk` wrapper, process detect, QUIT stall |
| `extractors.py` | `extract_mode` — **GARAGE = IsGarageVisible** |
| `telemetry.py` | SDK vars → `TelemetrySnapshot` |
| `sdk_units.py` | Jednotky, sentinely |
| `drivers.py` | DriverInfo jména |
| `sectors.py` | Sector pct |
| `session_context.py` | Session/track metadata |
| `session_flags.py` | Decode `SessionFlags` bitů (extraction only) |
| `sof.py` | Strength of field (commentary helper, ne overlay karta) |
| `weather.py` | Počasí |
| `trk_loc.py` | Track location |

## `obs/`

| Soubor | Role |
| --- | --- |
| `client.py` | obs-websocket v5 |
| `stream_status_refresh.py` | OBS streaming → YouTube status |
| `youtube_vod.py` | Patch kapitol do VOD |

## `logic/`

| Soubor | Role |
| --- | --- |
| `state_machine.py` | Debounce, cooldown, override, grace po loadu |
| `policy.py` | `DrivingMode` → OBS scéna |
| `stream_chapters.py` | In-memory kapitoly |
| `youtube_chapters.py` | Formát YouTube chapter textu |
| `broadcast_clock.py` | Jeden broadcast clock |

## `server/`

| Soubor | Role |
| --- | --- |
| `api.py` | REST + WS `/ws`, `create_app` |
| `dashboards.py` | `/gr-status` (žádné `/vr-status`) |
| `admin.py` / `admin_health.py` | `/admin`, `/api/admin/*` |
| `metrics.py` / `metrics_display.py` | Counters |
| `event_log.py` | Ring buffer |
| `task_registry.py` | Named asyncio tasks |
| `app_keys.py` | aiohttp AppKey |
| `health_banner.py` | Konzolový banner |

## `overlay/`

| Soubor | Role |
| --- | --- |
| `runtime.py` | Overlay tick glue |
| `bus.py` | Snapshot + WS broadcast |
| `http.py` | `/overlay`, `/ws/overlay` |
| `consumer.py` | N12 overlay consumer |
| `models.py` | Snapshot / RaceState / Bio / System |
| `protocol.py` | Candidate / RaceEvent / WS envelope |
| `tape.py` | JSONL session tape (`llm_polish` na INFO když `session_tape_llm`) |
| `schema.py` | FieldSpec / overlay field schema |
| `replay.py` / `replay_input.py` | JSONL replay do overlay ticku |
| `display.py` / `display_v4.py` | Server-side display mapping |
| `i18n.py` | HUD copy |
| `v4_manifest_schema.py` | Theme manifest validace |

## `events/`

| Soubor | Role |
| --- | --- |
| `engine.py` | Fan-out RaceState → emitery |
| `manager.py` / `manager_v2.py` | Lifecycle + V4 envelopes |
| `envelope.py` | `EventEnvelope` |
| `arbitration.py` | Pit suppress, eviction |
| `async_fanout.py` | N12 bounded broadcast |
| `fanout.py` | Sync fan-out helper |
| `stream.py` | Frozen stream items |
| Emittery | `battle.py`, `position.py`, `overtake.py`, `lap.py`, `incident.py`, `pit.py`, … |
| `adapters/` | RaceEvent → V4 envelope |
| `scenarios/` | Deterministic scenario engine (#216 subset): `engine.py`, `registry.py`, `loader.py`, `model.py`, `track_excursion.py` |

## `commentary/`

| Soubor | Role |
| --- | --- |
| `director.py` | Envelope → graph node → TTS |
| `graph.py` + `data/sequence_graph.json` | Sequence graph |
| `graph_runtime.py` | Stateful modes `legacy\|shadow\|active` |
| `consumer.py` / `scheduler.py` | N12 consumer + speech queue |
| `tts.py` / `supertonic_backend.py` | Sinks |
| `polish.py` / `composer.py` / `microplan.py` | Optional LLM |
| `prepared_filler.py` / `llm_lane.py` / `style_cards.py` | Prepared filler + polish lane |
| `speech_hero.py` / `story_identity.py` | Hero naming / story identity |
| `replay_eval.py` | Recorded `llm_polish` eval (not CI-required) |
| `http.py` | `/commentary` TTS test UI |
| `validator.py` | Utterance / graph cell validation |
| `in_car.py` / `session_briefs.py` / `opener.py` | Sidecar |
| `stream_context.py` | Stream-start TTS + opener mutex |

## `race/`

| Soubor | Role |
| --- | --- |
| `runtime.py` / `pipeline.py` | N12 composition |
| `observer.py` | Race observer |
| `context.py` | Snapshot → RaceState |
| `opponents.py` | Ahead/behind, gapy |
| `flags.py` / `aftermath.py` / `narrative.py` / `story.py` | Narrative |
| `session_end.py` / `grid_story.py` / `timing_hunt.py` | Finish / start / P/Q |
| `ministory.py` / `editorial_stage.py` / `prepared_facts.py` | Editorial MiniStory + stale-call revision |
| `order.py` / `run.py` / `history.py` / `driver_facts.py` | Order / run epoch / driver facts |
| `timing/` | Sector/lap crossings |
| `watcher_log.py` | Debug decision ring |

## `bio/`, `system/`, `sampling/`, `util/`

`bio/provider.py` BLE HR. `system/provider.py` + `lhm_http.py` sysinfo. `sampling/scheduler.py` poll helper (adaptive channels **nejsou** runtime — spec #212). `util/clock.py` monotonic; `single_instance.py` bind před init; `diagnostic_voice.py` opt-in EN SAPI operator hlášky (`[diagnostics] voice`).

## `web/`

| Cesta | UI |
| --- | --- |
| `web/admin/` | Operator admin |
| `web/overlay/` | HUD V3/V4 JS |
| `web/commentary/` | TTS test |
| `web/themes/` | V3 raster (legacy fallback) |
| `web/themes-v4/` | V4 + Pit Wall runtime |

## Testy

`tests/test_<oblast>.py`. Replay: `tests/fixtures/replay_input/`. Golden: `tests/test_golden_v4_fixtures.py`. Linky indexu: `tests/test_dokumentace_links.py`.
