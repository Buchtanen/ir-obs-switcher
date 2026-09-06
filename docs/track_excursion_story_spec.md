# Track excursion story — scenario taxonomy and commentary contract

**Status:** proposed product and detection contract; no runtime behavior changed by this document

Current implementation: [active development subset](track_excursion_live_test.md). The broader
taxonomy below is not a claim that all causes, pace, repairs or reset recognition are implemented.

**Baseline:** `codex/fix-overlay-commentary-test-7` @ `4497040`

**Scenario definition:**
[`docs/scenarios/track_excursion_story_v1.json`](scenarios/track_excursion_story_v1.json)

**Scenario engine:** [race_scenario_engine_spec.md](race_scenario_engine_spec.md)

**Consolidated delivery plan:**
[track_excursion_implementation_plan.md](track_excursion_implementation_plan.md)

---

## 1. Product decision

The story is named **Track Excursion Story**, runtime ID `track_excursion_story/v1`.

Its primary truth is that the hero left the racing surface. It is not an “incident story”. The
iRacing incident counter is supporting evidence and may start an observation window, but it must
not determine the spoken noun.

The complete story has three independently evaluated parts:

```text
possible precursor/cause
        -> confirmed track excursion
        -> confirmed or probable outcome
```

`BACK_ON_TRACK` is not automatically the end. After rejoining, the observer must determine whether
the driver:

- regained control and normal running;
- continues significantly slower;
- limps to the pits;
- resets/tows to the pits;
- remains stopped or disappears from the world.

Causes and outcomes may stay unknown. A specific confirmed core fact is more valuable than a
complete but invented story.

## 2. Hard spoken-language rule

The word **incident** and its inflected/localized forms are forbidden in ordinary narration of:

- an off-track excursion;
- contact;
- loss of control, slide, or spin;
- braking overshoot;
- avoidance;
- damage, towing, reset, rejoin, or recovery.

It is allowed only in the dedicated numeric context `INCIDENT_POINTS_UPDATE`, where the actual
iRacing incident-point count is the subject of the sentence.

Examples:

| Truth | Allowed | Forbidden |
| --- | --- | --- |
| Off track | “Vyjel mimo trať.” | “Máme tu incident.” |
| Contact | “Došlo ke kontaktu.” | “Po incidentu zpomalil.” |
| Slide | “Auto šlo do smyku.” | “Zachraňuje incident.” |
| Spin | “Dostal hodiny.” | “Incident ho otočil.” |
| Recovery | “Auto srovnal a pokračuje.” | “Z incidentu se zotavil.” |
| Count | “Po tomto momentu má čtyři incident body.” | n/a |

This is an eligibility rule, not a style preference:

1. when `OFF_TRACK` is confirmed, generic `incident` commentary nodes are unavailable;
2. the selected microplan must carry `primary_relation = track_excursion`;
3. the composer may use only the vocabulary family for the selected semantic facts;
4. the post-LLM validator rejects forbidden incident vocabulary unless
   `event_type == INCIDENT_POINTS_UPDATE`;
5. a rejected LLM result stays silent, preserving the #215 contract; it does not fall back to a
   forbidden generic sentence.

Internal compatibility event names may temporarily contain `INCIDENT`. They are transport names,
not permission to say the word.

## 3. Scenario granularity

### 3.1 Confirmed core facts

These are directly observable with the current extracted fields:

| Runtime fact | Meaning |
| --- | --- |
| `OFF_TRACK_ENTERED` | `PlayerTrackSurface` is stably OffTrack |
| `OFF_TRACK_ACTIVE` | The hero remains outside the scored racing surface |
| `BACK_ON_TRACK` | Stable OffTrack → OnTrack transition |
| `MOTION_RESTORED` | On-track movement is held above the recovery threshold |
| `STOPPED` | Motion remains below the stopped threshold |
| `TOW_ACTIVE` | `PlayerCarTowTime` is positive |
| `PIT_ENTRY_DRIVEN` | Pit entry follows continuous lap progress and normal pit approach |
| `RESET_TO_PITS` | Teleport/reset signature, not a driven pit entry |

### 3.2 Cause hypotheses

These attach to the excursion as evidence-qualified hypotheses. They do not replace the confirmed
off-track fact.

| Scenario name | Runtime ID | Meaning |
| --- | --- | --- |
| Loss of control | `LOSS_OF_CONTROL` | Vehicle motion no longer follows the intended steering path |
| Slide | `SLIDE` | Sustained sideslip without enough rotation for a spin |
| Spin | `SPIN` | Large accumulated heading rotation with loss of forward progress |
| Vehicle contact | `CONTACT_VEHICLE` | Contact with another car is supported by dynamics and relative-car evidence |
| Barrier contact | `CONTACT_BARRIER` | Contact with a fixed object is supported by dynamics and boundary evidence |
| Braking overshoot | `BRAKING_OVERSHOOT` | Braking/turn-in was materially later or faster than a trusted local reference |
| Avoidance maneuver | `AVOIDANCE_MANEUVER` | A nearby conflict and evasive input pattern precede the excursion |
| Unknown cause | `CAUSE_UNKNOWN` | The excursion is confirmed but no cause crosses its confidence threshold |

