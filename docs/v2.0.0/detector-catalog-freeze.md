# v2.0.0 detector catalog and parameter freeze

**Status:** design-freeze candidate owned by issues #241, #247–#255 and #256

This branch-only artifact freezes what the first temporal/composite detectors mean and which values may be tuned after replay testing. Defaults are conservative estimates, not measured truth. Tuning may change a default inside its frozen range without changing architecture; changing an algorithm, unit, predicate, correlation key, lifecycle or range requires a new detector version and a return to the design gate.

## Shared detector contract

Every detector instance is keyed by `(detectorId, detectorVersion, streamEpoch, occurrenceId, orderedCorrelationKey)`. It consumes one immutable FeatureFrame at a time in strictly increasing process-global `frameSequence` order and owns exactly one `inactive|candidate|active|clearing` FSM. Duplicate/older frames are audited no-ops. Narrative `reducerSequence`, speech state, event priority, prompt freedom, fatigue and LLM output are forbidden inputs.

The v2 baseline uses:

- `battle_ahead_v1`: ordered actors `hero→targetAhead`;
- `battle_behind_v1`: ordered actors `challengerBehind→hero`;
- `battle_two_front_v1`: composite identity `(frontRelationEpoch,rearRelationEpoch)`.

The two directional detectors use the same algorithm and parameter schema. Their IDs remain distinct so replay reports and later tuning cannot accidentally exchange actor roles.

## Input and sign convention

The required registered features are:

```text
gap.relation.seconds.estimated_v1
gap.trend.slope
gap.trend.net_closing
gap.trend.coverage
gap.trend.confidence
gap.target_stable
vehicle.phase.current
```

Gap is nonnegative seconds. `gap.trend.slope < 0` and `gap.trend.net_closing > 0` mean the ordered first actor is closing on the second. A missing, stale, ambiguous, wrong-occurrence or wrong-relation value evaluates to `unknown`; `unknown` never satisfies an enter, update or held-for predicate.

Samples are partitioned into monotonic one-second buckets. Sample coverage contributes only the elapsed interval until the next expected sample, capped at `sample_interval_s`; a lone sample never fills the rest of a bucket. A bucket contributes the median valid gap and its midpoint only when its covered duration is at least `bucket_s × min_coverage`. Over the trailing window, slope is ordinary least squares over at least three valid bucket medians and net closing is first-third median minus last-third median. Window coverage is the summed covered duration divided by requested window duration. Insufficient samples/buckets/coverage is `unknown`. A bucket cannot be carried across a relation epoch, occurrence, pit/tow/teleport invalidation or process instance.

## Frozen parameter schema

All defaults below have `provenance=estimated`. Floats must be finite.

| Parameter | Unit/type | Default | Frozen range | Effect |
| --- | --- | ---: | ---: | --- |
| `sample_interval_s` | seconds | 0.25 | 0.10..1.00 | Feature sampling cadence; not the application tick |
| `trend_window_s` | seconds | 12.0 | 6.0..30.0 | Longer rejects braking noise but increases delay |
| `bucket_s` | seconds | 1.0 | 0.5..2.0 | Robust aggregation resolution |
| `min_samples` | count | 8 | 6..60 | Minimum valid raw samples |
| `min_coverage` | fraction | 0.80 | 0.60..1.00 | Minimum usable window coverage |
| `min_confidence` | fraction | 0.70 | 0.50..1.00 | Minimum composed estimator confidence |
| `enter_gap_max_s` | seconds | 3.0 | 1.0..8.0 | Largest gap eligible to open |
| `min_closing_change_s` | seconds | 0.60 | 0.20..2.00 | Minimum robust net closing over the configured window |
| `max_closing_slope` | seconds/second | -0.04 | -0.30..-0.01 | Slope must be at most this value |
| `confirm_s` | seconds | 3.0 | 1.0..10.0 | Continuous enter hold |
| `material_change_s` | seconds | 0.40 | 0.10..1.50 | Minimum change in the window's net-closing value for update revision |
| `update_min_interval_s` | seconds | 6.0 | 2.0..30.0 | Per-relation update rate limit |
| `exit_gap_min_s` | seconds | 4.0 | 1.5..12.0 | Clear-distance hysteresis |
| `clear_slope` | seconds/second | -0.01 | -0.05..0.10 | Stable/opening trend eligible to clear |
| `clear_s` | seconds | 2.0 | 1.0..10.0 | Continuous clear hold |
| `stale_after_s` | seconds | 1.0 | 0.5..3.0 | Maximum feature age |
| `approach_enter_s` | gap seconds | 1.50 | 0.80..3.00 | Material approach band |
| `approach_exit_s` | gap seconds | 1.80 | 1.00..4.00 | Approach-band exit hysteresis |
| `attack_enter_s` | gap seconds | 0.80 | 0.30..1.50 | Attack band |
| `attack_exit_s` | gap seconds | 1.10 | 0.50..2.00 | Attack-band exit hysteresis |
| `overlap_enter_s` | gap seconds | 0.35 | 0.10..0.80 | Proximity prerequisite for overlap confirmation |
| `overlap_exit_s` | gap seconds | 0.55 | 0.20..1.20 | Overlap exit hysteresis |
| `overlap_confirm_s` | seconds | 0.50 | 0.25..2.00 | Continuous ordered-overlap confirmation |
| `two_front_confirm_s` | seconds | 1.00 | 0.50..4.00 | Both directional relations active |
| `two_front_clear_s` | seconds | 1.00 | 0.50..4.00 | Either relation absent before composite end |

