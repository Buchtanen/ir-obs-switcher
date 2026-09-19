# v2.0.0 EN realization and semantic-verifier freeze

**Status:** controlled-English grammar and corpus machine-frozen for issues #266–#271

This branch-only artifact closes what “factually valid generated text” can mean for a small local model. It covers all 37 realization families used by the exact 64-beat baseline.

## Safety boundary

An embedding/cosine score cannot prove actor direction, polarity, number, freshness or causality. It may only reduce repetition. A second LLM judging the first is also not an authoritative fact gate. Production acceptance is therefore hybrid:

1. deterministic BeatPlan selects the complete allowed claim frame and a pure compiler freezes one RealizationBundle;
2. authored output or Qwen realizes one bounded EN utterance;
3. a family-specific deterministic parser maps every semantic fragment back to typed claims and precomputed surface values;
4. any unknown semantic fragment, missing required claim or extra claim rejects the attempt;
5. the failed `(beatId, episodeRevision)` is suppressed and the director chooses a different beat or silence—no repair, retry or same-beat fallback.

This gives conservative precision by allowing false rejects. It does not claim to understand unrestricted English. `tight` is a controlled natural-language subset; `balanced/loose` remain disabled per family until their grammar, corpus and holdout acceptance are explicitly approved.

## Acceptance function

For BeatPlan claim frame `C=(R,O,F)`, selected optional set `O*`, family `f` and output `x`:

```text
Parse_f(x) = (P, U)

Accept(x,C,f) =
    ShapeEn(x)
AND U = empty
AND R subset_of P
AND P subset_of Closure_f(R union O*)
AND Predicates(P) intersection F = empty
AND ActorsMatch(P,C)
AND SurfaceValuesMatch(P,C)
AND TemporalFrameMatch(P,C)
```

`U` contains every non-style fragment the parser cannot classify. `Closure_f` contains only registered entailments such as “down to eight tenths” implying the selected current gap claim; it never adds cause, emotion, intention or outcome. Negation is a claim operator, not ignored punctuation.

## Tight output language

- One sentence in the first production slice; 2–240 normalized characters and at most 32 lexical tokens. Catalog may set lower bounds.
- No headings, quotes, markdown, JSON, speaker labels, questions, first person, imperatives, model commentary or `<think>` residue.
- Exactly the bound hero/target aliases and pronouns from `SurfaceLexicon`; unknown proper nouns, car numbers and positions reject.
- Every numeric/ordinal/time value must match a BeatPlan-generated `SurfaceValueSet`. Examples such as `0.8 seconds`, `eight tenths` and a declared band phrase are equivalent only when precomputed from the same fact. The verifier does not use an open numeric tolerance.
- Comparatives and relation verbs are directional. `hero closes on target` cannot satisfy `target closes on hero`; passive voice is disabled unless that family grammar declares and tests the actor mapping.
- Current, projected and historical modalities have separate tokens. `could`, `projected` or `on course for` cannot become a completed result; a completed result cannot be softened into an unsupported prediction.
- Style tokens may alter cadence, connective and approved non-semantic verbs only. Emotion, driver intent, blame, strategy, certainty, medical interpretation and causal explanation are semantic and require claims; the baseline contains no such optional inference claims.

## Compiler-owned surface data

Before Qwen is called, the prompt compiler creates the exact `realization-bundle/2` object frozen in `schema-contracts.md`. Its SurfaceLexicon contains:

```text
surfaceValueSets, relationLexemes, connectives, forbiddenLexemes
```

Actor aliases live in the bundle's separate collision-free `actorBindings`; selected AtomicFact copies live in `factBindings`. The verifier receives this exact immutable bundle and hashes; it never reconstructs values from current mutable telemetry. Number expansion, rounding, unit pluralization and ordinal rendering are pure shared functions tested once and reused by authored and Qwen paths. A response is evaluated only after the actor proves that every bound AtomicFact remains canonical-equal/current in its newest FactView and that occurrence, lineage and episode revision still match.

## Common rejection codes

