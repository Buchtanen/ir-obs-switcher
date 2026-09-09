# v2.0.0 event and beat disposition freeze

**Status:** 64-beat inventory, closed successor DAG and 256 EN pattern cards are machine-frozen; #256 implementation-time auditor proves the matrix; #257 typed catalog loader is implemented; #258 lineage-aware EpisodeRegistry is closed; #259 resolved-episode retention is closed; #260 long-silence clock and filler opportunities are implemented. Next: #261 immutable BeatPlan.

This branch-only artifact closes the inventory gap between the current V4 event surface, the legacy commentary graph and the target narrative catalog. It is not shipped to `master`. Implemented catalog behavior is projected in [catalog-behavior.md](catalog-behavior.md).

## Audited source inventory

The previous “50 event types” count covered only `sequence_graph.json`. The complete master vocabulary is the union below:

| Source | Count | Meaning |
| --- | ---: | --- |
| Legacy commentary graph | 50 | Event identifiers referenced by 54 nodes and 24 edges |
| V4 overlay event catalog entries | 37 | Public overlay presentation identifiers |
| V4 catalog fallback keys | 5 | Compatibility aliases, not necessarily runtime emitters |
| Additional commentary emitter `PACE_HUNT` | 1 | Accepted commentary-only event absent from both catalogs |
| **Unique union** | **60** | Complete identifiers requiring explicit disposition |

Ten identifiers are outside the legacy graph: `BATTLE_LOST`, `BLE_LOST`, `CPU_TEMP_HIGH`, `GPU_TEMP_HIGH`, `HEART_RATE`, `LINK_DROP`, `NO_IMPROVEMENT`, `PACE_HUNT`, `PIT_LANE` and `PIT_RELEASED`.

The target catalog contains exactly **64 semantic BeatDefinitions**:

| Group | Beats |
| --- | ---: |
| Timing and pace | 12 |
| Battles | 8 |
| Position outcomes | 4 |
| Incidents and recovery | 5 |
| Pit cycle | 6 |
| Stream/session/context | 22 |
| Bio context | 1 |
| Fillers | 6 |
| **Total** | **64** |

The increase above the earlier 46–60 estimate is explained by three missing master event types with speech relevance, six explicit filler situations, stage-specific intro/wrap/in-car guards, semantic splits for sector and incident claims, and one restart beat. It is not wording-driven duplication. The release baseline requires at least four enabled audited EN pattern cards per beat: **256 minimum**, not thousands of pregenerated sentences.

## Identifier disposition

`wire` means the current V4 event type remains unchanged for overlay compatibility. `kind` is the internal NarrativeEvent kind. A dash in Beat means the identifier can never create speech.

