# Commentary extension — engineering handover

**Status:** `needs-engineering`

**Content branch:** `commentary-extension-texts`

**Runtime baseline:** `origin/master`

**Content baseline:** `origin/cursor/commentary-content-db-plan-8972` at `692da08`

**Machine-readable proposal:** [`commentary_extension_proposals.json`](commentary_extension_proposals.json)

This handover covers every runtime change required by the proposed session, SoF, and weather commentary. None of the work below is silently wired by the content change. The active graph still has 26 nodes and 12 unchanged edges.

## Acceptance criteria

- [ ] SessionInfo and telemetry extraction is fail-soft and resets on a new session key.
- [ ] Every proposed slot has one documented source, normalization rule, and missing-value behavior.
- [ ] SoF formula and roster filters are approved and covered by deterministic unit tests.
- [ ] New event types are added to the catalog only with explicit emitters or sidecars and tests.
- [ ] Practice, qualifying, race, SoF, and weather briefs speak no more than once per configured session trigger.
- [ ] Missing optional weather or roster values leave at least one fully bound line available.
- [ ] EN and CS render through the current validator and remain viewer-facing third person.
- [ ] Feature flags, if introduced, default off and are documented in `CONFIG.md` and `config/config.example.ini`.
- [ ] No database or network dependency is added.

## Proposed slots and binding contract

| Slot | Type | Example | Exact iRSDK / SessionInfo source | Normalization and fallback | Used by | Current status |
|---|---|---|---|---|---|---|
| `track` | `label` | `Spa-Francorchamps - Grand Prix Pits` | `WeekendInfo.TrackDisplayName`; optionally append `WeekendInfo.TrackConfigName` | Use display name first. Append configuration only when non-empty and not already part of the display name. Do not speak `TrackID`. | all session intros, `weather_brief` | **H1 extraction done** (`iracing.session_context.track_display_name` / `extract_session_context`); director binding / graph nodes still open (H4). |
| `field_size` | `int` | `32` | Count `DriverInfo.Drivers[]` | Exclude `CarIsPaceCar != 0`, `IsSpectator != 0`, invalid `CarIdx`, and empty roster entries. Missing `IsSpectator` → exclude (conservative). | qualify/race intro, `sof_brief` | **H1 roster parse done** (`parse_roster`); field_size / SoF binding still open (H2/H4). |
| `sof` | `label` | EN `2,450`; CS `2 450` | Derive from valid `DriverInfo.Drivers[].IRating` values | The current SoF spec proposes an arithmetic mean of racing drivers. Round once after aggregation, then format a locale-aware thousands separator before binding so the validator never receives a four-digit run. The product owner must approve the formula before wiring. | `sof_brief` | Formula, localization, and binding not implemented. |
| `sof_class` | `label` | EN `2,520`; CS `2 520` | Same roster, filtered by `CarClassID == DriverInfo.Drivers[DriverCarIdx].CarClassID` | Apply the same locale-aware formatter. Omit class-specific lines when player class or class roster is unavailable. | `sof_brief` | Formula, localization, and binding not implemented. |
| `skies` | `label` | `partly cloudy` | Live `Skies`; fallback `WeekendInfo.TrackSkies`; forecast `WeekendInfo.WeekendOptions.Skies` | Map the live enum to localized spoken labels. Keep forecast and current condition distinct in the envelope metadata. | `weather_brief` | Extraction, localization, and binding not implemented. |
| `air_temp` | `label` | `23 C` | Live `AirTemp`; fallback `WeekendInfo.TrackAirTemp`; forecast `WeekendInfo.WeekendOptions.WeatherTemp` | Normalize units, round for speech, and keep the unit in the bound value. | `weather_brief` | Extraction and binding not implemented. |
| `track_temp` | `label` | `31 C` | Prefer live `TrackTempCrew`, then `TrackTemp`; fallback `WeekendInfo.TrackSurfaceTemp` | Normalize units and round for speech. No precise forecast track-temperature field is evidenced in the current repository. | `weather_brief` | Extraction and binding not implemented. |
| `wind_speed` | `label` | `4 m/s` | Live `WindVel`; fallback `WeekendInfo.TrackWindVel`; forecast `WeekendInfo.WeekendOptions.WindSpeed` | Normalize source units before formatting. Do not combine values from different observation times. | `weather_brief` | Extraction and binding not implemented. |
| `precipitation` | `label` | `light rain` | Live `Precipitation`; corroborate with `TrackWetness` and `WeatherDeclaredWet` | Map live intensity to a small localized vocabulary. No precise forecast precipitation key is evidenced on master; never infer rain probability from `Skies`. | `weather_brief` | Extraction, mapping, and binding not implemented. |

The proposed slots use only graph-supported types (`int` and `label`). SoF uses `label`, not `int`, because the current validator rejects four consecutive digits after binding. A future typed `temperature`, `rating`, or `percentage` slot would be a separate schema change and is not required for this handover.

## Proposed node triggers

