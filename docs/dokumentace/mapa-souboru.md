# Mapa souborů

Kořen runtime: `src/irswitch/`. Testy: `tests/test_*.py`. Web statika: `src/irswitch/web/`.

Hledej podle této tabulky, ne full-repo grep napoprvé.

## Entry a config

| Soubor | Role |
| --- | --- |
| `main.py` | CLI, `run_service`, `main_loop`, OAuth startup |
| `config.py` | Parse INI → `AppConfig` |
| `config_reload.py` | Live vs restart-required keys |
| `models.py` | `DrivingMode`, `SwitchState` |
| `oauth.py` | YouTube OAuth token store |
| `i18n.py` | Stringy GR/VR dashboardu (ne overlay HUD) |

## `iracing/`

| Soubor | Role |
| --- | --- |
| `reader.py` | `pyirsdk` wrapper, process detect, QUIT stall, `read_mode` / `read_telemetry` |
| `extractors.py` | `extract_mode`, session type/num — **GARAGE = IsGarageVisible** |
| `telemetry.py` | Seznam SDK vars → `TelemetrySnapshot` |
| `sdk_units.py` | Jednotky, sentinely |
| `drivers.py` | Jména z DriverInfo |
| `sectors.py` | Sector pct → timing points |
| `session_context.py` | Session/track metadata |
| `sof.py` | Strength of field |
| `weather.py` | Počasí z iRSDK |
| `trk_loc.py` | Track location helper |

In-flight (#181): `session_flags.py` — decode `SessionFlags` bitů. Na master není.

## `obs/`

| Soubor | Role |
| --- | --- |
| `client.py` | obs-websocket v5: scény, stream, volume (duck) |
| `stream_status_refresh.py` | Hrana OBS streaming → YouTube status |
| `youtube_vod.py` | Patch kapitol do VOD description |

## `logic/`

| Soubor | Role |
| --- | --- |
| `state_machine.py` | Debounce, cooldown, override, grace 3 s po loadu |
| `policy.py` | `DrivingMode` → název OBS scény |
| `stream_chapters.py` | In-memory kapitoly pro WS/status |
| `youtube_chapters.py` | Formát YouTube chapter textu |

## `server/`

| Soubor | Role |
| --- | --- |
| `api.py` | REST + WS `/ws`, create_app |
| `admin.py` | `/admin`, `/api/admin/*` |
| `admin_health.py` | Ready / blocking / warnings |
| `dashboards.py` | `/gr-status`, `/vr-status` |
| `metrics.py` / `metrics_display.py` | Counters |
| `event_log.py` | Ring buffer pro dashboard |
| `task_registry.py` | Named asyncio tasks |
| `app_keys.py` | aiohttp AppKey |
| `health_banner.py` | Konzolový banner |

## `overlay/`

| Soubor | Role |
| --- | --- |
| `runtime.py` | Orchestrace ticků, engine, commentary hook |
| `bus.py` | Snapshot + WS broadcast (secret redaction) |
| `http.py` | `/overlay`, `/ws/overlay`, config UI |
| `models.py` | `TelemetrySnapshot`, `RaceState`, `BioState`, `SystemState` |
| `protocol.py` | `CandidateEvent`, `RaceEvent`, WS envelope |
| `settings.py` | Overlay/event/commentary dataclass z INI |
| `session.py` | Session key + warmup + reset hooks |
| `tape.py` | JSONL session tape |
| `mock.py` / `replay.py` / `replay_input.py` | Dry-run bez iRacing |
| `display.py` / `display_v4.py` | Server-side display mapping |
| `schema.py` | Overlay config schema pro `/api/config` |
| `i18n.py` | Overlay language + HUD copy |
| `activity.py` | Overlay activity log |
| `v4_manifest_schema.py` | Validace theme manifestu |

## `events/`

| Soubor | Role |
| --- | --- |
| `engine.py` | Fan-out RaceState → emittery (deterministické pořadí) |
| `manager.py` | MVP lifecycle (duration/cooldown/active) |
| `manager_v2.py` | Sequence + V4 envelopes + pit guard |
| `envelope.py` | `EventEnvelope` wire format |
| `event_catalog.py` | eventType ↔ V4 manifest state |
| `arbitration.py` | Pit cycle suppress, eviction |
| `decision_log.py` | Proč event prošel / ne |
| `battle.py`, `position.py`, `overtake.py`, `lap.py`, `incident.py`, `pit.py`, `pit_story.py`, `session.py`, `session_phase.py`, `link_drop.py`, `invalid_lap.py`, `clean_streak.py`, `rival_threat.py`, `practice.py`, `quali.py`, `sector_split.py`, `target_locked.py`, `hr_pressure.py`, `battle_intensity.py` | Emittery |
| `adapters/` | RaceEvent → V4 envelope |

In-flight (#179): `fanout.py`.

## `commentary/`

| Soubor | Role |
| --- | --- |
| `director.py` | Envelope → graph node → TTS |
| `graph.py` + `data/sequence_graph.json` | Sequence graph |
| `tts.py` | Sink (SAPI process / null) |
| `duck.py` | OBS duck během řeči |
| `polish.py` | Volitelný LLM framing |
| `validator.py` | Slot fill + max seconds |
| `in_car.py` / `session_briefs.py` | Sidecar detektory (mimo engine) |
| `bridge.py` | Legacy RaceEvent → speech envelope |
| `http.py` | `/commentary` test UI |
| `anti_repeat.py`, `slot_format.py`, `assignments.py` | Anti-repeat, formát, text assignments |

In-flight (#179): `scheduler.py`, `consumer.py`. In-flight (#181): `opener.py`, `stream_context.py`.

## `race/`

| Soubor | Role |
| --- | --- |
| `context.py` | Snapshot → RaceState |
| `opponents.py` | Ahead/behind, gapy |
| `history.py` | Bounded gap history |
| `timing/` | Sector/lap crossings, store, reference |

In-flight (#179): `observer.py`, `aftermath.py`, `narrative.py`, `story.py`. In-flight (#181): `flags.py`, `timing_hunt.py`.

## `bio/`, `system/`, `sampling/`, `util/`

Viz příslušné doménové stránky. Krátce: `bio/provider.py` BLE HR; `system/provider.py` psutil/NVML/LHM; `sampling/scheduler.py` Hz smyčky; `util/clock.py` monotonic.

## `web/`

| Cesta | UI |
| --- | --- |
| `web/admin/` | Operator admin |
| `web/overlay/` | HUD (JS V3/V4) |
| `web/commentary/` | TTS test page |
| `web/themes/`, `web/themes-v4/` | Manifesty a assety |
| GR/VR HTML | servíruje `server/dashboards.py` (+ assets) |

## Testy (orientace)

Prefix `tests/test_<oblast>.py` odpovídá doméně (`test_state_machine.py`, `test_event_engine_*`, `test_commentary_*`, `test_overlay_*`). Replay scénáře: `tests/fixtures/replay_input/`.