Contact is temporal, not permanently a precursor. It can be:

- `CONTACT_VEHICLE -> OFF_TRACK_ENTERED` when another car causes the excursion;
- `OFF_TRACK_ENTERED -> CONTACT_BARRIER` when the excursion ends at a barrier;
- `OFF_TRACK_ENTERED -> CONTACT_VEHICLE` when the uncontrolled car contacts another vehicle
  after leaving the normal line.

The graph stores `temporal_relation = before_core | during_core | after_core` and must not infer
causality from timing alone.

### 3.3 Outcome scenarios

| Scenario name | Runtime ID | Required meaning |
| --- | --- | --- |
| Control regained | `CONTROL_REGAINED` | Stable controllable motion returns; no claim about track position |
| Back on track | `BACK_ON_TRACK` | The car is physically/scoring-wise back on the racing surface |
| Normal running resumed | `NORMAL_RUNNING_RESUMED` | Rejoined and local pace recovered for a minimum hold |
| Continuing slowly | `PACE_LOSS_SUSTAINED` | Car continues, but local pace remains materially below reference |
| Limping to pits | `LIMPING_TO_PITS` | Sustained pace loss is followed by a supported pit intention/approach |
| Pit for repairs | `PIT_FOR_REPAIRS` | Driven pit entry plus repair evidence confirms the purpose |
| Tow started | `TOW_STARTED` | Race-mode tow/ESC state becomes authoritative |
| Reset to pits | `RESET_TO_PITS` | Practice/Qualifying reset or teleport to the pit stall |
| Stopped after excursion | `STOPPED_AFTER_EXCURSION` | Car remains stopped without a tow/reset yet |
| Run continuation lost | `RUN_CONTINUATION_LOST` | Run-scoped terminal result; not automatically a race retirement |

`BACK_ON_TRACK` is a geometric transition. `CONTROL_REGAINED` is a vehicle-control conclusion.
`NORMAL_RUNNING_RESUMED` is a pace conclusion. They may occur at different times and must not be
collapsed into one ambiguous “recovered” fact.

## 4. Complete state graph

This composite story is a **factorized statechart**, not one flat FSM. Location, vehicle control,
contact evidence, and consequence can change independently. A flat model would need separate
states for combinations such as “off track + moving + barrier contact + damage suspected” and
would quickly become unmaintainable.

```text
LOCATION       ON_TRACK -> OFF_TRACK -> REJOINED -> ON_TRACK / PIT / NOT_IN_WORLD

CONTROL        STABLE -> SLIDE / SPIN / LOST_CONTROL -> STOPPED / CONTROL_REGAINED

CONTACT        NONE -> CONTACT_UNKNOWN / CONTACT_VEHICLE / CONTACT_BARRIER
                        relation: before_core / during_core / after_core

CONSEQUENCE    EVALUATING -> NORMAL_PACE
                          -> PACE_LOSS -> LIMPING_TO_PITS -> PIT_FOR_REPAIRS
                          -> DAMAGE_SUSPECTED -> DAMAGE_CONFIRMED
                          -> TOW_STARTED [RACE]
                          -> RESET_TO_PITS [PRACTICE/QUALIFYING]
```

The composite narrator reads a consistent snapshot across these regions. Examples:

```text
LOCATION=OFF_TRACK + CONTACT=CONTACT_BARRIER(after_core)
  + CONSEQUENCE=TOW_STARTED
  -> “Po výjezdu přišla rána do bariéry a nyní následuje odtah.”

LOCATION=REJOINED + CONTROL=CONTROL_REGAINED
  + CONSEQUENCE=NORMAL_PACE
  -> “Auto srovnal, je zpět na trati a pokračuje v tempu.”

LOCATION=REJOINED + CONSEQUENCE=PACE_LOSS
  -> “Je zpět na trati, ale pokračuje výrazně pomaleji.”
```

The track-excursion episode is created only when `OFF_TRACK_ENTERED` is confirmed. A bounded
pre-roll buffer attaches earlier slide, contact, braking, or avoidance evidence to that new
episode. A slide that is caught while the car stays on track belongs to a separate future
`vehicle_control_story`; it must not create a fictitious track excursion.

The observer may emit the confirmed core immediately and revise only the cause/outcome evidence.
It must never revise `OFF_TRACK_ENTERED` back into a generic event label.

## 5. What can be detected today

### 5.1 Current reliable capabilities

The current extractor and `RaceState` contain:

- incident count;
- player track surface;
- speed;
- lap-distance progress;
- tow time;
- pit-road state and pit/reset geometry;
- nearby cars by position and estimated longitudinal gap;
- session type, session/run identity, and player position.

