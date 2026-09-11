# #278 Vertical-slice acceptance

**Status:** Slice 14 — offline feature-order + bucket-coverage drivers for F28 (no live Windows §24.9 GO).

## Slice 1 — frozen projection harness

| Contract | Value |
| --- | --- |
| Machine fixtures | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (**44** / F01–F44) |
| Executable expectations | **248** |
| Boundary calculations | **14** |
| Fail-closed mutations | **16** (`vertical-slice-mutations.json`) |
| Builder | `docs/v2.0.0/machine/build_vertical_slice_fixtures.py` |
| Pytest consumer | `tests/test_vertical_slice_fixtures.py` |

**AC locks (Slice 1):**
- Frozen artifacts match builder (`validate_all` / canonical equality).
- Mutations remain fail-closed.
- Gap inventory records **6/44** named unit-test touchpoints; **38** remain unwired for later runtime slices.
- Does **not** rewrite `machine/*` hashes; does **not** claim live speech or §24.9 GO.

## Slice 2 — F08/F15/F24 expiry runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F08` (speaking critical / no prepared queue), `F15` (fact-only invalidation), `F24` (half-open TTL + mailbox skip) |
| Pytest | `tests/test_vertical_slice_expiry_runtime.py` |
| Inventory | **9/44** wired; **35** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 2):**
- Machine projection for F08/F15/F24 still matches frozen expectations/calcs.
- Runtime drivers prove no barge-in / no prepared queue, fact-only silence path, half-open expiry without fallback.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 3 — F02/F03/F04 transition runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F02` (canonical P0>Q0>R0 inheritance), `F03` (Race→Qualifying rewind), `F04` (confirmed same-session restart) |
| Pytest | `tests/test_vertical_slice_transition_runtime.py` |
| Inventory | **12/44** wired; **32** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 3):**
- Machine projection for F02/F03/F04 still matches frozen expectations.
- Runtime drivers prove lineage inheritance, ordered rewind without `SESSION_REWOUND`, speech cancel on occurrence reset, and confirmed restart without false positives.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 4 — F05/F06/F07 director scoring runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F05` (first pursuit / controlled open score), `F06` (related continuation preference), `F07` (inclusive switch margin) |
| Pytest | `tests/test_vertical_slice_scoring_runtime.py` |
| Inventory | **15/44** wired; **29** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 4):**
- Machine projection for F05/F06/F07 still matches frozen expectations/calcs (`score_70` / `score_76` / margin boundaries).
- Runtime drivers prove threshold open without V4 priority term, related successor over weather filler, and inclusive switch margin (82 holds / 84 switches).
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 5 — F01/F10/F17 stream + silence runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F01` (stream before session), `F10` (long-silence filler threshold), `F17` (lobby stream-scope filler) |
| Pytest | `tests/test_vertical_slice_silence_runtime.py` |
| Inventory | **18/44** wired; **26** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 5):**
- Machine projection for F01/F10/F17 still matches frozen expectations/calcs (`score_36` / threshold gte).
- Runtime drivers prove null session identity on stream start, 24+12 silence pressure selecting filler, and lobby filler limited to stream facts with missing-track rearm.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 6 — F23/F37 director policy runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F23` (fatigue / order / story cap one formula), `F37` (switch policy vs urgency sort / filler) |
| Pytest | `tests/test_vertical_slice_policy_runtime.py` |
| Inventory | **20/44** wired; **24** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 6):**
- Machine projection for F23/F37 still matches frozen expectations/calcs (half-life 0.5 / effective cap 2).
- Runtime drivers prove base-2 fatigue, stable `(40,3)` order, cadence cap with closing escape, inclusive margin switch, lower-urgency switch, critical priority, filler fallback-only, and inclusive replacement breakdown.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 7 — F21/F42 partition + silence-origin runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F21` (lossless 64/64/2 context partition), `F42` (one silence origin across opening/busy/inactive) |
| Pytest | `tests/test_vertical_slice_partition_silence_runtime.py` |
| Inventory | **22/44** wired; **22** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 7):**
- Machine projection for F21/F42 still matches frozen expectations/calcs (`partition` → `[64,64,2]`).
- Runtime drivers prove protected/ordinary partition boundaries, source-order preservation, three planning impulses, and silence arm/cancel/rearm/stale/config-next-arm locks.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 8 — F09/F11 Qwen hard-fail runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F09` (invalid Qwen output / distinct cycle attempt), `F11` (cold Qwen hard-ineligible) |
| Pytest | `tests/test_vertical_slice_qwen_runtime.py` |
| Inventory | **24/44** wired; **20** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 8):**
- Machine projection for F09/F11 still matches frozen expectations.
- Runtime drivers prove actor-reversed suppress + reservation release, distinct attempt 2 then cycle exhaust, and cold Qwen hard ineligibility without cold-timeout spend or backend rewrite while authored may win.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.