| Current identifier | Source/class | v2 disposition | Narrative kind | BeatDefinition(s) | `tape_channel` |
| --- | --- | --- | --- | --- | --- |
| `APPROACH` | graph + wire, temporal | keep wire; normalize internally | `battle.approach` | `battle.approach` | `race.battle.closing` |
| `ATTACK_RANGE` | graph + wire, temporal | keep wire | `battle.attack_range` | `battle.attack_range` | `race.battle.attack` |
| `BACK_UNDER_WAY` | graph, derived lifecycle | keep commentary input | `incident.recovered` | `incident.recovery` | `race.incident.recovery` |
| `BATTLE_FOR_POSITION` | graph + wire, composite | keep wire | `battle.two_front` | `battle.two_front` | `race.battle.two_front` |
| `BATTLE_LOST` | fallback alias only | reject in v2 catalog; migrate fixture to `POSITION_LOST` | — | — | `compat.alias` |
| `BATTLE_WON` | graph + wire, outcome | keep wire | `battle.won` | `battle.won` | `race.battle.outcome` |
| `BLE_LOST` | wire catalog/UI fixture only | visual/operator only | — | — | `system.connectivity` |
| `CLEAN_STREAK` | graph + wire, temporal counter | keep wire | `timing.clean_streak` | `timing.clean_streak` | `race.timing.consistency` |
| `CPU_TEMP_HIGH` | wire catalog only | visual/operator only | — | — | `system.thermal` |
| `ENTER_CAR` | graph, vehicle lifecycle | keep input; route by confirmed stage | `session.enter_car` | `session.enter_car.practice`, `.qualifying`, `.race` | `session.vehicle` |
| `FIELD_FACT` | graph, derived context | keep input | `session.field_fact` | `session.field_fact` | `session.context.field` |
| `FINAL_LAP` | graph + wire, direct edge | keep wire | `session.final_lap` | `session.final_lap` | `race.session.final_lap` |
| `FINISH` | graph + wire, direct result | keep wire | `session.hero_finish` | `session.hero_finish` | `race.session.finish` |
| `GAIN_FOUND` | graph + wire, temporal | keep wire | `timing.pace_gain` | `timing.pace.gain` | `race.timing.delta` |
| `GPU_TEMP_HIGH` | wire catalog only | visual/operator only | — | — | `system.thermal` |
| `HEART_RATE` | fallback alias only | reject; migrate fixture to `HR_PRESSURE_RISING` | — | — | `compat.alias` |
| `HOT_LAP` | graph + wire, temporal | keep wire | `timing.hot_lap` | `timing.lap.hot` | `race.timing.attempt` |
| `HR_PRESSURE_RISING` | graph + wire, temporal bio | keep wire; fact-safe tone only | `bio.pressure_rising` | `bio.pressure` | `bio.pressure` |
| `HUNTED` | graph + wire, temporal | keep wire | `battle.pressure_behind` | `battle.pressure_behind` | `race.battle.pressure` |
| `HUNTING` | graph + wire, temporal | keep wire | `battle.pursuit` | `battle.pursuit` | `race.battle.closing` |
| `INCIDENT` | graph + wire, direct/classified | keep wire; split by explicit branch fact | `incident.occurred` | `incident.off_track`, `incident.unclassified` | `race.incident.event` |
| `INCIDENT_AFTERMATH` | graph, derived lifecycle | keep input | `incident.aftermath` | `incident.aftermath` | `race.incident.aftermath` |
| `INVALID_LAP` | graph + wire, direct result | keep wire | `incident.invalid_lap` | `incident.invalid_lap` | `race.incident.invalid_lap` |
| `LAP_COMPLETE` | graph + wire, direct edge | keep wire | `timing.lap_completed` | `timing.lap.completed` | `race.timing.lap` |
| `LEADER_CHANGE` | graph + wire, direct result | keep wire | `position.leader_change` | `position.leader_change` | `race.position.leader` |
| `LINK_DROP` | wire, connectivity | visual/operator only; never infer race facts | — | — | `system.connectivity` |
| `NO_IMPROVEMENT` | fallback alias only | reject/drop legacy fixture; do not infer a timing result | — | — | `compat.alias` |
| `OVERTAKE` | graph + wire, correlated result | keep wire | `position.pass_completed` | `position.pass` | `race.position.pass` |
| `OVERTAKEN` | graph + fallback alias, not current adapter output | reject as v2 input; migrate to `POSITION_LOST` with cause fact | — | — | `compat.alias` |
| `PACE_HUNT` | emitter only, temporal | keep commentary input | `timing.pace_hunt` | `timing.pace.hunt` | `race.timing.target` |
| `PARADE_PAD` | graph, filler impulse | replace name in internal catalog | `filler.parade_lap` | `filler.parade_lap` | `filler.track_state` |
| `PERSONAL_BEST` | graph + wire, direct result | keep wire | `timing.personal_best` | `timing.lap.personal_best` | `race.timing.lap` |
| `PIT_ENTRY` | graph + wire, lifecycle | keep wire | `pit.entry` | `pit.entry` | `race.pit.cycle` |
| `PIT_EXIT` | graph + wire, lifecycle | keep wire; remove graph-node overlap | `pit.exit` | `pit.exit` | `race.pit.cycle` |
| `PIT_LANE` | wire outside graph, lifecycle | keep wire and add narrative mapping | `pit.lane` | `pit.lane` | `race.pit.cycle` |
| `PIT_OUTCOME` | graph + wire, result | keep wire | `pit.outcome` | `pit.outcome` | `race.pit.outcome` |
| `PIT_RELEASED` | wire outside graph, lifecycle | keep wire and add narrative mapping | `pit.released` | `pit.released` | `race.pit.cycle` |
| `PIT_STOPPED` | graph + wire, lifecycle | keep wire | `pit.stopped` | `pit.stopped` | `race.pit.cycle` |
| `POSITION_ATTACK` | graph + wire, temporal | keep wire | `timing.position_attack` | `timing.position.attack` | `race.timing.attempt` |
| `POSITION_GAINED` | graph + wire, direct result | keep wire | `position.gained` | `position.gained` | `race.position.change` |
| `POSITION_LOST` | graph + wire, direct result | keep wire | `position.lost` | `position.lost` | `race.position.change` |
| `PROJECTED_LAP` | graph + wire, temporal estimate | keep wire; prediction wording tightly constrained | `timing.projected_lap` | `timing.lap.projected` | `race.timing.attempt` |
| `QUALI_RECAP` | graph, session result | keep input | `session.qualifying_recap` | `session.qualifying_recap` | `session.qualifying.recap` |
| `RIVAL_THREAT` | graph + wire, temporal | keep wire | `battle.rival_threat` | `battle.rival_threat` | `race.battle.pressure` |
| `SECTOR_BEST` | graph + wire, direct result | keep wire; split from generic sector beat | `timing.sector_best` | `timing.sector.best` | `race.timing.sector` |
| `SECTOR_SPLIT` | graph + wire, direct edge | keep wire | `timing.sector_split` | `timing.sector.split` | `race.timing.sector` |
| `SESSION_CHECKERED` | graph, lifecycle result | keep input; dedupe with checkered flag branch | `session.checkered` | `session.checkered` | `race.control.flag` |
| `SESSION_FLAG` | graph, direct flag edge | keep input; branch on explicit flag enum | `session.flag_changed` | `session.flag.yellow`, `session.flag.green`, `session.checkered` | `race.control.flag` |
| `SESSION_INTRO_PRACTICE` | graph, lifecycle | replace with stage-routed `SESSION_STARTED` input | `session.started` | `session.intro.practice` | `session.lifecycle` |
| `SESSION_INTRO_QUALIFY` | graph, lifecycle | replace with stage-routed `SESSION_STARTED` input | `session.started` | `session.intro.qualifying` | `session.lifecycle` |
| `SESSION_INTRO_RACE` | graph, lifecycle | replace with stage-routed `SESSION_STARTED` input | `session.started` | `session.intro.race` | `session.lifecycle` |
| `SESSION_PREVIEW` | graph, downstream context | keep internal input | `session.preview_next` | `session.preview.next` | `session.lifecycle` |
| `SESSION_WRAP` | graph, lifecycle/result | replace with stage-routed `SESSION_ENDED` input | `session.ended` | `session.wrap.practice`, `.qualifying`, `.race` | `session.lifecycle` |
| `SIDE_BY_SIDE` | graph + wire, temporal/composite | keep wire | `battle.side_by_side` | `battle.side_by_side` | `race.battle.side_by_side` |
| `SOF_BRIEF` | graph, context | keep internal input | `session.sof_brief` | `session.sof_brief` | `session.context.field` |
| `STREAM_START` | graph, OBS lifecycle | reject from final narrative catalog; adapter emits `STREAM_STARTED` | `stream.started` | `stream.started` | `stream.lifecycle` |
| `TARGET_LOCKED` | graph + wire, temporal | keep wire | `timing.target_locked` | `timing.target.locked` | `race.timing.target` |
| `TIME_LOST` | graph + catalog fallback, temporal | keep wire-compatible input | `timing.pace_loss` | `timing.pace.loss` | `race.timing.delta` |
| `WEATHER_BRIEF` | graph, context | keep internal input | `session.weather_brief` | `session.weather_brief` | `session.context.weather` |
| `WEATHER_CHANGE` | graph, temporal context | keep internal input | `session.weather_changed` | `session.weather_change` | `session.context.weather` |

All 60 rows are terminally classified. Compatibility aliases have no v2 BeatDefinition. Visual/operator-only events may be recorded in their channel but cannot enter EventOpportunityQueue.

### New internal lifecycle event kinds

These are derived NarrativeEvents carried in the same immutable `APPLY_CONTEXT_BATCH` as its TimelineSnapshot and FactView. They are not standalone NarrativeCommands, additions to the V4 overlay EventEnvelope wire, or part of the 60-current-identifier count.

| NarrativeEvent kind | Produced by | Speech routing | `tape_channel` |
| --- | --- | --- | --- |
| `STREAM_STARTED` | debounced BroadcastClock edge/process attach | `stream.started` | `stream.lifecycle` |
| `STREAM_ENDED` | confirmed BroadcastClock inactive edge | no beat; invalidate/close/flush | `stream.lifecycle` |
| `SESSION_STARTED` | new coherent SessionRef occurrence | stage-specific intro | `session.lifecycle` |
| `SESSION_ENDED` | completed/superseded occurrence | stage-specific wrap, qualifying recap, preview when valid | `session.lifecycle` |
| `SESSION_RESTARTED` | same-ref confirmed rewind | `session.restart` plus new occurrence | `session.lifecycle` |