Schema cross-field invariants:

```text
sample_interval_s < bucket_s <= trend_window_s
min_samples * sample_interval_s <= trend_window_s
confirm_s <= trend_window_s
enter_gap_max_s < exit_gap_min_s
overlap_enter_s < overlap_exit_s <= attack_enter_s < attack_exit_s
attack_exit_s <= approach_enter_s < approach_exit_s <= enter_gap_max_s
update_min_interval_s >= clear_s
stale_after_s <= trend_window_s
```

The range and invariant validator rejects the whole detector definition before stream admission. It never clamps values.

## Directional enter/update/close predicates

`battle_ahead_v1` and `battle_behind_v1` enter only when all are true continuously for `confirm_s`:

```text
stream is confirmed active
session.stage == race
vehicle.phase.current == racing for both actors where target phase is known
race flag == green
ordered relation identity is stable
gap feature age <= stale_after_s
gap <= enter_gap_max_s
net_closing >= min_closing_change_s
slope <= max_closing_slope
coverage >= min_coverage
confidence >= min_confidence
neither actor is in pit, towing, teleported or not in world
```

When target phase is unavailable, target pit/surface evidence must still be known and valid; absence is `unknown`, not permission. The `active` transition publishes `battle.closing` with ordered actors and submits an event candidate. Ahead maps to the unchanged V4 identifier `HUNTING` and internal kind `battle.pursuit`; behind maps to `HUNTED` and `battle.pressure_behind`. The first accepted candidate for a correlation becomes narrative phase `started`; a later accepted material candidate becomes `updated`. Rejected/suppressed candidates still leave FactView truthful but cannot open/revise a speakable episode or create an opportunity.

While active, a material revision occurs only when either the hysteretic gap band changes or absolute `net_closing` change from the last emitted revision is at least `material_change_s`, and `update_min_interval_s` has elapsed. Each revision uses current fact IDs and effective parameter hash.

Immediate identity/reset invalidators close without a hold: occurrence/stream change, ordered target/relation change, pit/tow/teleport/not-in-world, unsupported stage, checkered/session end, or irreconcilable identity conflict. Other loss of truth enters `clearing` and closes after `clear_s` when any is continuously true:

```text
gap >= exit_gap_min_s
slope >= clear_slope
coverage < min_coverage
confidence < min_confidence
feature is stale or unknown
race flag is not green
```

If the full enter predicate returns before the clear deadline, the instance returns to active without a new STARTED event. A closed instance records one detector ENDED transition and expires its current `battle.closing` fact. No new V4 ENDED identifier is invented. The resulting FactView update closes/invalidates dependent narrative state without creating speech.

## Hysteretic story bands