With these fields the system can reliably recognize:

- off-track entry and duration;
- stopped versus moving at a coarse level;
- back on track;
- tow/reset versus continuous driving;
- driven pit entry versus teleport/reset;
- sustained gross pace loss after a track excursion, once a local reference is added.

### 5.2 Slide and spin

**Current answer: no, not reliably.** The application extracts only scalar speed for player
dynamics. It does not currently extract yaw rate, steering angle, lateral velocity/acceleration,
brake, throttle, or wheel speeds.

The proposed detector needs live availability verification and then extraction of at least:

- vehicle-frame longitudinal and lateral velocity;
- yaw rate and unwrapped yaw change;
- steering-wheel angle;
- lateral and longitudinal acceleration;
- brake and throttle;
- optionally individual wheel speeds and ABS activity.

Derived features:

```text
sideslip beta       = atan2(v_lateral, max(abs(v_longitudinal), epsilon))
yaw accumulation    = integral(abs(yaw_rate), dt) over a bounded window
countersteer score  = opposite-sign steering/yaw evidence held in time
speed loss ratio    = current_speed / pre-event_speed
```

Initial classification:

- `SLIDE_PROBABLE`: high `abs(beta)` and yaw mismatch held for at least `0.25 s`, forward progress
  preserved, accumulated yaw below the spin boundary;
- `SPIN_CONFIRMED`: accumulated heading rotation exceeds the calibrated boundary and forward
  progress collapses or reverses;
- `LOSS_OF_CONTROL`: evidence is strong but does not safely distinguish slide from spin.

Thresholds are car-class and speed dependent. Fixed universal yaw/slip thresholds must not become
production defaults without labeled replay calibration.

### 5.3 Contact

**Current answer: contact type is not authoritative.** An incident-count jump and a nearby car do
not prove that the nearby car caused contact. The current project correctly treats nearby cars as
context only.

`CONTACT_PROBABLE` may combine:

- abrupt longitudinal/lateral acceleration impulse;
- discontinuity in yaw rate or wheel speed;
- incident-count edge in a narrow time window;
- another car occupying a compatible relative position;
- loss of speed or trajectory discontinuity.

Vehicle versus barrier must remain `unknown` unless the evidence source can distinguish them. A
nearby driver must never be named as the cause from proximity alone. Replay vision/audio could be
a future independent source, but is outside this deterministic telemetry scenario.

### 5.4 Braking overshoot

**Current answer: not yet.** “Missed braking point” is not a direct telemetry fact. It requires a
track/car reference model:

- unwrapped track position;
- brake onset and pressure history;
- speed at brake onset and turn-in;
- steering/yaw response;
- reference distribution from the hero's clean laps for the same track/car/conditions.

Suggested evidence:

```text
late_brake_z = (observed_brake_position - reference_median) / reference_MAD
entry_speed_z = (observed_entry_speed - reference_median) / reference_MAD
```

`BRAKING_OVERSHOOT_PROBABLE` requires both a material reference deviation and a compatible later
trajectory/off-track result. Without a trusted reference, the cause remains unknown. Commentary
must not say “probrzdil” from speed loss alone.

### 5.5 Avoidance maneuver

**Current answer: intention cannot be confirmed.** It can only be a high-confidence hypothesis.

Evidence may include:

- a car ahead or alongside in a collision corridor;
- closing/conflict time-to-contact;
- abrupt steering or braking away from that corridor;
- the evasive input preceding the off-track transition;
- no earlier loss-of-control signature.

Suggested metric:

```text
TTC = longitudinal_gap / max(relative_closing_speed, epsilon)
```

`AVOIDANCE_MANEUVER_PROBABLE` is narratable only above a calibrated high threshold. Otherwise the
commentary says only that the hero went off track.

### 5.6 Damage and limping

Slow speed alone does not prove damage. The outcome ladder is:

```text
PACE_LOSS_SUSTAINED       confirmed from local pace
DAMAGE_SUSPECTED          pace loss plus contact/tow/vehicle-dynamics evidence
LIMPING_TO_PITS           sustained pace loss plus supported pit intention
PIT_FOR_REPAIRS           repair telemetry/flag or repair service confirms damage
```

Local pace ratio:

```text
pace_ratio = observed_segment_speed / clean_reference_segment_speed
```

The reference is conditioned by track, car class, wet state, yellow/caution state, pit approach,
and traffic. A low ratio must be held across time/track distance and must not fire during a normal
slow corner, caution, pit entry, start, or traffic blockage.

Until repair evidence is extracted and validated, say “pokračuje výrazně pomaleji” or “míří do
boxů”; do not assert “auto je poškozené”.

## 6. Mode-specific endings

### Race