`LONG_SILENCE_ELAPSED`, playback callbacks and other worker/timer inputs remain actor-only NarrativeCommands defined exactly once in `actor-transition-contract.md`. They never enter event taxonomy or EventOpportunity routing directly; any filler opportunity is created by the actor's silence evaluation and uses its selected beat channel.

## Legacy node disposition

Every one of the 54 `sequence_graph.json` nodes has one explicit target. `merge` removes duplicate semantics; `split` is allowed only where claims or hard guards differ.

| Legacy node | Disposition | Target BeatDefinition(s) |
| --- | --- | --- |
| `lap_complete` | keep semantics | `timing.lap.completed` |
| `personal_best` | keep semantics | `timing.lap.personal_best` |
| `gain_found` | keep semantics | `timing.pace.gain` |
| `time_lost` | keep semantics | `timing.pace.loss` |
| `sector_split` | split by event claim | `timing.sector.split`, `timing.sector.best` |
| `target_locked` | keep semantics | `timing.target.locked` |
| `projected_lap` | keep, tighten prediction claim | `timing.lap.projected` |
| `hot_lap` | keep semantics | `timing.lap.hot` |
| `position_attack` | keep semantics | `timing.position.attack` |
| `clean_streak` | keep semantics | `timing.clean_streak` |
| `hunting` | split HUNTING/APPROACH lifecycle meaning | `battle.pursuit`, `battle.approach` |
| `hunted` | keep semantics | `battle.pressure_behind` |
| `two_front_battle` | keep semantics | `battle.two_front` |
| `side_by_side` | keep semantics | `battle.side_by_side` |
| `overtake` | keep semantics | `position.pass` |
| `position_gained` | keep semantics | `position.gained` |
| `position_lost` | keep canonical POSITION_LOST; remove OVERTAKEN alias | `position.lost` |
| `rival_threat` | keep semantics | `battle.rival_threat` |
| `battle_won` | keep semantics | `battle.won` |
| `incident` | merge generic/unknown branch | `incident.unclassified` |
| `invalid_lap` | keep semantics | `incident.invalid_lap` |
| `final_lap` | keep semantics | `session.final_lap` |
| `finish` | keep hero-specific result | `session.hero_finish` |
| `pit_entry` | keep semantics | `pit.entry` |
| `back_on_track` | narrow to correlated pit exit | `pit.exit` |
| `in_car` | remove generic duplicate; unsupported stage stays silent | — |
| `stream_start` | rename internal lifecycle event | `stream.started` |
| `in_car_practice` | keep stage guard | `session.enter_car.practice` |
| `in_car_qualify` | keep stage guard | `session.enter_car.qualifying` |
| `in_car_race` | keep stage guard | `session.enter_car.race` |
| `pit_outcome` | remove PIT_EXIT overlap; retain outcome only | `pit.outcome` |
| `hr_pressure` | keep fact-safe semantics | `bio.pressure` |
| `session_intro_practice` | map to canonical session start | `session.intro.practice` |
| `session_intro_qualify` | map to canonical session start | `session.intro.qualifying` |
| `session_intro_race` | map to canonical session start | `session.intro.race` |
| `sof_brief` | keep context | `session.sof_brief` |
| `weather_brief` | keep context | `session.weather_brief` |
| `attack_range` | keep semantics | `battle.attack_range` |
| `pit_stopped` | keep semantics | `pit.stopped` |
| `incident_aftermath` | keep semantics | `incident.aftermath` |
| `back_under_way` | keep closure | `incident.recovery` |
| `leader_change` | keep semantics | `position.leader_change` |
| `session_wrap` | split by stage-specific facts/guards | `session.wrap.practice`, `.qualifying`, `.race` |
| `session_preview` | keep bridge semantics | `session.preview.next` |
| `session_checkered` | merge duplicate checkered claim | `session.checkered` |
| `field_fact` | keep context | `session.field_fact` |
| `weather_change` | keep material update | `session.weather_change` |
| `incident_off_track` | keep classified branch | `incident.off_track` |
| `incident_unknown` | merge with generic unclassified incident | `incident.unclassified` |
| `session_flag_yellow` | keep branch | `session.flag.yellow` |
| `session_flag_green` | keep branch | `session.flag.green` |
| `session_flag_checkered` | merge duplicate checkered claim | `session.checkered` |
| `quali_recap` | keep result | `session.qualifying_recap` |
| `parade_pad` | replace padding semantics with factual filler | `filler.parade_lap` |

## Frozen policy profiles

Values are initial, versioned estimates. Tuning may alter a value within its frozen range without changing the identity or lifecycle contract.

| Profile | Base priority | Urgency | TTL | Penalty coefficient | Cadence scope / minimum | Typical use |
| --- | ---: | --- | ---: | ---: | --- | --- |
| `critical` | 90 | `critical` | 45 s | 0.25 | once per semantic outcome revision | finish, checkered, severe lifecycle outcome |
| `result` | 78 | `story` | 30 s | 0.50 | semantic identity / 8 s | pass, position/pit/incident outcome, wrap |
| `live_story` | 64 | `story` | 10 s | 0.80 | episode / 8 s | battle, pit lifecycle, active attempt |
| `transient` | 56 | `story` | 6 s | 1.00 | semantic identity / 12 s | short gap/sector/flag updates |
| `context` | 46 | `context` | 20 s | 1.00 | `tape_channel` / 45 s | field, weather, bio, session context |
| `filler` | 24 | `background` | 12 s | 1.40 | silence impulse / `long_silence_s` | long-silence track-state beat |

All numeric fields are finite. Priority range is 0–100, TTL range is 1–120 seconds, cadence range is 0–300 seconds and penalty coefficient range is 0–4. `selection_threshold=35`, `switch_margin=8` and global playback-acceptance interval 4 seconds are initial director estimates. Global cadence is start-to-start; profile cadence uses the scope shown and both must pass. Against a focused continuation, any higher-urgency challenger switches; only when none exists may an equal/lower-urgency challenger switch by reaching the inclusive score margin. Filler is considered only when no event/story/episode candidate is selectable.

Beat channels are explicit catalog values. The complete compact mapping is:

