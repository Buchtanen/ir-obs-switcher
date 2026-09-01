# Commentary extension — engineering handover

**Status:** `wired` (W4/H4); driver-fact extension `needs-engineering`

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
- [ ] RaceObserver maintains session-scoped hero/opponent driver profiles and
  updates them safely on a roster revision or driver swap.
- [ ] Driver-fact text remains optional and sparse; missing profile data never
  removes the profile-free fallback pool.
- [ ] Nationality stays unbound until a trustworthy source is approved; no
  country is inferred from `ClubName`, driver name, language, or livery.

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

<a id="driver-fact-extension-needs-engineering"></a>

## Driver-fact extension — `needs-engineering`

These are proposed context slots only. They are not added to the active graph
or silently bound by this specification change. RaceObserver collects the facts
once per SessionInfo revision, updates a profile when the same `CarIdx` changes
`UserID`, and publishes the relevant profiles through the frozen N12
`ContextSnapshot`.

### Proposed slots and sources

| Slot | Type | Example | Exact iRSDK / SessionInfo source | Intended nodes | Missing-value and implementation notes |
| --- | --- | --- | --- | --- | --- |
| `hero_irating` | `label` | EN `2,450`; CS `2 450` | Player row in `DriverInfo.Drivers[].IRating`, joined by `DriverInfo.DriverCarIdx` / `PlayerCarIdx` | session intros, `sof_brief`, selected `field_fact` | Binding not implemented. Format before TTS; invalid/missing stays unbound. |
| `target_irating` | `label` | EN `3,120`; CS `3 120` | Target `CarIdx` row in `DriverInfo.Drivers[].IRating` | `hunting`, `hunted`, `side_by_side`, `attack_range`, `rival_threat` | Binding not implemented. Requires exact accepted-event target/correlation match. |
| `hero_safety_rating` | `label` | `A 3.42` | Player row `DriverInfo.Drivers[].LicString` | session intros, rare `field_fact` | Binding not implemented. `LicLevel` / `LicSubLevel` are validation aids, not a second display formula. |
| `target_safety_rating` | `label` | `B 2.87` | Target row `DriverInfo.Drivers[].LicString` | selected battle/rival beats | Binding not implemented. Do not equate SR with expected clean driving. |
| `hero_car` | `label` | `Porsche 911 GT3 R` | Player row `CarScreenName`; fallback `CarScreenNameShort` | session intros, pit, finish, rare `field_fact` | Binding not implemented. Never speak `CarPath` or numeric `CarID`. |
| `target_car` | `label` | `BMW M4 GT3` | Target row `CarScreenName`; fallback `CarScreenNameShort` | selected battle/rival beats | Binding not implemented. Prefer name or car, not a stacked biography. |
| `hero_start_position` | `int` | `12` | One-time pre-green `CarIdxClassPosition[hero]`; overall `CarIdxPosition[hero]` only for single-class/fallback with recorded scope | position gain/loss, finish, session wrap | Binding not implemented. Freeze after first valid capture; late join stays unbound. |
| `target_start_position` | `int` | `8` | Same one-time capture for the target `CarIdx` | rare battle/finish context | Binding not implemented. Never substitute current position or qualifying result. |
| `hero_nationality` | `label` | `Czechia` | **No reliable source evidenced in the current in-session iRSDK schema** | rare intro/field fact | Binding not implemented. Requires a separately approved and tested source. |
| `target_nationality` | `label` | `Italy` | **No reliable source evidenced in the current in-session iRSDK schema** | rare named-rival aside | Binding not implemented. Never infer from `ClubName`, name, language, or livery. |

`start_position` uses the same class-first narrative scope as live `position`.
RaceObserver stores the explicit `class` / `overall` scope in context so a
multiclass story cannot compare unlike positions. `QualifyResultsInfo.Results[]`
may support a separate qualifying-result story, but is not silently renamed to
race start position.

### Data flow and freshness contract

```text
iRacing telemetry + SessionInfo revision/content digest
  -> RaceObserver DriverFactLedger (`CarIdx`, `UserID`, `identity_epoch`)
  -> frozen N12 ContextSnapshot version N
  -> accepted event batch embeds version N and its exact payload
  -> CommentaryConsumer dequeues event + context together
  -> latest-context veto gate -> slot resolution -> variant choice -> validator
```

- The producer refreshes RaceObserver before collecting candidates. Context and
  accepted events therefore describe the same tick; acceptance-to-context age
  is at most one configured poll interval.
- Commentary resolves `hero_*` and `target_*` only from the embedded context.
  It never reads RaceObserver, SessionInfo, or the currently nearest car.
- `latest_context` may veto an embedded binding when session or
  `(CarIdx, UserID, identity_epoch)` changed. It must not overwrite an old event
  with a newer driver's fact.
- Live relationship copy (gap, current position, hunting/hunted) has a 3-second
  speech-age ceiling in addition to the normal event TTL. Static iRating/SR/car
  facts remain valid only while the same session identity is current. Start
  position is immutable for that identity.
