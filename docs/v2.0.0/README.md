# v2.0.0 narrative runtime — issue index

**Status:** design-freeze in progress; runtime gate closed by #235
**Umbrella:** [#234 — v2: narrative runtime master plan](https://github.com/Buchtanen/ir-obs-switcher/issues/234)
**Milestone:** [v2.0.0](https://github.com/Buchtanen/ir-obs-switcher/milestone/2)
**Specification:** [Commentary narrative runtime](../commentary_narrative_runtime_spec.md)
**Design-freeze audit:** [Pre-implementation contract gate](design-freeze-audit.md)
**Event/beat disposition:** [60 identifiers → 64 BeatDefinitions](event-beat-disposition.md)
**Public contracts:** [Exact v2 config, migration and HTTP shapes](public-contracts.md)
**Actor transitions:** [Single mailbox, lane, overflow, reset and shutdown contract](actor-transition-contract.md)
**Schemas and IDs:** [DTO fields, versions, identity/nullability and reason registry](schema-contracts.md)
**Facts/features/channels:** [Closed predicates, units, allowlists, feature IDs and tape taxonomy](fact-feature-registry.md)
**Detector catalog:** [Temporal math, estimated parameter ranges, hysteresis and two-front contract](detector-catalog-freeze.md)
**Realization/verifier:** [Controlled EN, all 37 families, rejects and promotion gates](realization-verifier-contract.md)
**Qwen transport:** [Exact prompt, request/result, SSE, timeout and latency contract](qwen-transport-contract.md)
**Machine freeze artifacts:** [Generated registries, DTO/beat/detector/graph/loader/config/API/actor schemas, goldens, mutation fixtures, checkers and V4 wire golden](machine/README.md)
**Frozen slice fixtures:** [Forty-four expected reducer/director/speech/config/realization/TTS scenarios](vertical-slice-fixtures.md)
**Final-PR exclusions:** [Planning and temporary mechanism removal gate](final-pr-exclusion-manifest.md)
**Baseline:** `master@0ce75d4`

This index covers the complete refactor, not only the first vertical slice. Each linked issue contains atomic tasks, acceptance criteria, verification requirements and docs/config impact. GitHub issue state is authoritative; checkboxes here are a release-planning mirror and are updated from evidence committed on the v2 development branch.

## Delivery rules

- Titles use the `v2:` prefix and all issues belong to milestone `v2.0.0`.
- Complete and close the design-freeze gate in #235 before the first runtime behavior edit.
- Implement in dependency order on the single v2 branch; temporary legacy/shadow comparison must not survive the final cutover.
- Behavior changes require focused pytest/replay evidence; docs-only work must state its TDD exception.
- Estimated detector thresholds may start conservatively without a prior corpus, but remain versioned and shadow/opt-in until tested.
- EN is the only v2 speech locale.
- The runtime holds at most one in-flight utterance and no prepared speech waiter.
- Speakable event meaning may wait only as bounded metadata with TTL, priority, penalty and a mandatory `tape_channel`.
- Existing V4 EventEnvelope/overlay wire remains unchanged; commentary uses an internal NarrativeEvent adapter and catalog lookup.
- Event kick-rate is measured at a read-only pre-arbitration candidate tap linked to DetectorObservation where applicable. Typed facts remain authoritative world truth, but only accepted events or the explicit silence lifecycle may open/revise speakable episodes or create opportunities; fact updates may only invalidate/close them.
- After every beat, event opportunities compete with natural story successors in one deterministic director pass.
- Opportunity consumption occurs at backend playback acceptance (`SPEECH_STARTED`), not at selection or an unverifiable physical audio-frame boundary.
- `tight` is the only prompt profile allowed in the first production slice.
- Issues #280–#281 are offline follow-ups and do not block the v2 runtime release unless explicitly promoted.
- No planning specification/index/audit/disposition/public-contract freeze file is included in the final PR to `master`; actual behavior/config/API/migration docs remain mandatory.
- A child issue may close from verified branch work when its dev diary records the pushed commit SHA; #279 and #234 remain integration/release gates.

## Wave A — contracts, configuration and recording

- [ ] [#235 — v2: architecture contracts and dependency-direction ADR](https://github.com/Buchtanen/ir-obs-switcher/issues/235) — mandatory design-freeze gate; no runtime behavior edit may precede closure.
- [ ] [#236 — v2: versioned IDs, clocks, units and schema primitives](https://github.com/Buchtanen/ir-obs-switcher/issues/236) — depends on #235.
- [ ] [#237 — v2: single ordered narrative event stream](https://github.com/Buchtanen/ir-obs-switcher/issues/237) — depends on #236; preserves V4 overlay wire and introduces the internal NarrativeEvent/command boundary.
- [ ] [#238 — v2: configuration and migration contract](https://github.com/Buchtanen/ir-obs-switcher/issues/238) — frozen breaking config/migration contract; no public legacy runtime flag.
- [ ] [#239 — v2: NarrativeTape schema and stream manifest](https://github.com/Buchtanen/ir-obs-switcher/issues/239) — depends on #236, #237; includes pre-arbitration DetectorObservation/EventCandidateTap and fixed funnel identities/boundaries.
- [ ] [#240 — v2: bounded asynchronous NarrativeTape writer](https://github.com/Buchtanen/ir-obs-switcher/issues/240) — depends on #239.
- [ ] [#241 — v2: trigger-driven CapturePlan compiler](https://github.com/Buchtanen/ir-obs-switcher/issues/241) — depends on #238–#240.
- [ ] [#242 — v2: replay reader, label sidecars and evaluation reports](https://github.com/Buchtanen/ir-obs-switcher/issues/242) — depends on #239, #240.

## Wave B — timeline and factual state

- [ ] [#243 — v2: authoritative StreamTimeline lifecycle reducer](https://github.com/Buchtanen/ir-obs-switcher/issues/243) — depends on #235–#237; owns exact `(SubSessionID, SessionNum)` identity and transition precedence.
- [ ] [#244 — v2: session occurrence and lineage branching](https://github.com/Buchtanen/ir-obs-switcher/issues/244) — depends on #243.
- [ ] [#245 — v2: typed AtomicFact ledger and provenance](https://github.com/Buchtanen/ir-obs-switcher/issues/245) — depends on #236, #244.
- [ ] [#246 — v2: fact inheritance, supersession and summaries](https://github.com/Buchtanen/ir-obs-switcher/issues/246) — depends on #245.

## Wave C — features and triggers

- [ ] [#247 — v2: typed FeatureEngine registry and bounded windows](https://github.com/Buchtanen/ir-obs-switcher/issues/247) — depends on #236, #237, #245.
- [ ] [#248 — v2: versioned gap estimator and validity rules](https://github.com/Buchtanen/ir-obs-switcher/issues/248) — depends on #247.
- [ ] [#249 — v2: safe typed predicate AST](https://github.com/Buchtanen/ir-obs-switcher/issues/249) — depends on #236, #247.
- [ ] [#250 — v2: generic correlated detector lifecycle FSM](https://github.com/Buchtanen/ir-obs-switcher/issues/250) — depends on #241, #247, #249.
- [ ] [#251 — v2: direct lap and sector edge triggers](https://github.com/Buchtanen/ir-obs-switcher/issues/251) — depends on #237, #243, #250.
- [ ] [#252 — v2: stream and session lifecycle triggers](https://github.com/Buchtanen/ir-obs-switcher/issues/252) — depends on #243, #244, #250.
- [ ] [#253 — v2: CLOSING temporal detector](https://github.com/Buchtanen/ir-obs-switcher/issues/253) — depends on #241, #248–#250.
- [ ] [#254 — v2: UNDER_PRESSURE temporal detector](https://github.com/Buchtanen/ir-obs-switcher/issues/254) — depends on #241, #248–#250.
- [ ] [#255 — v2: composite two-front battle detector](https://github.com/Buchtanen/ir-obs-switcher/issues/255) — depends on #253, #254.
- [ ] [#256 — v2: v2 event-family coverage matrix](https://github.com/Buchtanen/ir-obs-switcher/issues/256) — depends on #235, #236; audits all 60 identifiers and the 64-beat baseline.

## Wave D — episodes, beats and direction

- [ ] [#257 — v2: StoryDefinition schema and catalog loader](https://github.com/Buchtanen/ir-obs-switcher/issues/257) — depends on #249, #256.
- [ ] [#258 — v2: lineage-aware EpisodeRegistry](https://github.com/Buchtanen/ir-obs-switcher/issues/258) — depends on #244, #245, #257.
- [ ] [#259 — v2: resolved-episode retention without speech queue](https://github.com/Buchtanen/ir-obs-switcher/issues/259) — depends on #258.
- [ ] [#260 — v2: long-silence lifecycle and filler opportunities](https://github.com/Buchtanen/ir-obs-switcher/issues/260) — depends on #237, #245, #252, #257.
- [ ] [#261 — v2: immutable BeatPlan and just-in-time planner](https://github.com/Buchtanen/ir-obs-switcher/issues/261) — depends on #246, #258–#260.
- [ ] [#263 — v2: ExposureStore and decay-based fatigue](https://github.com/Buchtanen/ir-obs-switcher/issues/263) — depends on #236, #237, #258 and precedes #283/#262 to avoid a dependency cycle.
- [ ] [#283 — v2: expiring event opportunities and post-beat arbitration](https://github.com/Buchtanen/ir-obs-switcher/issues/283) — depends on #237, #239, #241, #257–#259, #261 and #263; owns TTL/priority/penalty, `tape_channel` and event-versus-successor policy.
- [ ] [#262 — v2: StoryDirector eligibility and deterministic arbitration](https://github.com/Buchtanen/ir-obs-switcher/issues/262) — depends on #261, #283.

## Wave E — speech, realization and verification

- [ ] [#264 — v2: single in-flight speech lane with no prepared waiter](https://github.com/Buchtanen/ir-obs-switcher/issues/264) — depends on #237, #259, #261, #283; owns backend acknowledgement and non-preemptive race-event policy.
- [ ] [#265 — v2: freshness commit gate v2](https://github.com/Buchtanen/ir-obs-switcher/issues/265) — depends on #244, #245, #258, #261, #264, #283.
- [ ] [#266 — v2: EN-only RealizationCatalog and migration classifier](https://github.com/Buchtanen/ir-obs-switcher/issues/266) — depends on #236, #256, #257.
- [ ] [#267 — v2: authored critical and lifecycle realization pack](https://github.com/Buchtanen/ir-obs-switcher/issues/267) — depends on #261, #266.
- [ ] [#268 — v2: dynamic compiled PromptOptions and prompt profiles](https://github.com/Buchtanen/ir-obs-switcher/issues/268) — depends on #261, #266.
- [ ] [#269 — v2: bounded Qwen transport and warm-up](https://github.com/Buchtanen/ir-obs-switcher/issues/269) — depends on #238, #264, #268.
- [ ] [#270 — v2: family-specific SemanticVerifier](https://github.com/Buchtanen/ir-obs-switcher/issues/270) — depends on #261, #266, #268.
- [ ] [#271 — v2: LLM evaluation corpus and latency report](https://github.com/Buchtanen/ir-obs-switcher/issues/271) — depends on #239, #242, #269, #270.

## Wave F — integration and operation

- [ ] [#284 — v2: single-owner NarrativeRuntime actor and command lifecycle](https://github.com/Buchtanen/ir-obs-switcher/issues/284) — owns mailbox ordering, effects, recovery and shutdown; depends on #237, #238, #240, #243, #245, #258, #262, #264, #265 and #269.
- [ ] [#272 — v2: legacy-to-v2 adapter and shadow comparison](https://github.com/Buchtanen/ir-obs-switcher/issues/272) — temporary branch-only harness after #284, removed before final PR.
- [ ] [#273 — v2: v2 health, observability and operator configuration](https://github.com/Buchtanen/ir-obs-switcher/issues/273) — depends on #238–#241, #269, #272, #283 and #284; owns exact public golden payloads.

## Wave G — complete event-family migration

- [ ] [#274 — v2: migrate race outcome event families](https://github.com/Buchtanen/ir-obs-switcher/issues/274) — position/pass/overtake/leader/finish.
- [ ] [#275 — v2: migrate lap, sector, practice and qualifying families](https://github.com/Buchtanen/ir-obs-switcher/issues/275) — timing and inherited recaps.
- [ ] [#276 — v2: migrate pit, incident, flag and recovery families](https://github.com/Buchtanen/ir-obs-switcher/issues/276) — stateful operational stories.
- [ ] [#277 — v2: migrate session, filler, weather, field and bio families](https://github.com/Buchtanen/ir-obs-switcher/issues/277) — non-race-event commentary.
- [ ] [#278 — v2: production vertical-slice end-to-end acceptance](https://github.com/Buchtanen/ir-obs-switcher/issues/278) — internal live checkpoint, not a partial release; includes #283 evidence.
- [ ] [#282 — v2: v2 documentation, operator runbook and maintenance contract](https://github.com/Buchtanen/ir-obs-switcher/issues/282) — versioned delivery documentation.
- [ ] [#279 — v2: complete catalog migration and v2.0.0 release cutover](https://github.com/Buchtanen/ir-obs-switcher/issues/279) — atomic breaking PR, planning/temporary code exclusion and release-level rollback.

## Wave H — offline graph follow-ups

- [ ] [#280 — v2: offline StoryGraphAnalyzer](https://github.com/Buchtanen/ir-obs-switcher/issues/280) — optional rich diagnostics; mandatory loader graph-safety checks remain in #257.
- [ ] [#281 — v2: 3D beat graph projection and NarrativeTape viewer](https://github.com/Buchtanen/ir-obs-switcher/issues/281) — optional non-authoritative viewer.

## Legacy overlap map

These open issues remain independent until maintainers explicitly close or absorb them:

| Legacy issue | v2 successors |
| --- | --- |
| [#219 — Capture LLM polish pairs](https://github.com/Buchtanen/ir-obs-switcher/issues/219) | #239–#242, #271 |
| [#220 — Session-aware race stories](https://github.com/Buchtanen/ir-obs-switcher/issues/220) | #243–#246, #258 |
| [#222 — Dynamic LLM prompt profiles](https://github.com/Buchtanen/ir-obs-switcher/issues/222) | #268, #270, #271 |
| [#223 — Continuous multi-sentence commentary](https://github.com/Buchtanen/ir-obs-switcher/issues/223) | #259, #261, #264; v2 explicitly removes prepared-speech queues |
| [#233 — VOD coverage integration](https://github.com/Buchtanen/ir-obs-switcher/issues/233) | #271, #274, #278 |

## Release gates

- [ ] All blocking issues #235–#279 and #282–#284 are closed or explicitly waived in #234 with evidence.
- [ ] Event coverage matrix #256 has no unclassified one of the 60 known master identifiers and validates all 64 beats.
- [ ] Detector and LLM evidence is reproducible from versioned tape; no released production detector has `tuning.required`.
- [ ] Per-`tape_channel` kick, queue, selection, expiry and spoken cadence is reproducible from tape.
- [ ] All active speech is EN-only and uses no prepared waiter.
- [ ] Full CI, Windows live test and rollback drill pass.
- [ ] Release PR uses `semver:major` and documents config/API migration.
