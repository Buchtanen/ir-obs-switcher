# Commentary extension — engineering handover

**Status:** `wired` (W4/H4)

**Content branch:** `commentary-extension-texts`

**Runtime baseline:** `origin/cursor/commentary-w4-integrate-8972` (+ H4 wire branch)

**Machine-readable proposal:** [`commentary_extension_proposals.json`](commentary_extension_proposals.json) (`status: wired`)

Session intro, SoF, and weather briefs are in `sequence_graph.json` and spoken via COMMENTARY_ONLY sidecars (`SessionBriefsDetector`), gated by `commentary.session_briefs` (default off). Topology (edges) unchanged.

## Acceptance criteria

- [x] SessionInfo and telemetry extraction is fail-soft and resets on a new session key.
- [x] Every proposed slot has one documented source, normalization rule, and missing-value behavior.
- [x] SoF formula and roster filters are approved and covered by deterministic unit tests (arithmetic-mean interim).
- [x] New event types use COMMENTARY_ONLY sidecars (not overlay catalog) with tests.
- [x] Practice, qualifying, race, SoF, and weather briefs speak no more than once per session key.
- [x] Missing optional weather or roster values leave at least one fully bound line available.
- [x] EN and CS render through the current validator and remain viewer-facing third person.
- [x] Feature flag `commentary.session_briefs` defaults off; documented in `CONFIG.md` and `config/config.example.ini`.
- [x] No database or network dependency is added.

## Proposed slots and binding contract

| Slot | Type | Example | Exact iRSDK / SessionInfo source | Normalization and fallback | Used by | Current status |
|---|---|---|---|---|---|---|
| `track` | `label` | `Spa-Francorchamps - Grand Prix Pits` | `WeekendInfo.TrackDisplayName`; optionally append `WeekendInfo.TrackConfigName` | Use display name first. Append configuration only when non-empty and not already part of the display name. Do not speak `TrackID`. | all session intros, `weather_brief` | **Wired** (`session_context` + director `slot_bindings`) |
| `field_size` | `int` | `32` | Count `DriverInfo.Drivers[]` | Exclude pace car / spectator / invalid `CarIdx`. Missing `IsSpectator` → exclude. | qualify/race intro, `sof_brief` | **Wired** |
| `sof` | `label` | EN `2,450`; CS `2 450` | Arithmetic mean of valid racing `IRating` values | Round once after aggregation; locale thousands separator via `format_sof_label`. **Not official iRacing SoF.** | `sof_brief` | **Wired** (interim formula) |
| `sof_class` | `label` | EN `2,520`; CS `2 520` | Same roster, filtered by player `CarClassID` | Same formatter; omit when class unavailable. | `sof_brief` | **Wired** |
| `skies` | `label` | `partly cloudy` | Live `Skies`; fallback `WeekendInfo.TrackSkies` | Localized spoken labels via `spoken_weather_bindings`. | `weather_brief` | **Wired** (prefer live) |
| `air_temp` | `label` | `23 C` | Live `AirTemp`; fallback `WeekendInfo.TrackAirTemp` | Rounded Celsius with unit. | `weather_brief` | **Wired** |
| `track_temp` | `label` | `31 C` | `TrackTempCrew` / `TrackTemp`; fallback `TrackSurfaceTemp` | Rounded Celsius with unit. | `weather_brief` | **Wired** |
| `wind_speed` | `label` | `4 m/s` | Live `WindVel`; fallback `TrackWindVel` | Normalized to m/s. | `weather_brief` | **Wired** |
| `precipitation` | `label` | `light rain` | Live `Precipitation` + wetness/declared | Small EN/CS vocab; never invent rain from `Skies`. | `weather_brief` | **Wired** |

## Trigger policy (H4 product choices)

| Node | Event | Trigger | Reset |
|---|---|---|---|
| `session_intro_*` | `SESSION_INTRO_*` | Once when session type resolves to Practice / Qualify / Race | `(SubSessionID, SessionNum)` or disconnect |
| `sof_brief` | `SOF_BRIEF` | Once when **race** active, intro acknowledged, roster ready (`field_size > 0`) | same |
| `weather_brief` | `WEATHER_BRIEF` | Once after intro (after SoF attempt on race); prefer live snapshot | same |

Arbitration: at most one brief envelope per overlay tick; if a brief speaks, `ENTER_CAR` is deferred to the next tick so in_car is not starved. Priorities follow proposals JSON (race intro 64 > SoF 46 > qualify 44 > in_car 38 > practice 36 > weather 34).

## Work packages

### H1 — SessionInfo roster and circuit context — done
### H2 — SoF computation — done (interim arithmetic mean)
### H3 — Weather extraction and speech formatting — done
### H4 — Events, director bindings, and anti-spam — done

Flag: `commentary.session_briefs` (default `false`) → director reason `session_briefs_disabled`.

## Test and documentation impact

- Runtime tests: `tests/test_commentary_session_briefs.py` (+ existing H1/H2/H3 suites)
- Content tests: density expects 32 nodes / 3332 lines; proposals marked wired
- Config: `CONFIG.md` + `config/config.example.ini`
- `COMMENTARY_ENGINE.md` session-briefs section