`empty`, `too_long`, `sentence_count`, `token_count`, `non_en_contract`, `meta_output`, `unknown_fragment`, `unknown_entity`, `actor_reversed`, `actor_ambiguous`, `number_unbound`, `number_mismatch`, `unit_mismatch`, `polarity_mismatch`, `tense_mismatch`, `required_missing`, `forbidden_claim`, `extra_claim`, `causal_inference`, `intent_inference`, `emotion_inference`, `medical_inference`, `prediction_as_result`, `result_as_prediction`, `unsupported_certainty`, `unsafe_negation`.

These are verifier reason IDs and must be added to the common machine registry. A rejection response may list multiple codes but exposes at most 16, sorted by first text offset then code.

## Family coverage matrix

Each row declares the parser's core relation frame and additions forbidden beyond the global contract. The exact per-beat required/forbidden claims remain in `event-beat-disposition.md`.

| Realization family | Required parse frame / direction | Additional hard rejects |
| --- | --- | --- |
| `timing.lap_result` | hero + completed/PB result; bound lap/time/reference only when selected | session/field best, invented improvement |
| `timing.delta` | hero + improved/worsened polarity + bound delta/reference | cause, reversed gain/loss, finished result |
| `timing.sector` | hero + sector identity + split/best polarity | lap/PB substitution, wrong sector |
| `timing.target` | hero pursuing timing/position target with bound gap | achieved result, named race pass |
| `timing.projection` | hero + explicit projected modality + projected time/position | completed-result grammar, certainty |
| `timing.attempt` | hero + current active attempt | predicted or completed result |
| `timing.consistency` | hero + exact clean-lap count | whole-session cleanliness, psychological judgement |
| `battle.closing` | ordered closer→target + trend/material band; gap if selected | pass/contact/outcome, reversed actors |
| `battle.attack` | ordered hero→target + current attack-range band | completed pass or inevitability |
| `battle.overlap` | ordered hero/target pair + simultaneous side-by-side state | winner, contact or result |
| `battle.pressure` | ordered rear target→hero + threat/closing relation | hero as hunter, inevitable loss |
| `battle.two_front` | hero→front and rear→hero as two distinct relations | actor collapse, one-sided claim presented as both |
| `battle.outcome` | hero/target + won outcome | pass mechanism unless selected |
| `position.pass` | ordered passer→passed + old/new order | contact/cause, leader claim unless selected |
| `position.change` | hero + old/new ordinal + gained/lost polarity | named opponent or mechanism unless selected |
| `position.leader` | old leader→new leader | hero involvement unless one bound actor is hero |
| `incident.event` | hero incident; optional off-track only for classified branch | contact, damage, blame or cause |
| `incident.invalid_lap` | hero + invalid current lap | incident cause or penalty consequence |
| `incident.aftermath` | hero + exact current aftermath state | recovery/damage conclusion |
| `incident.recovery` | hero + resumed motion + known surface state | no-damage/full-recovery claim |
| `pit.lifecycle` | hero + exact phase + pit-cycle identity | skipped future phase, service/strategy inference |
| `pit.outcome` | hero + entry/exit comparison and polarity | strategy/cause judgement |
| `stream.lifecycle` | stream epoch + started reason | invented prior history/session stage |
| `session.intro` | current occurrence + exact stage | other stage as current; inherited fact without past marker |
| `session.restart` | stage + old/new occurrence relation | stream restart, cause |
| `session.wrap` | ended occurrence + exact stage/reason | unsupported result or future-stage certainty |
| `session.preview` | next actually present stage | absent/skipped stage, schedule certainty |
| `session.flag` | exact flag transition/scope or checkered state | incident cause, start/finish result unless selected |
| `session.final_lap` | hero + exact final-lap identity | finish position/result |
| `session.finish` | hero + observed finish position; class position only if selected | official/final classification without final fact |
| `session.recap` | past qualifying occurrence + selected result/time | race/grid certainty |
| `session.context` | exactly one selected field/SoF fact and scope | quality/result prediction |
| `session.weather` | selected current/change weather predicates with temporal polarity | forecast, cause, unobserved track effect |
| `session.vehicle` | hero entered car + exact current stage/occurrence | lap/pace/start result |
| `bio.context` | hero + measured HR band/freshness only | emotion, stress, health, cause or performance effect |
| `filler.track_state` | exact vehicle/broadcast phase + one selected stable fact | invented event, urgency, prediction |
| `filler.off_track` | exact lobby/garage context + one selected stable fact | on-track action or active-session claim |