- `SessionReset` flushes deferred old-session speech. A stale/missing profile
  reruns variant selection without profile slots; if none binds, skip with
  `driver_context_stale`, `driver_identity_changed`, or
  `driver_fact_unavailable`.

### Text usage policy

- Keep at least 70% of every affected EN/CS cell free of driver-profile slots.
- Normally use one driver fact per utterance. A progress comparison may combine
  start and current position because they form one fact, not a biography list.
- Use target facts only with a stable target `CarIdx` and name/correlation.
- Rotate facts with a per-driver, per-fact cooldown; do not repeat the same
  iRating, SR, car, or nationality every time the rival re-enters near field.
- Treat ratings as context, not predictions or value judgements. Do not derive
  nationality or stereotypes. Keep viewer-facing third person in EN and CS.
- If the selected fact is missing, choose another fully bound profile-free line;
  never speak `unknown`, raw ids, or a partially filled template.

### Proposed bilingual copy examples

Each example intentionally uses one contextual detail rather than listing the
whole profile.

| Context | EN | CS |
| --- | --- | --- |
| race intro / car | `He starts the race in the {hero_car}.` | `Do závodu vyráží s vozem {hero_car}.` |
| race intro / grid | `He starts from P{hero_start_position}.` | `Startuje z {hero_start_position}. místa.` |
| field aside / iRating | `His iRating is {hero_irating}, useful context for this field.` | `Jeho iRating {hero_irating} dokresluje sílu tohoto pole.` |
| field aside / SR | `He brings a {hero_safety_rating} licence into this race.` | `Do závodu vstupuje s licencí {hero_safety_rating}.` |
| hunting / rival iRating | `{target_name} brings an iRating of {target_irating} to this fight.` | `{target_name} jde do souboje s iRatingem {target_irating}.` |
| hunted / rival SR | `{target_name} carries a {target_safety_rating} licence into the chase.` | `{target_name} má pro tenhle tlak licenci {target_safety_rating}.` |
| battle / rival car | `The {target_car} of {target_name} is the next obstacle.` | `Další překážkou je {target_name} s vozem {target_car}.` |
| progress from grid | `From P{hero_start_position} to P{position}, his race is moving forward.` | `Ze startovního P{hero_start_position} na P{position}, závod se posouvá.` |
| finish / car | `He brings the {hero_car} home.` | `S vozem {hero_car} přijíždí do cíle.` |
| named rival / nationality | `{target_name} represents {target_nationality} in this fight.` | `{target_name} v tomhle souboji reprezentuje {target_nationality}.` |

### H5 — Driver profiles, context binding, and copy

1. Add a pure, fail-soft `DriverProfileSnapshot` extractor and bounded
   `CarIdx` ledger owned by RaceObserver.
2. Refresh on SessionInfo revision/content digest; replace on `UserID` change;
   clear on session reset/disconnect.
3. Capture class/overall start positions once at the pre-green boundary, with a
   diagnosed first-green fallback and no late-join invention.
4. Put hero and relevant target profiles into N12 `ContextSnapshot`; bind them
   after dequeue by accepted subject/target identity, never by current nearest
   car.
5. Implement the freshness veto before variant selection, including ordered
   reset flush, `identity_epoch`, the 3-second live-relation ceiling, fallback
   reselection, and explicit skip reasons.
6. Add only selected lines to the graph, preserving the 70% profile-free floor,
   then validate all EN/CS/HR cells with missing and full profile fixtures.
7. Leave nationality slots unwired until a source is separately approved. An
   external lookup must address authentication, caching, rate limits, privacy,
   offline behavior, and the no-new-dependency rule.

Tests: malformed roster, rating/SR formatting, car fallback, driver swap,
SessionInfo refresh, multiclass start scope, first-green fallback, late join,
reset, stale target correlation, changed identity on queued work, relation older
than 3 seconds, latest-context veto without substitution, missing nationality,
fact cooldown, 70% profile-free density, and all bilingual bound examples
against the validator.

<a id="situation-and-llm-context-needs-engineering"></a>

## Situation and LLM context — `needs-engineering`

Current commentary does not reliably tell the viewer which lap or part of the
race is underway. H6 adds deterministic situation data to the N12 context,
selected graph copy, and the optional LLM fact lock. This specification change
does not modify the active graph or runtime.

### Proposed situation slots

| Slot | Type | Example | Exact source / derivation | Intended nodes | Notes |
| --- | --- | --- | --- | --- | --- |
| `current_lap` | `int` | `12` | Live `Lap`, normalized and greater than zero | `field_fact`, `lap_complete`, selected battle/position bridges | Binding not implemented. Must pass the 3-second situation freshness gate. |
| `lap_context` | `label` | EN `lap 12 of 30`; CS `12. kolo z 30` | `Lap` plus fixed active-session `SessionInfo.Sessions[SessionNum].SessionLaps`; fall back to current-lap-only label | `field_fact`, phase bridge, session wrap | Binding not implemented. Locale formatter owns word order and Czech ordinal form. |
| `race_phase` | `label` | EN `middle phase`; CS `střední fáze` | Upstream deterministic phase policy from progress; explicit final/checkered/finished override | `field_fact`, selected battle/position bridges | Binding not implemented. LLM may only reuse an upstream-formatted allowed phrase. |
| `remaining_context` | `label` | EN `5 laps remaining`; CS `zbývá 5 kol` | Sentinel-aware `SessionLapsRemain`; timed fallback from proposed `SessionTimeRemain` extraction | `field_fact`, closing/final bridges | Binding not implemented. Locale formatter handles pluralization; omit when unreliable. |