| Proposed node | Proposed event | Trigger and reset | Required engineering |
|---|---|---|---|
| `session_intro_practice` | `SESSION_INTRO_PRACTICE` | Once when the active session resolves to Practice; reset on `(SubSessionID, SessionNum)` change. | Approve event id; create accepted envelope or explicit commentary sidecar; bind `track`. |
| `session_intro_qualify` | `SESSION_INTRO_QUALIFY` | Once when the active session resolves to Qualify. | Approve event id; bind `track` and optional `field_size`; keep slot-light lines usable. |
| `session_intro_race` | `SESSION_INTRO_RACE` | Once when the active session resolves to Race, before ordinary race beats. | Approve event id and arbitration priority; bind `track` and optional `field_size`. |
| `sof_brief` | `SOF_BRIEF` | Once per race join, or another explicitly approved trigger from the SoF spec. | Approve formula and trigger; compute overall/class SoF; emit metrics; add missing-data behavior. |
| `weather_brief` | `WEATHER_BRIEF` | Once before or at session start; optional refresh requires a separate anti-spam policy. | Decide forecast versus current snapshot; extract and localize values; emit only mutually consistent observations. |

No proposed event id is currently in the Event Engine catalog. Do not insert these nodes into `sequence_graph.json` until the catalog, envelope path, and tests land together.

## Work packages

### H1 — SessionInfo roster and circuit context

**Status:** extraction API landed in `src/irswitch/iracing/session_context.py` (+ `tests/test_session_context.py`). Not yet hooked to telemetry snapshot fields, SoF (H2), or director events (H4).

1. Extend the iRacing extraction layer to read `DriverInfo` and the named `WeekendInfo` fields. ✅
2. Cache parsed session data by `(SubSessionID, SessionNum)` and invalidate it on change. ✅ (`SessionContextCache`)
3. Add immutable normalized fields for circuit display name, roster entries, and player class. ✅
4. Keep missing or malformed SessionInfo as normal state; never fail the main loop. ✅

Tests: circuit name with and without configuration; empty roster; pace car; spectator; missing `IsSpectator`; invalid `IRating`; multiclass player lookup; session reset. ✅

### H2 — SoF computation

1. Obtain product approval for the arithmetic-mean formula proposed in `EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md`, or replace it with an approved documented formula.
2. Implement a pure helper returning overall SoF, class SoF, field size, and evidence counts.
3. Round only the final aggregate and return `None` when no valid sample exists.
4. Keep overall and class values separately named in envelope metrics.

Tests: no drivers, one driver, single class, multiclass, spectator/pace-car exclusion, invalid ratings, missing player class, deterministic rounding.

### H3 — Weather extraction and speech formatting

1. Add the live weather variables to the telemetry read list only where needed.
2. Parse forecast/current SessionInfo values without treating them as interchangeable.
3. Create pure formatters for sky label, temperature, wind, and precipitation intensity in EN and CS.
4. Emit only values captured from the same logical snapshot.
5. Preserve slot-light variants so partial weather data still produces a fully bound choice.

Tests: enum localization; unit normalization; missing values; dynamic weather; wet track without active rain; precipitation without a forecast; EN/CS formatting under 90 characters.

### H4 — Events, director bindings, and anti-spam

1. Add approved event ids and emitters, or use a documented sidecar analogous to `ENTER_CAR`.
2. Put new values in `EventEnvelope.metrics` using the exact slot names above.
3. Extend `slot_bindings()` only after those metrics exist; do not reuse an existing slot with a new meaning.
4. Gate each intro/brief once per session key and reset deterministically.
5. Decide priorities relative to `in_car`, `final_lap`, battles, and finish.
6. Add a bounded anti-repeat history in a separate director change if product wants a hard no-repeat guarantee. This content branch only increases the pool; `rng.choice` can still repeat by chance.

Tests: accepted-envelope-only speech; once-per-session behavior; reset; priority collision; missing optional slot; every emotion bucket; deterministic RNG; anti-repeat window if implemented.

## Product decisions required

1. SoF formula: proposed arithmetic mean, official formula, or another documented calculation?
2. SoF trigger: race intro, car entry, pit entry, or a subset?
3. Weather voice: pre-session forecast, current conditions, or both with distinct wording?
4. Refresh policy: once per session only, or one explicitly rate-limited update after material weather change?
5. Intro order: session intro before or after `in_car`?
6. Anti-repeat: content-only probability reduction, or a hard bounded history in `CommentaryDirector`?

## Test and documentation impact

- Runtime tests: extraction fixtures, pure SoF/weather helpers, emitters, envelope metrics, director binding, reset, and missing-data fallbacks.
- Content tests: validate every proposed line using a temporary `GraphNode` with the proposed slots.
- Config: no change in this branch. Any new flags must update both `CONFIG.md` and `config/config.example.ini`, default off.
- API: no change unless the new context or decisions are exposed publicly.
- Database: no change; the local graph-shaped JSON remains the only content store.