- `timing.lap.{completed,personal_best}` → `race.timing.lap`; `timing.pace.{gain,loss}` → `race.timing.delta`; `timing.sector.*` → `race.timing.sector`;
- `timing.{target.locked,pace.hunt}` → `race.timing.target`; `timing.{lap.projected,lap.hot,position.attack}` → `race.timing.attempt`; `timing.clean_streak` → `race.timing.consistency`;
- `battle.{pursuit,approach}` → `race.battle.closing`; `battle.attack_range` → `race.battle.attack`; `battle.side_by_side` → `race.battle.side_by_side`; `battle.{pressure_behind,rival_threat}` → `race.battle.pressure`; `battle.two_front` → `race.battle.two_front`; `battle.won` → `race.battle.outcome`;
- `position.pass` → `race.position.pass`; `position.{gained,lost}` → `race.position.change`; `position.leader_change` → `race.position.leader`;
- `incident.{off_track,unclassified}` → `race.incident.event`; `incident.invalid_lap` → `race.incident.invalid_lap`; `incident.aftermath` → `race.incident.aftermath`; `incident.recovery` → `race.incident.recovery`;
- `pit.{entry,lane,stopped,released,exit}` → `race.pit.cycle`; `pit.outcome` → `race.pit.outcome`;
- `stream.started` → `stream.lifecycle`; all `session.intro.*`, `session.restart`, `session.wrap.*`, `session.preview.next` and `session.enter_car.*` → `session.lifecycle` except the context/result overrides below;
- `session.checkered` and `session.flag.{yellow,green}` → `race.control.flag`; `session.final_lap` → `race.session.final_lap`; `session.hero_finish` → `race.session.finish`; `session.qualifying_recap` → `session.qualifying.recap`; `session.{sof_brief,field_fact}` → `session.context.field`; `session.{weather_brief,weather_change}` → `session.context.weather`;
- `bio.pressure` → `bio.pressure`; every `filler.*` beat → `filler.track_state`.

The lifecycle command that caused a filler evaluation remains on `filler.lifecycle`; the resulting opportunity and speech exposure use the selected beat's `filler.track_state` channel.

## Story templates and terminal contracts

| Story | Correlation identity | Opens | Updates | Closes | Natural successor order | Max consecutive non-closing | Story cadence |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| `timing_attempt` | occurrence + lap/attempt | hot lap, gain/target | projection, attack, sector | lap complete, invalid lap, restart | hot → projection/target → sector → lap result | 2 | 8 s |
| `battle_ahead` | occurrence + hero + target + relation epoch | pursuit | approach, attack range, side-by-side | pass, battle won, target change, exit hysteresis, reset | pursuit → approach → attack range → side-by-side → outcome | 3 | 8 s |
| `battle_behind` | occurrence + hero + target + relation epoch | pressure/rival threat | material pressure band | position lost, target change, exit hysteresis, reset | pressure → rival threat/two-front → loss or closure | 2 | 8 s |
| `battle_two_front` | occurrence + hero + front/rear targets + both relation epochs | composite predicate enter | material front/rear band | either identity changes or composite exits | two-front → side-by-side/pass/loss when correlated | 2 | 8 s |
| `pit_cycle` | occurrence + pit-cycle ordinal | entry | lane, stopped, released, exit | outcome, reset | entry → lane → stopped? → released? → exit → outcome | 3 | 8 s |
| `incident` | occurrence + incident ordinal | classified incident | aftermath | recovered, session/reset | incident → aftermath/invalid-lap → recovery | 2 | 8 s |
| `session_occurrence` | occurrence ID | session started/restarted | context, flags, final lap | session ended/superseded | intro/restart → context → checkered/finish → wrap → preview | 3 | 8 s |
| `stream_lifecycle` | narrative `streamEpoch` under one `broadcastEpoch` | narrative run started | none | OBS stream end/commentary disable/process shutdown | stream opening only | 1 | 0 s |
| `bio_pressure` | occurrence + hero + sensor epoch | pressure enter | material band revision | clear/stale/reset | pressure context or silence | 1 | 0 s |
| `single_result` | occurrence + accepted event ID | self-contained accepted result/context event | never | consumed, superseded, invalid or TTL | none; may also close a correlated story | 1 | 0 s |
| `filler_single` | silence impulse ID + scope; occurrence normally, stream only for pre-session lobby | long silence + one valid fact set | never | selected, invalid or TTL | none | 1 | 0 s |

Question marks mean an optional lifecycle state, not a non-deterministic edge. Every edge between occurrence-scoped episodes additionally requires matching occurrence/lineage and its listed correlation identity; the stream-opening edges bind the current confirmed occurrence named by their guard. A terminal event may produce a self-contained result beat even if its opening beat was never spoken.

Episode routing is deterministic and ordered:

1. attach to an active episode with exact allowed correlation identity;
2. otherwise attach to an allowed composite episode containing the same participant/relation epochs;
3. otherwise open the NarrativeEvent kind's declared story template;
4. a catalog-marked self-contained terminal/context event may open `single_result` if no correlated episode exists;
5. otherwise record `no_episode_route` and create no opportunity.

An event may therefore declare more than one ordered route, but the router chooses exactly one episode instance. For example, `position.pass` closes a matching `battle_ahead`; without that correlation it becomes a self-contained `single_result`. Embeddings and LLM output never participate in routing.

## Natural successor edges

These edges create candidates only while the target beat's required claims and hard context remain true. Event-triggered beats do not require an incoming edge. `preferred` is a score bonus, not a lock; normal director arbitration still applies.