The loader must prove all 64 beats resolve to one of these 37 rows. Every row has one concrete accepted commentary utterance plus isolated actor/polarity, value/unit, temporal, forbidden-addition and unknown-fragment counterexamples. The machine checker evaluates each expected semantic reason; it does not accept prose parse-frame descriptions as sample utterances.

## Authored versus Qwen

- Critical lifecycle/results default to authored patterns until their Qwen family holdout is separately promoted.
- Authored text is not trusted merely because it is in source control; catalog load validates its placeholders and CI runs it through the same family parser with representative bindings.
- Qwen receives only the selected semantic frame, one tight pattern or approved family pool, immutable RealizationBundle surface/bindings and relevant family rules. It never receives the full graph, mutable FactLedger/FactView, unrelated telemetry, current config or prior hidden chain of thought.
- One transport attempt is allowed. Invalid transport/content/verification suppresses the beat revision and returns control to the director.

The literal base/output prompt blocks, canonical DATA projection, UTF-8 bounds, exact OpenAI-compatible SSE body/parser, request/result identity, actor deadline and latency equations are normative in [the Qwen transport contract](qwen-transport-contract.md). Family grammar/card content comes from this document and the catalog, but transport code cannot add examples, repair context or prior text.

## Promotion gates

For each family/profile/backend combination, a versioned corpus must include valid cases and counterfactual actor, polarity, number, staleness, forbidden outcome/cause and unknown-fragment cases. The first production slice admits only `tight`.

Promotion requires:

- zero accepted material hallucinations/reversed actors on the release-blocking corpus and holdout;
- all required-claim omissions rejected;
- measured false-reject rate and warm/cold TTFT/total latency reported, not hidden by retries;
- P90 total Qwen time below the configured timeout with documented headroom on target hardware;
- catalog/verifier/prompt/model hashes recorded in NarrativeTape.

Because the existing local test measured warm total median/P90/max about 0.53/0.86/1.04 seconds and cold start about 3.46 seconds, the proposed 1.5-second request timeout is acceptable only after successful warm-up. Warm-up failure marks Qwen unavailable and makes Qwen-backed beats ineligible; it does not repeatedly spend cold-start latency during live arbitration. Numeric values remain estimated until the release corpus is rerun.

## Required fixtures

The design gate remains closed until branch-only fixtures provide:

1. one schema/grammar definition for every family row;
2. generated SurfaceValueSet cases for times, gaps, deltas, positions, laps and names;
3. at least four enabled audited EN pattern cards per beat (minimum 256 total), with unusable legacy strings explicitly rejected rather than migrated blindly;
4. family positive/counterexample corpus and expected reason codes;
5. the exact Qwen prompt/profile/version, request/SSE goldens and repeatable latency runner from `qwen-transport-contract.md`;
6. proof that no verifier path calls an embedding or another LLM as a hard fact gate.

The branch-only evidence is `machine/realization-contract.json`, `machine/realization-pattern-cards.json`, `machine/realization-corpus.json`, `machine/qwen-transport-goldens.json` and their checker/mutation set. It materializes all 37 tight grammars, four enabled audited cards for each of 64 beats, 222 family corpus cases, six closed surface-value sets, complete authored/Qwen common requests, canonical prompt/request bytes, thirteen SSE fixtures and four deadline races. The SSE set includes incremental split-UTF-8 decoding and exact visible/frame/stream overflow reasons. `machine/run_qwen_latency.py` is the no-proxy/no-redirect, no-retry warm/cold measurement runner; target-machine results remain a post-implementation release gate rather than a reason to widen this grammar.