| Evidence | Scenario outcome | Commentary meaning |
| --- | --- | --- |
| Tow time becomes active | `TOW_STARTED` | The car is being towed/reset; the current race run is interrupted |
| Stopped, no tow yet | `STOPPED_AFTER_EXCURSION` | The car remains stopped; do not predict retirement |
| Continues slowly | `PACE_LOSS_SUSTAINED` | The car continues but pace is significantly reduced |
| Slow continuation then driven pit entry | `LIMPING_TO_PITS` | The driver completes the remaining distance and heads to the pits |
| Repair service confirmed | `PIT_FOR_REPAIRS` | Repairs, not merely a routine stop, are supported |

Do not say “retired” on tow start alone. Retirement requires a separate authoritative terminal
condition or no return before session classification closes.

### Practice and Qualifying

| Evidence | Scenario outcome | Commentary meaning |
| --- | --- | --- |
| Reset/teleport to pit stall | `RESET_TO_PITS` | The lap/run is abandoned and the car returns directly to pits |
| Continuous lap progress into pit approach | `PIT_ENTRY_DRIVEN` | The driver physically drives the car back |
| Reset followed by a new run | terminal old episode | New `run_epoch` owns the next story |

Never call an ESC/reset `PIT_ENTRY_DRIVEN`. The existing teleport geometry remains authoritative.

## 7. Commentary composition

### 7.1 Specific truth dominates generic context

Candidate eligibility order:

```text
confirmed semantic fact
  > high-confidence cause + confirmed off-track compound
  > confirmed off-track alone
  > silence
```

A generic counter change is never preferred over confirmed off-track, contact, slide, spin, or
braking overshoot.

### 7.2 Compound root sentences

When cause and off-track belong to the same parent story and their temporal relationship is
supported, the Director may choose one compound microplan instead of two competing lines:

| Facts | Example |
| --- | --- |
| `SLIDE -> OFF_TRACK` | “Auto šlo do smyku a skončilo mimo trať.” |
| `SPIN -> OFF_TRACK` | “Dostal hodiny a vyjel mimo trať.” |
| `CONTACT_VEHICLE -> OFF_TRACK` | “Po kontaktu s vozem vedle končí mimo trať.” |
| `BRAKING_OVERSHOOT -> OFF_TRACK` | “Probrzdil nájezd a vyjel mimo trať.” |
| `AVOIDANCE_MANEUVER -> OFF_TRACK` | “Při úhybném manévru vyjel mimo trať.” |
| unknown cause + `OFF_TRACK` | “Vyjel mimo trať.” |

Use the specific cause only at its narratable confidence. Do not hedge every sentence; omit a weak
cause instead.

### 7.3 Outcome sentences

| Outcome | Example |
| --- | --- |
| `CONTROL_REGAINED` | “Auto srovnal a pokračuje.” |
| `BACK_ON_TRACK` | “Je zpět na trati.” |
| `NORMAL_RUNNING_RESUMED` | “Je zpět v tempu a pokračuje.” |
| `PACE_LOSS_SUSTAINED` | “Pokračuje, ale výrazně pomaleji.” |
| `LIMPING_TO_PITS` | “Pomalu dojíždí zbytek kola a míří do boxů.” |
| `PIT_FOR_REPAIRS` | “Dojel do boxů na opravu.” |
| `TOW_STARTED` | “Auto zůstalo stát a následuje odtah.” |
| `RESET_TO_PITS` | “Resetuje do boxů; toto kolo končí.” |

`BACK_ON_TRACK` should be spoken promptly when the excursion was already heard. If the previous
line is still speaking, the newest valid closure replaces an older equal-tier waiter under the
#215 scheduler contract.

## 8. Confidence and narration policy

| Evidence level | Runtime behavior | Speech behavior |
| --- | --- | --- |
| `CONFIRMED` | May drive state transition | Direct factual language |
| `PROBABLE_HIGH` | May attach a cause/outcome hypothesis | Specific language only after calibrated threshold; otherwise omit |
| `PROBABLE_LOW` | Diagnostic context only | Never spoken as fact |
| `UNKNOWN` | Preserve episode and await timeout/reset | Omit cause/outcome; speak confirmed core only |

Initial narration thresholds:

- off-track/rejoin/tow/reset: `>= 0.85`;
- slide/loss of control: `>= 0.90` after car-class calibration;
- contact type: `>= 0.95` and independent target evidence;
- braking overshoot: `>= 0.92` with trusted reference;
- avoidance intention: `>= 0.95`;
- damage assertion: confirmed repair source, not a probability threshold alone.

These are starting safety thresholds for shadow evaluation, not claimed calibrated production
values.

## 9. Required graph and microplan changes

### 9.1 Audit of the current graph

The baseline `sequence_graph.json` is graph version 2 with 54 nodes and 24 edges. Only five nodes
cover this subject:

| Current node | Event selector | Current meaning | Defect |
| --- | --- | --- | --- |
| `incident` | `INCIDENT/RESULT`, unbranched | Mixture of count, contact, mistake, save, and recovery | One node states several mutually unproven facts |
| `incident_off_track` | `INCIDENT/RESULT`, `branch=off_track` | Confirmed excursion | Correct core vocabulary, but only eight variants and no outgoing story edge |
| `incident_unknown` | `INCIDENT/RESULT`, `branch=unknown` | Unknown counter edge | Still says incident/hit although the physical event is unknown |
| `incident_aftermath` | `INCIDENT_AFTERMATH/RESULT` | `kind=stalled|rolling` | Most text assumes contact/hit and the raw `kind` label is not semantic/localized |
| `back_under_way` | `BACK_UNDER_WAY/RESULT` | Motion restored after stalled aftermath | Some text also claims rejoin, control, or restored pace which this event does not prove |

The current relevant edges are:

```text
incident -> incident_aftermath
  same_correlation=false, 0.5..20 s, transition +8

incident_aftermath -> back_under_way
  same_correlation=true, 0.5..90 s, transition +8, closure
```

This is not a complete cycle for four independent reasons.

1. A correctly classified event selects `incident_off_track`, not `incident`. There is no
   `incident_off_track -> incident_aftermath` or `incident_off_track -> back_under_way` edge.
2. The Director drops `INCIDENT_AFTERMATH` when `INCIDENT` is present in the same batch. If that
   intermediate beat is not spoken, `back_under_way` has no direct edge from the heard root.
3. The first edge deliberately ignores correlation, so any recent `incident` node can lend a
   transition bonus to an unrelated aftermath. The second requires the same correlation, which
   cannot connect independent beat correlations in the proposed parent episode.
4. No nodes or edges represent precursor, contact timing, stopped state, rejoin, pace assessment,
   tow/reset, slow return to pits, or confirmed repair.

The content itself also leaks unsupported semantics. Indicative static counts on the baseline
variants are:

| Node | Lines | Mention “incident” | Assert contact/hit | Assert continuing/recovery/pace |
| --- | ---: | ---: | ---: | ---: |
| `incident` | 96 | 20 | 5 | 23 |
| `incident_off_track` | 8 | 0 | 0 | 0 |
| `incident_unknown` | 8 | 2 | 1 | 0 |
| `incident_aftermath` | 96 | 4 | 31 | 2 |
| `back_under_way` | 72 | 0 | 1 | 7 |

Counts overlap and are only a review aid; every line still needs semantic validation. Concrete
failures include:

- `incident` says contact, a save, return to the racing line, or continued pace from only a count
  edge;
- `incident_aftermath` says “Po kontaktu…” or “po zásahu…” although its input proves only
  stalled/rolling;
- `incident_aftermath` can format the internal English token `stalled` into Czech copy;
- `back_under_way` contains “return to pace” variants although it proves only motion;
- composer history labels hard-code “od incidentu” / “from the incident” and “přes jeho následky”,
  bypassing otherwise-correct node wording.

The current `unique_result` semantic policy keys fatigue by `event_id`, so the graph does not know
that root, consequence, and closure teach the audience about one parent episode. The current
`occurrence` material policy has the same limitation.

### 9.2 Required graph schema v3

Do not encode the new cycle only as more text variants. Graph version 3 must add typed scenario
semantics while retaining version-2 compatibility during rollout.

`GraphCandidate` and `_BeatRef` gain:

```text
scenario_id
parent_story_id
beat_role              root | development | closure | terminal
primary_relation       track_excursion | contact | control | pace | pit_return
cause                   optional closed enum
outcome                 optional closed enum
temporal_relation       before_core | during_core | after_core
evidence_level          CONFIRMED | PROBABLE_HIGH | PROBABLE_LOW | UNKNOWN
confidence              0..1
```

Node matching gains a closed `match` object. It is not a general expression language:

```json
{
  "event_types": ["TRACK_EXCURSION"],
  "phases": ["RESULT"],
  "match": {
    "primary_relation": "track_excursion",
    "cause": ["slide"],
    "evidence_level": ["CONFIRMED", "PROBABLE_HIGH"],
    "minimum_confidence": 0.90
  }
}
```

Only schema-enumerated fields and enum values are valid. Unknown selectors fail graph validation
and invoke the existing fail-soft fallback.

Edge identity changes from one ambiguous boolean to a closed policy:

```json
{
  "when": {
    "identity": "same_parent_story",
    "min_gap_s": 0.3,
    "max_gap_s": 90.0
  }
}
```

Allowed identity policies:

| Policy | Use |
| --- | --- |
| `same_correlation` | Lifecycle phases of one beat |
| `same_parent_story` | Different beats of one track-excursion episode |
| `caused_by_parent_story` | Child pit cycle linked to the excursion episode |
| `same_run` | Rare session facts where no episode relation is required |
| `any` | Explicit legacy-only transition; prohibited for the new cycle |

The loader maps version-2 `same_correlation=true|false` for compatibility. All new track-excursion
edges must use an explicit identity policy; `any` is invalid for them.

Add graph policies:

```text
SemanticPolicy.SCENARIO_EPISODE
MaterialChangePolicy.SCENARIO_BEAT
```