| From | To | Additional guard | Edge policy |
| --- | --- | --- | --- |
| `stream.started` | `session.intro.practice` | current confirmed practice occurrence | preferred, non-closing |
| `stream.started` | `session.intro.qualifying` | current confirmed qualifying occurrence | preferred, non-closing |
| `stream.started` | `session.intro.race` | current confirmed race occurrence | preferred, non-closing |
| `timing.lap.hot` | `timing.lap.projected` | same attempt revision; projection valid | preferred, non-closing |
| `timing.lap.hot` | `timing.target.locked` | same attempt; target valid | allowed, non-closing |
| `timing.lap.projected` | `timing.position.attack` | same attempt; qualifying position target | preferred, non-closing |
| `timing.target.locked` | `timing.pace.gain` | same attempt; material gain | allowed, non-closing |
| `timing.target.locked` | `timing.pace.loss` | same attempt; material loss | allowed, non-closing |
| `timing.sector.split` | `timing.sector.best` | same sector result explicitly best | preferred, non-closing |
| `timing.lap.projected` | `timing.lap.completed` | same lap completed | preferred, closing |
| `timing.target.locked` | `timing.lap.completed` | same lap completed | allowed, closing |
| `timing.lap.hot` | `incident.invalid_lap` | same attempt invalidated | preferred, closing |
| `battle.pursuit` | `battle.approach` | same target/relation; approach claims true | preferred, non-closing |
| `battle.pursuit` | `battle.two_front` | same front relation plus valid rear relation | allowed, non-closing |
| `battle.approach` | `battle.attack_range` | same target/relation; attack band true | preferred, non-closing |
| `battle.attack_range` | `battle.side_by_side` | same target/relation; overlap true | preferred, non-closing |
| `battle.pursuit` | `position.pass` | same target; ordered pass result | allowed, closing |
| `battle.approach` | `position.pass` | same target; ordered pass result | preferred, closing |
| `battle.attack_range` | `position.pass` | same target; ordered pass result | preferred, closing |
| `battle.side_by_side` | `position.pass` | same target; ordered pass result | preferred, closing |
| `battle.side_by_side` | `battle.won` | same target; battle outcome without pass claim | allowed, closing |
| `battle.pressure_behind` | `battle.rival_threat` | same rear target/relation; threat claims true | preferred, non-closing |
| `battle.pressure_behind` | `battle.two_front` | same rear relation plus valid front relation | allowed, non-closing |
| `battle.rival_threat` | `position.lost` | correlated position-loss result | preferred, closing |
| `battle.two_front` | `battle.side_by_side` | one declared relation becomes overlap | allowed, non-closing |
| `battle.two_front` | `position.pass` | correlated front relation result | allowed, closing |
| `battle.two_front` | `position.lost` | correlated rear relation result | allowed, closing |
| `pit.entry` | `pit.lane` | same pit cycle; lane fact active | preferred, non-closing |
| `pit.lane` | `pit.stopped` | same pit cycle; stopped fact active | preferred, non-closing |
| `pit.lane` | `pit.released` | same cycle; no stop observed; released fact active | allowed, non-closing |
| `pit.stopped` | `pit.released` | same pit cycle; released fact active | preferred, non-closing |
| `pit.released` | `pit.exit` | same pit cycle; exit fact active | preferred, non-closing |
| `pit.lane` | `pit.exit` | same cycle; exit without observed stop/release | allowed, non-closing |
| `pit.exit` | `pit.outcome` | same cycle; comparison fact valid | preferred, closing |
| `incident.off_track` | `incident.aftermath` | same incident; aftermath revision valid | preferred, non-closing |
| `incident.unclassified` | `incident.aftermath` | same incident; aftermath revision valid | allowed, non-closing |
| `incident.off_track` | `incident.invalid_lap` | same occurrence/lap; invalid result | allowed, non-closing |
| `incident.aftermath` | `incident.recovery` | same incident; recovery evidence valid | preferred, closing |
| `session.final_lap` | `session.checkered` | same race occurrence; checkered active | allowed, non-closing |
| `session.final_lap` | `session.hero_finish` | same race occurrence; hero finished | preferred, closing |
| `session.checkered` | `session.hero_finish` | same occurrence; hero finish observed | preferred, closing |
| `session.checkered` | `session.wrap.race` | same occurrence ended; finish may be unknown | allowed, closing |
| `session.intro.practice` | `session.sof_brief` | same occurrence; fact fresh and not exposed | allowed, non-closing |
| `session.intro.practice` | `session.weather_brief` | same occurrence; fact fresh and not exposed | allowed, non-closing |
| `session.intro.qualifying` | `session.weather_brief` | same occurrence; fact fresh and not exposed | allowed, non-closing |
| `session.intro.race` | `session.sof_brief` | same occurrence; fact fresh and not exposed | allowed, non-closing |
| `session.intro.race` | `session.weather_brief` | same occurrence; fact fresh and not exposed | allowed, non-closing |
| `session.wrap.practice` | `session.preview.next` | next present stage known | preferred, closing |
| `session.wrap.qualifying` | `session.qualifying_recap` | qualifying result facts valid | preferred, non-closing |
| `session.qualifying_recap` | `session.preview.next` | next present stage known | preferred, closing |

No other natural successor edge exists in v2 baseline. In particular, filler, bio, field/weather update, flags, standalone position results and single-result beats have no implicit continuation. They may be followed only through a new event/silence opportunity and normal arbitration.

### Frozen successor evaluation

The table above is a closed 50-edge set. An implementation cannot infer another edge from matching groups, stories, predicates, embeddings or realization text. Each director pass expands only the edges whose `from` beat is the last playback-accepted beat. It then applies, in order:

1. the same active narrative `streamEpoch`;
2. the edge's exact typed correlation bindings and positive/negative fact conditions;
3. the target BeatDefinition's required claims and hard context, where `unknown` is ineligible;
4. half-open fact/opportunity validity and not-already-exposed material identity;
5. the maximum of global, policy and StoryDefinition cadence;
6. the minimum of public and StoryDefinition consecutive-beat caps for non-closing edges.

A closing edge bypasses only the consecutive non-closing cap. It does not mutate or resolve episode truth when selected or spoken: the accepted event/fact/lifecycle reducer already owns that transition. Closing permits a still-valid outcome realization from the matching resolved identity. If no edge remains eligible, the director returns to ordinary event/episode/filler arbitration; it never waits on or manufactures a successor.

Successor scoring is frozen as `58 continuation base + 6 same-story continuity + edge bonus + 6 material revision`, before the already-defined fatigue/penalty terms. `preferred` contributes 6 and `allowed` contributes 0. Preference is only a score term; it is not a traversal lock and cannot bypass a hard guard, a higher-urgency challenger or the inclusive `switch_margin` rule. An event and successor route producing the same `(beatId, episodeId, materialRevision)` are one deduplicated candidate.

The generated projection contains 64 nodes and 50 edges: 28 preferred, 22 allowed, 18 closing and 32 non-closing. Thirty-six nodes have no implicit continuation. The graph is a DAG with 64 singleton strongly connected components, so there is no cyclic story walk; validity, cadence, exposure identity and story caps remain mandatory barriers even if a future schema version intentionally introduces a cycle.

## Beat inventory

The table is the authoritative 64-beat design baseline. `on_track` means normalized broadcast context, never a raw OBS scene name. `any-stage` means any confirmed supported stage.

