# Commentary microplans — implementation evidence

Issue: #208  
Branch: `feat/commentary-style-card-microplans`

## Delivered scope

- `commentary-microplan/1` separates story selection and factual propositions from language realization.
- `commentary-facts/3` sends only selected facts, actor direction, time frame and one compatible style card. It does not send unrelated telemetry or the authored anchor.
- The canonical fallback is built from required propositions, so a model outage cannot fall back to generic copy that omits the event fact.
- Normal execution uses one model call. One hard semantic rejection may use one shorter safety request; transport errors and timeout do not repeat an identical call.
- Validator authority is the selected fact set. P/S tokens are parsed before proper-name checks, decimal precision is preserved, and two-front actions are checked against their actor roles.
- Style warnings do not spend another inference. Safe terminal punctuation is normalized deterministically.
- Non-positive/non-finite source gaps, zero deltas and non-positive positions do not enter selected fact text. A zero provisional SoF is omitted.

## Verification

Deterministic focused suite after implementation: 75 tests (composer, graph, polish, session briefs, config and new microplan regressions).

Local Ollama `qwen3:4b-instruct-2507-q4_K_M` checks after prompt/card correction:

- Three two-front style cards, three runs each: 9/9 accepted on the first call, 0 fallbacks, three materially distinct outputs, median 453 ms after warm-up.
- Position-gain, rear-pressure and two-front sample: 6/6 first-call acceptance. Median 453 ms after warm-up.
- A prior experiment exposed two actor-direction mistakes which the old relation-wide check accepted. Those samples became regression tests and the examples/validator were tightened before recording the 9/9 result above.
- Cold model starts remain an external latency source: observed cold requests of roughly 4.7–6.8 s. Warm requests were typically 0.2–0.7 s. No retry policy can remove model-loading latency.

Example variants for identical two-front facts:

1. `He attacks Gjoel ahead, with Meyer applying pressure behind.`
2. `He attacks Gjoel up front, while Meyer keeps the pressure on from behind.`
3. `Meyer pressures him from behind while his attack targets Gjoel ahead.`

## Remaining integration

The microplan already carries source correlation, run epoch and revision. The editorial MiniStory registry/commit authority will consume these fields in the dependent lifecycle phase. Full tape-corpus acceptance remains the integration gate after relation, epoch and chapter work is merged.