Their semantic key is:

```text
(run_epoch, scenario_id, parent_story_id, primary_relation)
```

and material revision is:

```text
(beat_role, cause, outcome, temporal_relation)
```

This keeps distinct facts within one episode speakable while applying repetition fatigue to a
repeated meaning rather than to unrelated event IDs.

### 9.3 Required node migration

Current nodes are migrated as follows:

| Current node | Action | Target |
| --- | --- | --- |
| `incident` | Remove from physical-event narration; retain only count-specific lines | `incident_points_update` / `INCIDENT_POINTS_UPDATE` |
| `incident_unknown` | Remove | Unknown cause uses `track_excursion` with confirmed core only |
| `incident_off_track` | Rename and expand | `track_excursion` / `TRACK_EXCURSION` |
| `incident_aftermath` | Split by actual fact | stopped, contact, control, and pace nodes below |
| `back_under_way` | Compatibility alias during rollout, then split | rejoin, control-regained, and pace-restored nodes |

Target speakable nodes:

| Stage | Node ID | Event / selector | What the sentence must say |
| --- | --- | --- | --- |
| Numeric side fact | `incident_points_update` | `INCIDENT_POINTS_UPDATE` | Incident-point count only; no physical cause/outcome |
| Root | `track_excursion` | `TRACK_EXCURSION`, cause unknown | Explicitly outside track/racing surface |
| Root compound | `loss_of_control_to_excursion` | cause `loss_of_control` | Loss of control **and** off-track |
| Root compound | `slide_to_excursion` | cause `slide` | Slide **and** off-track |
| Root compound | `spin_to_excursion` | cause `spin` | Spin **and** off-track |
| Root compound | `vehicle_contact_to_excursion` | cause `contact_vehicle`, relation before/during | Vehicle contact **and** off-track; driver name only when independently known |
| Root compound | `barrier_contact_to_excursion` | cause `contact_barrier`, relation before/during | Barrier contact **and** off-track |
| Root compound | `braking_overshoot_to_excursion` | cause `braking_overshoot` | Overshoot **and** off-track |
| Root compound | `avoidance_to_excursion` | cause `avoidance_maneuver` | Avoidance **and** off-track |
| Development | `stopped_after_excursion` | `STOPPED_AFTER_EXCURSION` | Car stopped; no unsupported cause |
| Development | `vehicle_contact_after_excursion` | `CONTACT`, vehicle, after core | Contact occurred after leaving the track |
| Development | `barrier_contact_after_excursion` | `CONTACT`, barrier, after core | Barrier contact occurred after leaving the track |
| Closure | `track_rejoined` | `BACK_ON_TRACK` | Back on racing surface only |
| Closure | `control_regained` | `CONTROL_REGAINED` | Car caught/straightened only |
| Closure | `normal_running_resumed` | `NORMAL_RUNNING_RESUMED` | Normal local pace is restored |
| Development | `pace_loss_sustained` | `PACE_LOSS_SUSTAINED` | Continues materially slower; do not assert damage |
| Development | `limping_to_pits` | `LIMPING_TO_PITS` | Slow continuous return toward pits |
| Terminal | `pit_for_repairs` | `PIT_FOR_REPAIRS` | Repairs only with confirmed repair evidence |
| Terminal | `tow_started_race` | `TOW_STARTED`, mode Race | Tow/reset started; do not assert retirement |
| Terminal | `reset_to_pits` | `RESET_TO_PITS`, mode Practice/Qualify | Run/lap abandoned by reset, not driven pit entry |
| Terminal | `run_continuation_lost` | `RUN_CONTINUATION_LOST` | This run ended; do not overstate session/race retirement |

`track limits` wording belongs only to a brief boundary excursion with no supported contact,
spin, stop, or major consequence. A large off-track must not be softened into a track-limits call.

All root-compound variants must contain both the specific supported cause and explicit off-track
meaning. A cause-specific node that can say only “dostal smyk” does not satisfy this scenario,
because it could omit the confirmed core fact.

### 9.4 Required edge set

Let `ROOTS` be all root and root-compound nodes. The JSON remains explicit; these groups describe
the required validator inventory rather than runtime wildcard edges.

Required primary paths:

```text
ROOTS -> stopped_after_excursion
ROOTS -> vehicle_contact_after_excursion | barrier_contact_after_excursion
ROOTS -> track_rejoined
ROOTS -> tow_started_race | reset_to_pits

stopped_after_excursion -> track_rejoined | tow_started_race | reset_to_pits
contact_*_after_excursion -> stopped_after_excursion | track_rejoined
contact_*_after_excursion -> pace_loss_sustained | tow_started_race | reset_to_pits

track_rejoined -> control_regained
track_rejoined -> normal_running_resumed | pace_loss_sustained
control_regained -> normal_running_resumed | pace_loss_sustained

pace_loss_sustained -> normal_running_resumed
pace_loss_sustained -> limping_to_pits | tow_started_race | reset_to_pits
limping_to_pits -> pit_entry
limping_to_pits -> pit_for_repairs
pit_entry -> pit_for_repairs when the pit cycle is caused by the parent excursion
```