Band state is a projection of one active directional relation, not a separate detector of closing truth:

- `closing`: active relation outside approach;
- `approach`: enter at `gap<=approach_enter_s`, leave only at `gap>=approach_exit_s`;
- `attack`: enter at `gap<=attack_enter_s`, leave only at `gap>=attack_exit_s`;
- `overlap`: enter only when `gap<=overlap_enter_s` and registered ordered-overlap evidence holds for `overlap_confirm_s`; leave when overlap evidence is known false or `gap>=overlap_exit_s` for `clear_s`.

Transitions may skip inward bands when a valid sample jumps across thresholds, but the detector submits at most one latest material candidate per reducer step. Ahead-band candidates map to the existing `APPROACH`, `ATTACK_RANGE` and `SIDE_BY_SIDE` V4 identifiers/internal kinds. Outward movement walks to the highest still-valid band; it does not replay synthetic intermediate events. The bands publish `battle.approaching`, `battle.attack_range` or `battle.side_by_side` facts only while their exact state is active.

## Two-front composite

`battle_two_front_v1` opens only when an active `hero→front` relation and active `rear→hero` relation share stream, occurrence and hero identity, have different target actor IDs and remain active for `two_front_confirm_s`. It submits `BATTLE_FOR_POSITION` / internal `battle.two_front` once on entry and publishes the registered `battle.two_front_active=true` feature keyed by both relation epochs. The beat's required claims remain the two ordered `battle.closing` facts; no unregistered two-front AtomicFact is invented.

Target replacement or occurrence/reset invalidation closes immediately. Either directional relation becoming inactive starts `two_front_clear_s`; restoration of the exact same two relation epochs cancels clearing. Expiry records ENDED once and clears the feature without creating a V4 end event. A replacement relation always closes the old composite and may start a new candidate; it never mutates the correlation key.

## Tuning and release policy

The three detectors are `experimental=true,tuning.policy=required` only during branch replay calibration. Their CapturePlan records the complete pre-window, five-second post-window, effective parameters, feature quality/coverage, predicate trace, transition reason and near-threshold negatives. Recorder preflight failure disables only these experimental detectors.

The complete `production|calibration` by `none|optional|required` legality and failure matrix is normative in `public-contracts.md`. Required-capture loss follows the composition-owned health/context bundle in `actor-transition-contract.md`; neither NarrativeRuntime nor TapeWriter owns DetectorBank mutation. This catalog may declare policy and capture requirements but cannot invent a third runtime profile or a private recovery path.

Before final cutover each detector must either:

1. pass its precision/recall/delay/flapping acceptance and be promoted to `experimental=false,tuning.policy=optional`; or
2. remain disabled and make its dependent event routes/beats ineligible.

No released production detector may retain `tuning.policy=required`. Calibration changes only defaults within the frozen ranges and records a new config hash. An algorithm/sign/unit/correlation/lifecycle change creates `*_v2` and requires new replay acceptance.

## Deterministic/direct triggers

S/F, sector, ordered position, pit lifecycle, flag, incident-count and StreamTimeline edges do not reuse the temporal thresholds above. Their `tuning.policy=none`; they use identity dedupe, monotonic ordering and explicit lifecycle guards only. Projection, pace-target, clean-streak, weather-change, HR-band and incident-recovery families are not admitted to runtime merely by this document: each migration issue must bind them to registered features and a validated detector definition before enabling its BeatDefinitions.

This last rule prevents a catalog row from becoming executable because its name exists. Until its detector binding is present and passes the loader, the safe state is unavailable/silent.

## Closure fixtures

Issues #247–#255 cannot close until replay/model fixtures prove:

- braking-point oscillation with insufficient net closing does not enter;
- a sustained closing window enters exactly once after confirmation;
- low coverage, stale data and target swap return unknown/close without a false new relation;
- every enter/exit boundary honors hysteresis and update rate limiting;
- front/rear actor reversal cannot share facts or tape identity;
- two-front opens only for two distinct stable targets and closes on either relation replacement;
- identical frames, parameter hash and reducer order yield identical facts/events;
- all emitted predicates, features, event kinds and tape channels resolve through the frozen registries.