| BeatDefinition | Story/role | Policy | Hard context | Opens from / closes on |
| --- | --- | --- | --- | --- |
| `timing.lap.completed` | timing/result | `result` | any-stage; completed lap fact | lap edge / self-contained terminal |
| `timing.lap.personal_best` | timing/result | `result` | any-stage; PB comparison valid | PB edge / self-contained terminal |
| `timing.pace.gain` | timing/update | `transient` | practice or qualifying; valid delta | material gain / lap/reset |
| `timing.pace.loss` | timing/update | `transient` | practice or qualifying; valid delta | material loss / lap/reset |
| `timing.sector.split` | timing/update | `transient` | any-stage; sector identity | sector edge / next sector/lap |
| `timing.sector.best` | timing/result | `result` | any-stage; comparison provenance | sector-best edge / self-contained |
| `timing.target.locked` | timing/update | `live_story` | practice or qualifying; stable target | target edge / target/lap/reset |
| `timing.lap.projected` | timing/update | `live_story` | practice or qualifying; estimate quality | projection band / lap/reset |
| `timing.lap.hot` | timing/opening | `live_story` | practice or qualifying; valid attempt | hot-lap enter / lap/invalid/reset |
| `timing.position.attack` | timing/update | `live_story` | qualifying; target position fact | attack band / lap/reset |
| `timing.clean_streak` | timing/context | `context` | any-stage; completed clean-lap count | material count / incident/reset |
| `timing.pace.hunt` | timing/context | `context` | practice or qualifying; stable target | target band / target/lap/reset |
| `battle.pursuit` | battle/opening | `live_story` | race, racing, green, on_track preferred | closing enter / battle close |
| `battle.approach` | battle/update | `live_story` | race, same target, on_track preferred | approach band / battle close |
| `battle.attack_range` | battle/escalation | `live_story` | race, same target, on_track preferred | attack band / battle close |
| `battle.side_by_side` | battle/climax | `critical` | race, same target, on_track | overlap enter / separation/outcome |
| `battle.pressure_behind` | battle/opening | `live_story` | race, stable rear target, green | pressure enter / rear battle close |
| `battle.rival_threat` | battle/escalation | `live_story` | race, position-at-risk fact | threat enter / loss/clear |
| `battle.two_front` | battle/composite | `live_story` | race, stable front and rear identities | composite enter / identity/exit |
| `battle.won` | battle/outcome | `result` | race; correlated outcome evidence | result / self-contained terminal |
| `position.pass` | position/outcome | `critical` | race; ordered actor/target evidence | pass result / terminal |
| `position.gained` | position/result | `result` | race; old/new position | change result / terminal |
| `position.lost` | position/result | `result` | race; old/new position | change result / terminal |
| `position.leader_change` | position/result | `result` | race; leader identity evidence | leader edge / terminal |
| `incident.off_track` | incident/opening | `result` | any-stage; explicit off-track branch | incident edge / recovery/reset |
| `incident.unclassified` | incident/opening | `result` | any-stage; branch unknown, no invented cause | incident edge / recovery/reset |
| `incident.invalid_lap` | incident/result | `result` | practice or qualifying; invalid fact | invalid edge / next attempt/reset |
| `incident.aftermath` | incident/update | `context` | same incident; stable aftermath fact | aftermath edge / recovery/reset |
| `incident.recovery` | incident/closure | `result` | same incident; moving/on-track evidence | recovery edge / terminal |
| `pit.entry` | pit/opening | `live_story` | any-stage; pit entry edge | entry / outcome/reset |
| `pit.lane` | pit/update | `live_story` | same pit cycle; in-lane fact | lane enter / exit/reset |
| `pit.stopped` | pit/update | `live_story` | same pit cycle; stopped evidence | stopped / release/exit |
| `pit.released` | pit/update | `live_story` | same pit cycle; moving evidence | release / exit/reset |
| `pit.exit` | pit/closure | `result` | same pit cycle; pit-exit edge | exit / outcome or terminal |
| `pit.outcome` | pit/outcome | `result` | same pit cycle; entry/exit comparison | outcome result / terminal |
| `stream.started` | stream/opening | `critical` | new narrative `streamEpoch` bound to confirmed active `broadcastEpoch` | STREAM_STARTED / OBS end, commentary disable or shutdown |
| `session.intro.practice` | session/opening | `context` | practice occurrence | SESSION_STARTED / occurrence end |
| `session.intro.qualifying` | session/opening | `context` | qualifying occurrence | SESSION_STARTED / occurrence end |
| `session.intro.race` | session/opening | `context` | race occurrence | SESSION_STARTED / occurrence end |
| `session.restart` | session/opening | `result` | confirmed same-ref rewind | SESSION_RESTARTED / new occurrence end |
| `session.wrap.practice` | session/closure | `result` | completed/superseded practice facts | SESSION_ENDED / terminal |
| `session.wrap.qualifying` | session/closure | `result` | completed/superseded qualifying facts | SESSION_ENDED / terminal |
| `session.wrap.race` | session/closure | `result` | completed/superseded race facts | SESSION_ENDED / terminal |
| `session.preview.next` | session/bridge | `context` | next present stage known | prior wrap / next session start |
| `session.checkered` | session/outcome | `critical` | explicit checkered evidence | flag/session edge / occurrence end |
| `session.final_lap` | session/escalation | `critical` | race; final-lap identity | final-lap edge / finish/reset |
| `session.hero_finish` | session/outcome | `critical` | race; hero finish position | FINISH / terminal |
| `session.qualifying_recap` | session/outcome | `result` | qualifying completed facts | qualifying end / terminal |
| `session.sof_brief` | session/context | `context` | confirmed field/SoF facts | intro/silence / occurrence end |
| `session.weather_brief` | session/context | `context` | confirmed weather facts | intro/silence / superseded |
| `session.weather_change` | session/update | `context` | material weather revision | weather edge / superseded |
| `session.field_fact` | session/context | `context` | confirmed field fact revision | intro/silence / superseded |
| `session.flag.yellow` | session/control | `critical` | race; explicit yellow flag | flag edge / green/checkered |
| `session.flag.green` | session/control | `critical` | race; explicit green after non-green | flag edge / yellow/checkered |
| `session.enter_car.practice` | session/vehicle | `context` | practice + enter-car edge | ENTER_CAR / exit/reset |
| `session.enter_car.qualifying` | session/vehicle | `context` | qualifying + enter-car edge | ENTER_CAR / exit/reset |
| `session.enter_car.race` | session/vehicle | `context` | race + enter-car edge | ENTER_CAR / exit/reset |
| `bio.pressure` | bio/context | `context` | fresh HR evidence; no medical/cause claim | material HR state / clear/reset |
| `filler.out_lap` | filler/single | `filler` | long silence + out-lap + fresh facts | silence impulse / selected or invalid |
| `filler.in_lap` | filler/single | `filler` | long silence + in-lap + fresh facts | silence impulse / selected or invalid |
| `filler.parade_lap` | filler/single | `filler` | long silence/parade impulse + parade fact | impulse / selected or invalid |
| `filler.garage` | filler/single | `filler` | long silence + garage context + fresh fact | silence impulse / selected or invalid |
| `filler.lobby` | filler/single | `filler` | long silence + lobby context + fresh fact; stream form only with track identity | silence impulse / selected or invalid |
| `filler.quiet_track` | filler/single | `filler` | long silence + on-track + no live race opportunity | silence impulse / selected or invalid |

## Claim and realization mapping