Raw LLM situation fields additionally include `lap_completed`, `total_laps`,
`session_time_elapsed_s`, `session_time_total_s`, `session_time_remaining_s`,
`progress_ratio`, `progress_source`, and explicit final/checkered/finished
booleans. They are prompt facts, not all separate spoken slots.

### Text cadence and usage

- Provide at least two `current_lap` / `lap_context` capable EN and CS lines in
  every `field_fact` HR cell while keeping the existing slot-free fallback pool.
- Mention lap/phase on deterministic phase change or after 120 seconds without
  a spoken situation fact. Apply a 90-second lap/phase fact cooldown.
- Do not announce every new lap. Never displace battle, incident, pit,
  final-lap, finish, or session-control speech.
- Situation-bearing copy must be selected within 3 seconds of its context. On
  delay or lap/phase mismatch, reselect without situation slots or record
  `situation_context_stale`.
- Practice/Qualifying may speak current lap/time, but never reuse Race
  `opening/middle/closing` language.

### Proposed bilingual copy examples

| Context | EN | CS |
| --- | --- | --- |
| lap orientation | `The field is working through {lap_context}.` | `Pole právě projíždí {lap_context}.` |
| lap + phase | `Lap {current_lap}; race phase: {race_phase}.` | `Kolo {current_lap}; fáze závodu: {race_phase}.` |
| hero position | `On {lap_context}, he is running P{position}.` | `Aktuálně běží {lap_context}, drží P{position}.` |
| phase bridge | `Race phase: {race_phase}; the pressure keeps building.` | `Fáze závodu: {race_phase}; tlak dál roste.` |
| remaining | `{remaining_context}; every clean move matters now.` | `{remaining_context}; každý čistý manévr teď rozhoduje.` |
| battle bridge | `Lap {current_lap}, and this fight is still alive.` | `Kolo {current_lap} a tenhle souboj stále žije.` |
| closing context | `The race has reached its {race_phase}.` | `Aktuální fáze závodu: {race_phase}.` |
| delayed event | `Back on lap {current_lap}, he was closing the gap.` | `Ještě v {current_lap}. kole stahoval ztrátu.` |

The Czech templates use a colon before the preformatted `race_phase` label to
avoid runtime case inflection. If a future sentence needs another grammatical
case, use a separate preformatted phase-phrase slot instead of guessing.

### LLM situation fact lock

The optional polish request receives the fully bound skeleton plus a bounded
fact object from the same embedded context. It must not receive live reader
access, raw arrays, or the complete roster. The prompt explicitly distinguishes
event-time facts from live/current wording.

Director also supplies `ALLOWED SITUATION ADDITIONS`: `NONE`, or a bounded list
of exact localized phrases from the snapshot. Subject to the 90-second
situation cooldown, the LLM may add zero or one phrase. It cannot freely
compose a new lap, remaining count, or phase from raw values.

Post-validation must reject `invented_situation_number`,
`unapproved_situation_addition`, `situation_phase_conflict`, and
`stale_situation_framing`. A rejected, timed-out, or malformed rewrite falls
back to the validated skeleton. If context lacks a lap/phase field, the prompt
forbids introducing one.

### H6 — Situation extraction, copy, and LLM contract

1. Extend telemetry/session extraction with normalized `SessionTimeRemain` and
   fixed active-session total laps/time; preserve unlimited/missing sentinels.
2. Add pure `SituationSnapshot` construction and deterministic phase tests for
   lap-limited, timed, unlimited, and missing-data races.
3. Carry the snapshot in every N12 context and enforce the same-tick acceptance
   plus 3-second final-selection freshness contracts.
4. Extend A5 `FIELD_FACT` rotation with lap/phase cadence and high-priority
   suppression; track last spoken lap, phase, and monotonic time.
5. Add the selected EN/CS graph lines and locale formatters without changing the
   meaning of the existing `lap` slot.
6. Build the bounded LLM fact block from the embedded context and implement
   numeric/phase fact-lock validation with skeleton fallback.
7. Record situation input/digest and polish decision in replay/debug tape so
   identical captures produce identical skeleton and acceptance decisions.

Tests: source sentinels, lap/time progress, 20%/70% boundaries, explicit phase
overrides, current-lap formatting, CS plurals/phase grammar, 120-second cadence,
90-second cooldown, busy suppression, 3-second stale veto, deferred past
framing, invented numbers/phases, timeout fallback, replay determinism, and all
bound EN/CS examples against the current validator.

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