All edges inside the scenario require `same_parent_story`. Links to the independently correlated
pit cycle require `caused_by_parent_story`.

The graph operates over heard beats, so it must include direct truthful skip edges for intermediate
beats that were detected but not spoken. At minimum:

```text
ROOTS -> track_rejoined
ROOTS -> normal_running_resumed
ROOTS -> pace_loss_sustained
ROOTS -> limping_to_pits
ROOTS -> pit_for_repairs
ROOTS -> tow_started_race
ROOTS -> reset_to_pits

stopped_after_excursion -> normal_running_resumed
stopped_after_excursion -> pace_loss_sustained
stopped_after_excursion -> limping_to_pits
```

These are not claims that the intermediate facts did not happen. They ensure that a valid outcome
can close the last fact the audience actually heard. Every direct edge still requires the same
parent identity and its own time window.

Suggested initial windows for shadow evaluation:

| Transition class | Window |
| --- | ---: |
| Root to immediate development/contact | `0.0..20 s` |
| Root/development to rejoin/control | `0.3..90 s` |
| Rejoin/control to pace assessment | `1..45 s` |
| Pace loss to pit intention | `1..300 s` |
| Limping to driven pit entry/repair | `1..900 s` |
| Root/development to tow/reset | `0.2..120 s` |

These are maximum narrative linkage windows, not detector thresholds. They must be calibrated from
complete session replays.

`incident_points_update` has no causal story edges. It is a numeric side fact and must not become a
root for contact, off-track, recovery, or pit-return narration.

### 9.5 Selection, suppression, and priority

Replace `_prefer_incident_over_aftermath()` with episode-aware beat arbitration:

1. compare only candidates from the same `parent_story_id`;
2. prefer a root compound over separate cause and core lines;
3. prefer confirmed core over a generic numeric side fact;
4. allow at most one root sentence per episode;
5. do not discard an aftermath/outcome belonging to a different episode merely because it arrives
   in the same batch;
6. when a development beat is skipped, keep direct closure eligibility;
7. coalesce `BACK_ON_TRACK`, `CONTROL_REGAINED`, and `NORMAL_RUNNING_RESUMED` if they become valid
   within one composition window, rather than speaking three near-duplicate sentences.

Strict editorial tiers remain lexicographic. Target assignments:

| Tier | Beats |
| ---: | --- |
| 800 | `TRACK_EXCURSION`; supported contact/slide/spin/loss-of-control compound root; decisive Race tow |
| 400 | `LIMPING_TO_PITS`, linked pit entry, `PIT_FOR_REPAIRS` |
| 250 | stopped, rejoin, control regained, normal pace, sustained pace loss, Practice/Qualify reset |
| 200 | `INCIDENT_POINTS_UPDATE` unless an explicit broadcast product decision raises it |

Confidence can order candidates only inside one tier. It cannot change this table or override
FINISH, START, flags, position, or other existing strict-tier invariants.

### 9.6 Text and microplan contract

For every new node:

- the anchor clause states only its node fact;
- emotion changes intensity, never cause, state, or outcome;
- optional history may mention only facts with the same parent story;
- `primary_relation`, `cause`, `outcome`, `temporal_relation`, evidence level, and confidence are
  explicit microplan fields;
- optional clauses cannot upgrade `PROBABLE_LOW`/`UNKNOWN` evidence into spoken truth;
- raw enum values such as `stalled` are never inserted into localized prose;
- a missing optional slot removes its clause, never the factual anchor;
- no `track_rejoined` variant claims normal pace;
- no `control_regained` variant claims pit intent or damage;
- no `pace_loss_sustained` variant claims damage;
- no `tow_started_race` variant claims retirement;
- no `reset_to_pits` variant calls the transition a driven pit entry.

Delete the hard-coded composer history labels `incident` and `incident_aftermath`. Replace them
with typed labels for the exact scenario nodes, for example “po výjezdu mimo trať”, “po kontaktu”,
“po návratu na trať”, and “při pomalém návratu do boxů”. History text follows the same forbidden
vocabulary validator as the anchor.

The vocabulary validator applies to authored variants, composed skeletons, history clauses, and
LLM output. For Czech and English ordinary driving-event categories, reject the token pattern
equivalent to `\bincident\p{L}*\b`. The sole allow-list category is `INCIDENT_POINTS_UPDATE`.
Simple substring checks are insufficient because Czech inflection must be covered without
rejecting unrelated text accidentally.

### 9.7 Required implementation files

The graph change is not isolated to JSON. The implementation must review/update:

| File/component | Required change |
| --- | --- |
| `commentary/data/sequence_graph.json` | New nodes, variants, explicit edges, schema version 3 |
| `commentary/graph.py` | Typed node match fields, edge identity policy, new semantic/material policies, validation |
| `commentary/graph_runtime.py` | Parent-story candidate identity, semantic keys, edge matching, score diagnostics |
| `commentary/director.py` | Episode-aware root/development arbitration and closure coalescing |
| `commentary/composer.py` | Exact scenario facts, parent-aware history, remove generic incident labels |
| commentary validator / TTS commit path | Forbidden-vocabulary validation with count-only allow-list |
| `commentary/priorities.py` | Explicit strict tiers for every new event type |
| `events/audience.py` and event catalog | Register commentary-only versus overlay-visible facts |
| story context serialization | Carry `scenarioId`, `parentStoryId`, beat role, cause/outcome, evidence |

The graph loader must reject a graph where:

- a required scenario node has no variants in a supported locale/emotion bucket;
- a new track-excursion edge uses legacy `same_correlation=false` instead of an identity policy;
- a closure has no path from any root actually selectable for that cause;
- a physical-event node contains forbidden incident vocabulary;
- `PIT_FOR_REPAIRS` lacks a repair-confirmation requirement;
- a target node refers to an unregistered event type.

### 9.8 Required graph regressions

Replace brittle assertions of exactly 54 nodes and 24 edges with named inventory and connectivity
assertions. Exact counts make legitimate graph growth look like a regression while failing to
prove that the story is complete.

Tests must prove:

- every root variant can reach every valid terminal appropriate to its mode;
- `incident_off_track` compatibility input maps to `track_excursion` and has a direct path to a
  rejoin/recovery closure;
- a suppressed same-batch development beat does not break the later closure path;
- two episodes close only against their own `parent_story_id` even at the same timestamp;
- same correlation with a different parent story is rejected as an identity conflict;
- a linked pit cycle uses `caused_by_parent_story`, while a routine pit stop does not close the
  excursion story;
- an off-track root can never fall back to `incident` or `incident_unknown` copy;
- every authored and composed ordinary-event line passes the forbidden-vocabulary rule;
- `INCIDENT_POINTS_UPDATE` is the only tested allow-list exception;
- contact after core cannot be composed as the cause of the core;
- rejoin, control restored, and normal pace remain independently testable and coalesce only inside
  the declared composition window;
- confidence below the node minimum removes the cause-specific node and falls back to the confirmed
  `track_excursion` root;
- a missing intermediate node still allows a truthful direct closure;
- graph history never links different run epochs or parent stories;
- strict editorial tiers and all #215 queue/MiniStory/LLM regressions remain green.

## 10. Acceptance criteria

- [ ] Confirmed off-track always selects off-track/track-limits vocabulary or silence, never a
      generic incident sentence.
- [ ] The word “incident” is accepted only for `INCIDENT_POINTS_UPDATE` in CS and EN validation.
- [ ] Cause is optional and never fabricated to complete the story.
- [ ] Contact before and after off-track retain distinct temporal relations.
- [ ] A nearby car alone cannot produce or name `CONTACT_VEHICLE`.
- [ ] Slide/spin remain disabled until the required dynamics fields are extracted and calibrated.
- [ ] Braking overshoot remains unknown without a trusted track/car reference.
- [ ] Avoidance is spoken only above its high-confidence threshold.
- [ ] Back on track, control regained, and normal pace resumed remain separate facts.
- [ ] Slow continuation does not assert damage.
- [ ] Driven pit entry, tow, and Practice/Qualifying reset are mutually exclusive outcomes.
- [ ] Race tow does not assert final retirement without a separate terminal fact.
- [ ] Every cause and outcome carries evidence, confidence, stable reason, episode identity, and
      run epoch.
- [ ] Strict editorial tiers and all #215 MiniStory/queue/LLM invariants remain intact.

## 11. Implementation slices

1. **Vocabulary guard:** make off-track exclusive over generic incident copy and add the
   `INCIDENT_POINTS_UPDATE` exception.
2. **Outcome expansion using current fields:** distinguish control restored, back on track,
   stopped, tow/reset, continuous slow driving, and driven pit entry.
3. **Pace model:** add track-segment clean reference and sustained pace-loss detection.
4. **Dynamics extraction in shadow:** yaw, lateral motion, steering, brake, throttle, acceleration,
   and optional wheel speeds.
5. **Slide/spin detector:** calibrate by car class and speed using labeled sessions.
6. **Contact hypothesis:** add impulse and relative-car evidence; keep target/type unknown unless
   independently supported.
7. **Braking and avoidance hypotheses:** require local reference and conflict-corridor evidence.
8. **Repair confirmation:** extract and validate repair evidence before enabling damage language.

Every slice lands test-first, runs in shadow before active use, and updates the versioned scenario
definition when semantics or thresholds change.

**TDD exception for this document:** docs-only product/specification change.

**Verification:** current extracted fields and existing off-track, tow, pit teleport, run epoch,
MiniStory, Director, and graph contracts were inspected on the stated baseline.