## Slice 9 — F13/F20 mailbox overflow + manual admission runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F13` (protected mailbox overflow / ordinary eviction first), `F20` (manual admission timeout / no delayed audio) |
| Pytest | `tests/test_vertical_slice_mailbox_manual_runtime.py` |
| Inventory | **26/44** wired; **18** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 9):**
- Machine projection for F13/F20 still matches frozen expectations.
- Runtime drivers prove ordinary eviction before emergency recovery with latest projection and incomplete history, non-blocking producer admits, and manual abandon-vs-claim linearization where timeout cannot produce delayed audio.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.


## Slice 10 — F12/F29 manual-disabled + offline lexicon runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F12` (manual speak while automatic commentary disabled), `F29` (offline actor lexicon validation) |
| Pytest | `tests/test_vertical_slice_manual_lexicon_runtime.py` |
| Inventory | **28/44** wired; **16** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 10):**
- Machine projection for F12/F29 still matches frozen expectations.
- Runtime drivers prove manual 202 with no narrative planning state, second-request busy, race truth without barge-in, and offline lexicon complete-parse / invalid-400 / actor-reversal locks without live reads.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.


## Slice 11 — F32/F38 facts-capacity + realization freshness runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F32` (bounded facts/episodes fail unknown, never false), `F38` (realization input frozen; freshness compares exact facts) |
| Pytest | `tests/test_vertical_slice_facts_freshness_runtime.py` |
| Inventory | **30/44** wired; **14** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 11):**
- Machine projection for F32/F38 still matches frozen expectations.
- Runtime drivers prove update-without-growth, deterministic fact eviction to unknown-not-false, pinned exhaustion without partial publish, degraded recover, episode eviction order, pinned reject, and frozen-bundle freshness equal/alias/stale/malformed/hash locks.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 12 — F18/F33 context-cut + prompt-freedom runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F18` (context batch is a coherent fact/event cut), `F33` (prompt freedom is a deterministic safety clamp) |
| Pytest | `tests/test_vertical_slice_context_prompt_runtime.py` |
| Inventory | **32/44** wired; **12** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 12):**
- Machine projection for F18/F33 still matches frozen expectations/calcs (canonical seed `16041955996680716084`).
- Runtime drivers prove apply-88 / mismatch reject / no old-view lookup / no batch merge / apply-89 one director, plus closed profiles, least-permissive clamp, tight baseline, safe promotion, canonical seed, card-or-fatigue, and failure-never-widens.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Slice 13 — F14/F35 playback-race + planning-replace runtime drivers

| Contract | Value |
| --- | --- |
| Fixtures | `F14` (playback acknowledgement races reset), `F35` (real new event replaces into a new planning cycle) |
| Pytest | `tests/test_vertical_slice_playback_replace_runtime.py` |
| Inventory | **34/44** wired; **10** unwired |
| Machine hashes | unchanged |

**AC locks (Slice 13):**
- Machine projection for F14/F35 still matches frozen expectations.
- Runtime drivers prove reset-then-stale-accept stays unconsumed, accept-then-reset interrupts exposed speech, reducer sequence authority, replace-without-suppression, close cycle N / open N+1 attempt 1, one alternative, lower/pure fact does not replace, accepted events only.
- Does **not** claim live §24.9 GO; CONFIG/API unchanged.

## Later slices

- Runtime NarrativeRuntime drivers for remaining F scenarios.
- Live Windows/iRSDK/OBS/Ollama/TTS §24.9 gates.