Every row inherits global contract `G0`: only bound EN names/numbers/units may be emitted; unbound cause, intent, emotion, certainty, future outcome, weather and medical interpretation are forbidden. “Forbidden addition” below extends `G0`. Optional claims must be selected into BeatPlan before generation. Predicate IDs and allowed attributes below are canonical and resolve through [the fact/feature registry](fact-feature-registry.md); `W_weather`, `W_field`, `W_filler_phase`, `W_filler_off_track` and `W_quiet_track` mean exactly the closed allowlists defined there, not free text selection.

Each BeatDefinition realization block is exactly `{family,backend,maxFreedom}` where backend is `authored|qwen_compiled` and freedom order is `tight < balanced < loose`. Each realization-family registry row is exactly `{family,promotedMaxFreedom,preferredFreedom,balancedAllowClauseReorder,looseAllowClauseReorder,enabledPatternCardIds}` in addition to its verifier grammar reference. Preferred cannot exceed promoted; a non-tight profile needs at least two enabled audited cards. The release baseline has `promotedMaxFreedom=tight` for every family. These fields are mandatory even for authored beats so audit/selection has one shape; authored rendering ignores sampling but its card still validates against the tight semantic contract.

| BeatDefinition | Required claims | Forbidden addition | Realization family |
| --- | --- | --- | --- |
| `timing.lap.completed` | `timing.lap_completed(hero; lap[, lapTime])` | PB or pace judgement without comparison fact | `timing.lap_result` |
| `timing.lap.personal_best` | `timing.personal_best(hero; lapTime, referenceTime, improvement)` | session/field best unless explicitly bound | `timing.lap_result` |
| `timing.pace.gain` | `timing.delta_improved(hero; delta, referenceId, segmentId)` | completed result or guaranteed target | `timing.delta` |
| `timing.pace.loss` | `timing.delta_worsened(hero; delta, referenceId, segmentId)` | cause of loss | `timing.delta` |
| `timing.sector.split` | `timing.sector_completed(hero; sectorId, segmentTime[, delta])` | sector-best claim | `timing.sector` |
| `timing.sector.best` | `timing.sector_best(hero; sectorId, segmentTime, referenceTime, improvement)` | lap/PB claim | `timing.sector` |
| `timing.target.locked` | `timing.target_locked(hero; targetPosition, gap, referenceId)` | achievement or prediction certainty | `timing.target` |
| `timing.lap.projected` | `timing.lap_projection(hero; projectedTime, estimatorVersion, quality)` | completed result; certainty wording | `timing.projection` |
| `timing.lap.hot` | `timing.active_attempt(hero; attemptId)` | eventual result | `timing.attempt` |
| `timing.position.attack` | `timing.position_projection(hero; targetPosition, projectedTime, referenceTime)` | actual position gained | `timing.projection` |
| `timing.clean_streak` | `timing.clean_lap_streak(hero; count)` | whole-session incident-free claim | `timing.consistency` |
| `timing.pace.hunt` | `timing.pace_target(hero; targetPosition, gap, referenceId)` | pass/position outcome | `timing.target` |
| `battle.pursuit` | `battle.closing(hero→target; gap, netClosing, slope, targetEpoch)` | side-by-side/pass certainty | `battle.closing` |
| `battle.approach` | `battle.approaching(hero→target; materialBand, gap, targetEpoch)` | contact/pass/outcome | `battle.closing` |
| `battle.attack_range` | `battle.attack_range(hero→target; gapBand, gap, targetEpoch)` | pass completed | `battle.attack` |
| `battle.side_by_side` | `battle.side_by_side(hero→target; relationEpoch)` | winner/outcome before result | `battle.overlap` |
| `battle.pressure_behind` | `battle.closing(target→hero; gap, netClosing, slope, targetEpoch)` | reverse actor roles; inevitable loss | `battle.pressure` |
| `battle.rival_threat` | `battle.position_threat(target→hero; positionAtRisk, relationEpoch)` | overtake already completed | `battle.pressure` |
| `battle.two_front` | `battle.closing(hero→front; …)` + `battle.closing(rear→hero; …)` | collapsing actors into one target | `battle.two_front` |
| `battle.won` | `battle.outcome(hero→target; outcome=won, relationEpoch)` | pass mechanism unless evidenced | `battle.outcome` |
| `position.pass` | `position.passed(hero→target; oldPasserPosition, newPasserPosition, oldTargetPosition, newTargetPosition)` | contact/cause; leader claim unless bound | `position.pass` |
| `position.gained` | `position.changed(hero; oldPosition, newPosition, direction=gained)` | named passed target unless evidenced | `position.change` |
| `position.lost` | `position.changed(hero; oldPosition, newPosition, direction=lost)` | named overtaker/cause unless evidenced | `position.change` |
| `position.leader_change` | `position.leader_changed(oldLeader→newLeader; oldCarId, newCarId)` | hero involvement unless bound | `position.leader` |
| `incident.off_track` | `incident.occurred(hero; incidentOrdinal, incidentDelta)` + `incident.off_track(hero; incidentOrdinal, surface)` | cause, damage or blame | `incident.event` |
| `incident.unclassified` | `incident.occurred(hero; incidentOrdinal, incidentDelta)` | off-track/contact/damage classification | `incident.event` |
| `incident.invalid_lap` | `incident.lap_invalid(hero; lap, attemptId)` | incident cause unless bound | `incident.invalid_lap` |
| `incident.aftermath` | `incident.state(hero; incidentOrdinal, state)` | recovery or damage outcome | `incident.aftermath` |
| `incident.recovery` | `incident.recovered_motion(hero; incidentOrdinal, heldFor)` + `vehicle.surface(hero; surface=on_track)` | “no damage” or full recovery claim | `incident.recovery` |
| `pit.entry` | `pit.phase(hero; phase=entry, cycleOrdinal)` | strategy reason | `pit.lifecycle` |
| `pit.lane` | `pit.phase(hero; phase=lane, cycleOrdinal)` | stop/release outcome | `pit.lifecycle` |
| `pit.stopped` | `pit.phase(hero; phase=stopped, cycleOrdinal)` | service performed unless bound | `pit.lifecycle` |
| `pit.released` | `pit.phase(hero; phase=released, cycleOrdinal)` | pit exit completed | `pit.lifecycle` |
| `pit.exit` | `pit.phase(hero; phase=exit, cycleOrdinal)` | position gain/loss without comparison | `pit.lifecycle` |
| `pit.outcome` | `pit.outcome(hero; cycleOrdinal, entryPosition, exitPosition, positionDelta, direction)` | strategy/cause judgement | `pit.outcome` |
| `stream.started` | `stream.started(startReason)` with common `broadcastEpoch`/`streamEpoch` | prior stream/session history when incomplete | `stream.lifecycle` |
| `session.intro.practice` | `session.started(stage=practice, startReason)` | qualifying/race facts as current | `session.intro` |
| `session.intro.qualifying` | `session.started(stage=qualifying, startReason)` | practice/race facts as current | `session.intro` |
| `session.intro.race` | `session.started(stage=race, startReason)` | practice/quali facts unless inherited and marked past | `session.intro` |
| `session.restart` | `session.restarted(stage, predecessorOccurrenceId)` | claim that stream restarted | `session.restart` |
| `session.wrap.practice` | `session.ended(stage=practice, reason)` | unsupported result facts | `session.wrap` |
| `session.wrap.qualifying` | `session.ended(stage=qualifying, reason)` | race outcome; unbound grid position | `session.wrap` |
| `session.wrap.race` | `session.ended(stage=race, reason)` | hero finish if not observed | `session.wrap` |
| `session.preview.next` | `session.next_present_stage(stage, sourceSubSessionId, sourceSessionNum)` | absent/skipped stage; scheduled certainty | `session.preview` |
| `session.checkered` | `race.checkered_active()` | hero finished or final position | `session.flag` |
| `session.final_lap` | `race.final_lap(hero; lap)` | finish result | `session.final_lap` |
| `session.hero_finish` | `race.hero_finished(hero; position[, classPosition, classificationStatus])` | official classification | `session.finish` |
| `session.qualifying_recap` | `session.qualifying_result(hero; position[, bestLapTime])` | race/grid certainty not evidenced | `session.recap` |
| `session.sof_brief` | `field.strength(value, fieldScope, sampleCount, official)` | quality judgement or result prediction | `session.context` |
| `session.weather_brief` | `W_weather` | forecast/cause; dry→sunny inference | `session.weather` |
| `session.weather_change` | `weather.changed(metric, oldFactId, newFactId, materialRevision)` + referenced new weather fact | unobserved track effect | `session.weather` |
| `session.field_fact` | `W_field` | extrapolation beyond selected fact | `session.context` |
| `session.flag.yellow` | `race.flag_changed(flag=yellow, scope)` | cause/incident identity unless bound | `session.flag` |
| `session.flag.green` | `race.flag_changed(flag=green, scope)` | “race start” unless start transition bound | `session.flag` |
| `session.enter_car.practice` | `vehicle.entered_car(hero; stage=practice)` | lap/pace outcome | `session.vehicle` |
| `session.enter_car.qualifying` | `vehicle.entered_car(hero; stage=qualifying)` | valid attempt/result before observed | `session.vehicle` |
| `session.enter_car.race` | `vehicle.entered_car(hero; stage=race)` | green/start state unless bound | `session.vehicle` |
| `bio.pressure` | `bio.hr_state(hero; band, bpm, sampleAge, sensorEpoch)` | medical, emotion, cause or performance claim | `bio.context` |
| `filler.out_lap` | `vehicle.phase(hero; phase=out_lap)` + `W_filler_phase` | hot-lap/result prediction | `filler.track_state` |
| `filler.in_lap` | `vehicle.phase(hero; phase=in_lap)` + `W_filler_phase` | pit intent unless bound | `filler.track_state` |
| `filler.parade_lap` | `vehicle.phase(hero; phase=parade_lap)` + `W_filler_phase` | green/race-start timing prediction | `filler.track_state` |
| `filler.garage` | `broadcast.context(context=garage)` + `W_filler_off_track` | on-track action | `filler.off_track` |
| `filler.lobby` | `broadcast.context(context=lobby)` + `W_filler_off_track` | active session action | `filler.off_track` |
| `filler.quiet_track` | `broadcast.context(context=on_track)` + `W_quiet_track` | fabricated race event or urgency | `filler.track_state` |

## Trigger and tuning ownership

| Beat/event group | Trigger type | Default tuning policy | Exposed parameter families |
| --- | --- | --- | --- |
| lap/sector/position/pit/session edges | direct/lifecycle | `none` | debounce/identity only; no sport threshold |
| pursuit/approach/pressure/threat | temporal | `optional` after promotion | window, min net change, slope, coverage, confirm/clear hysteresis |
| side-by-side/two-front | composite | `optional` after promotion | identity stability, overlap/gap bands, confirmation |
| projected/hot/target/pace/clean streak | temporal | `optional` | material bands, minimum samples/coverage, cadence |
| incident classification/aftermath/recovery | direct + temporal | `optional` | classification confidence, stable movement/on-track windows |
| HR pressure | temporal | `optional` | freshness, baseline window, enter/exit band; no medical inference |
| filler | silence lifecycle + composite guards | `none` | global `long_silence_s`; catalog TTL/cadence only |

During branch calibration, a changed temporal/composite detector may be marked `experimental=true, tuning.required`. It must be promoted to `optional` or `none` before the final release catalog.

## Machine-checkable closure requirements

The exact beat projection is generated as `machine/beat-catalog.json` with its Draft 2020-12 schema, invalid-mutation fixtures and standard-library checker. It cross-validates all 64 beat IDs against the 57-predicate/five-allowlist fact registry, all 37 realization families, six policies and 36 `tape_channel` values. Required predicates retain actor direction, exact claim cardinality, required/optional attributes and literal enum constraints; per-beat forbidden additions remain exact catalog strings under the closed global forbidden-claim list. Replaced `STREAM_START`, `SESSION_INTRO_*` and `SESSION_WRAP` identifiers are disposition/migration evidence only and cannot appear as v2 beat triggers; the canonical lifecycle kinds are used instead.

Four audited EN cards per beat are materialized in `machine/realization-pattern-cards.json` (256 enabled cards). The 50 natural successor edges and SCC/dead-end proof are materialized in `machine/successor-graph.json`; `machine/catalog-loader-contract.json` and its mutation goldens freeze the checks that the later production loader must reproduce. `irswitch.contracts.coverage_matrix.audit_coverage_matrix` is the implementation-time CI proof for issue #256; `tests/test_coverage_matrix.py` executes it.

`irswitch.contracts.coverage_matrix.audit_coverage_matrix` (via `tests/test_coverage_matrix.py`) proves:

- exactly 60 current identifiers appear once in the disposition table;
- every identifier is one of speakable, visual/operator-only or compatibility alias;
- every speakable row resolves to at least one of exactly 64 BeatDefinitions;
- every BeatDefinition resolves to at least one ordered story route, one realization family, one policy profile and one valid `tape_channel`;
- every BeatDefinition/family resolves the closed realization block, valid freedom ordering and sufficient enabled pattern-card pool;
- aliases and visual-only events can never create EventOpportunity;
- every successor reference exists and every nonterminal SCC has an exit, TTL/cadence barrier and material-revision guard;
- every stage-specific beat uses the normalized stage/context enums and no raw OBS scene name.
