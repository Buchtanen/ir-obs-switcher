# Testy, CI, release

- Pytest: `./run_tests.sh` / `run_tests.ps1`.
- CI: `.github/workflows/ci.yml` — ruff, black, mypy, tests+coverage (blocking).
- PR do `master`: přesně jeden `semver:*` label (`RELEASE_POLICY.md`). Check `semver-label` na `opened` počká na label z API (~60 s); nepíše ho. Policy: `scripts/check_semver_label.py`, testy `tests/test_semver_label.py`.
- Verze se nebumpuje v běžném PR. Release Please.

Index testů je prefix `tests/test_<oblast>.py`, ne historický `tests.md` katalog počtů.

## #278 vertical-slice fixture pytest harness (Slice 1)

**Status:** offline consumer on branch `cursor/vertical-slice-fixtures-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (**5** tests) |
| Acceptance doc | [vertical-slice-acceptance.md](../../v2.0.0/vertical-slice-acceptance.md) |
| Prose + F01–F44 spec | [vertical-slice-fixtures.md](../../v2.0.0/vertical-slice-fixtures.md) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` |
| Fail-closed mutations | `docs/v2.0.0/machine/vertical-slice-mutations.json` |
| Builder / validator | `docs/v2.0.0/machine/build_vertical_slice_fixtures.py` |

**Slice 1 locks:** frozen JSON matches builder output; **16** mutations stay fail-closed; gap inventory records **6/44** scenarios with adjacent unit-test touchpoints at Slice 1 land (**38** unwired then; superseded by Slice 2 inventory below).

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**.

Lookup: [inflight § #278 slice 1](../inflight/README.md#278-vertical-slice-fixtures-slice-1-lookup) · [acceptance § Slice 1](../../v2.0.0/vertical-slice-acceptance.md#slice-1--frozen-projection-harness) · [dokumentace index](../README.md).

## #278 vertical-slice expiry runtime (Slice 2)

**Status:** offline F08/F15/F24 drivers on branch `cursor/vertical-slice-expiry-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_expiry_runtime.py`](../../../tests/test_vertical_slice_expiry_runtime.py) (**6** tests: **3** parametrized machine projection + F08/F15/F24 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **9/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 2](../../v2.0.0/vertical-slice-acceptance.md#slice-2--f08f15f24-expiry-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F08/F15/F24 rows; hashes **unchanged**) |

**Slice 2 locks:** F08 speaking-critical / no prepared queue; F15 fact-only invalidation silence; F24 half-open TTL + mailbox skip; machine projection still matches frozen expectations/calcs; gap inventory **9/44** wired, **35** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 2](../inflight/README.md#278-vertical-slice-expiry-runtime-slice-2-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice transition runtime (Slice 3)

**Status:** offline F02/F03/F04 drivers on branch `cursor/vertical-slice-transition-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_transition_runtime.py`](../../../tests/test_vertical_slice_transition_runtime.py) (**6** tests: **3** parametrized machine projection + F02/F03/F04 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **12/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 3](../../v2.0.0/vertical-slice-acceptance.md#slice-3--f02f03f04-transition-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F02/F03/F04 rows; hashes **unchanged**) |

**Slice 3 locks:** F02 canonical P0>Q0>R0 lineage inheritance; F03 ordered Race→Qualifying rewind without `SESSION_REWOUND`, speech cancel on occurrence reset; F04 confirmed same-session restart without false positives; machine projection still matches frozen expectations; gap inventory **12/44** wired, **32** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 3](../inflight/README.md#278-vertical-slice-transition-runtime-slice-3-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice scoring runtime (Slice 4)

**Status:** offline F05/F06/F07 drivers on branch `cursor/vertical-slice-scoring-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_scoring_runtime.py`](../../../tests/test_vertical_slice_scoring_runtime.py) (**7** tests: **3** parametrized machine projection + F05/F06/F07 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **15/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 4](../../v2.0.0/vertical-slice-acceptance.md#slice-4--f05f06f07-director-scoring-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F05/F06/F07 rows; hashes **unchanged**) |

**Slice 4 locks:** F05 opening pursuit score 70 clears threshold without V4 priority term; F06 related continuation preferred over weather filler; F07 inclusive switch margin (82 holds / 84 switches); machine projection still matches frozen expectations/calcs; gap inventory **15/44** wired, **29** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 4](../inflight/README.md#278-vertical-slice-scoring-runtime-slice-4-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice silence runtime (Slice 5)

**Status:** offline F01/F10/F17 drivers on branch `cursor/vertical-slice-silence-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_silence_runtime.py`](../../../tests/test_vertical_slice_silence_runtime.py) (**6** tests: **3** parametrized machine projection + F01/F10/F17 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **18/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 5](../../v2.0.0/vertical-slice-acceptance.md#slice-5--f01f10f17-stream--silence-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F01/F10/F17 rows; hashes **unchanged**) |

**Slice 5 locks:** F01 stream-before-session keeps null identity and arms silence only after terminal; F10 24+12 silence pressure selects filler and missing-fact path rearms full interval; F17 lobby filler stays stream-scoped with exact two facts and missing-track guard rearm; machine projection still matches frozen expectations/calcs; gap inventory **18/44** wired, **26** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 5](../inflight/README.md#278-vertical-slice-silence-runtime-slice-5-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice policy runtime (Slice 6)

**Status:** offline F23/F37 drivers on branch `cursor/vertical-slice-policy-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_policy_runtime.py`](../../../tests/test_vertical_slice_policy_runtime.py) (**4** tests: **2** parametrized machine projection + F23/F37 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **20/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 6](../../v2.0.0/vertical-slice-acceptance.md#slice-6--f23f37-director-policy-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F23/F37 rows; hashes **unchanged**) |

**Slice 6 locks:** F23 base-2 fatigue half-life, stable `(40,3)` order, effective story cap 2 with non-closing block and closing/critical escape; F37 inclusive margin switch, lower-urgency switch, critical priority, filler fallback-only, inclusive replacement 78, no non-event replace, full score breakdown; machine projection still matches frozen expectations/calcs; gap inventory **20/44** wired, **24** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 6](../inflight/README.md#278-vertical-slice-policy-runtime-slice-6-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice partition silence runtime (Slice 7)

**Status:** offline F21/F42 drivers on branch `cursor/vertical-slice-partition-silence-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_partition_silence_runtime.py`](../../../tests/test_vertical_slice_partition_silence_runtime.py) (**4** tests: **2** parametrized machine projection + F21/F42 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **22/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 7](../../v2.0.0/vertical-slice-acceptance.md#slice-7--f21f42-partition--silence-origin-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F21/F42 rows; hashes **unchanged**) |

**Slice 7 locks:** F21 lossless `[64,64,2]` partition with first two protected / last ordinary, same-revision idempotency, source order preserved, three planning impulses; F42 single silence origin across run arm, playback cancel, busy rearm, inactive no-credit, stale generation, and config-next-arm; machine projection still matches frozen expectations/calcs; gap inventory **22/44** wired, **22** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 7](../inflight/README.md#278-vertical-slice-partition-silence-runtime-slice-7-lookup) · [dokumentace index § #278](../README.md).

## #278 vertical-slice qwen runtime (Slice 8)

**Status:** offline F09/F11 drivers on branch `cursor/vertical-slice-qwen-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_qwen_runtime.py`](../../../tests/test_vertical_slice_qwen_runtime.py) (**4** tests: **2** parametrized machine projection + F09/F11 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **24/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 8](../../v2.0.0/vertical-slice-acceptance.md#slice-8--f09f11-qwen-hard-fail-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F09/F11 rows; hashes **unchanged**) |

**Slice 8 locks:** F09 actor-reversed suppress + reservation release, no retry/fallback, distinct attempt 2, cycle exhaust after second failure; F11 cold Qwen hard-ineligible without cold-timeout spend, authored may win, backend never rewritten to authored; machine projection still matches frozen expectations; gap inventory **24/44** wired, **20** unwired.

**Explicit non-goals:** no rewrite of frozen `machine/*` hashes; **`CONFIG.md` / `API.md` unchanged**; no live §24.9 GO.

Lookup: [inflight § #278 slice 8](../inflight/README.md#278-vertical-slice-qwen-runtime-slice-8-lookup) · [dokumentace index § #278](../README.md).

## Related

[RELEASE_POLICY.md](../../../RELEASE_POLICY.md), [scripts/README.md](../../../scripts/README.md) (`check_semver_label.py`), [VERSIONING.md](../../../VERSIONING.md), skill `pr-semver-label`.


## #278 vertical-slice mailbox/manual runtime (Slice 9)

**Status:** offline F13/F20 drivers on branch `cursor/vertical-slice-mailbox-manual-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_mailbox_manual_runtime.py`](../../../tests/test_vertical_slice_mailbox_manual_runtime.py) (**4** tests: **2** parametrized machine projection + F13/F20 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **26/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 9](../../v2.0.0/vertical-slice-acceptance.md#slice-9--f13f20-mailbox-overflow--manual-admission-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F13/F20 rows; hashes **unchanged**) |

**Slice 9 locks:** F13 ordinary eviction first, emergency recovery, latest projection, history incomplete, no lost opportunities, producer nonblocking; F20 abandon returns 503-class no audio, claim linearized 202-or-error, no narrative state, tape terminal decision, manual silence only; machine projection still matches frozen expectations; gap inventory **26/44** wired, **18** unwired.


## #278 vertical-slice manual/lexicon runtime (Slice 10)

**Status:** offline F12/F29 drivers on branch `cursor/vertical-slice-manual-lexicon-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_manual_lexicon_runtime.py`](../../../tests/test_vertical_slice_manual_lexicon_runtime.py) (**4** tests: **2** parametrized machine projection + F12/F29 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **28/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 10](../../v2.0.0/vertical-slice-acceptance.md#slice-10--f12f29-manual-disabled--offline-lexicon-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F12/F29 rows; hashes **unchanged**) |

**Slice 10 locks:** F12 manual 202 with no narrative planning state, second busy, race truth without barge-in; F29 only complete parses, invalid 400-class without live reads, reversal actor_reversed; machine projection still matches frozen expectations; gap inventory **28/44** wired, **16** unwired.


## #278 vertical-slice facts/freshness runtime (Slice 11)

**Status:** offline F32/F38 drivers on branch `cursor/vertical-slice-facts-freshness-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_facts_freshness_runtime.py`](../../../tests/test_vertical_slice_facts_freshness_runtime.py) (**4** tests: **2** parametrized machine projection + F32/F38 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **30/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 11](../../v2.0.0/vertical-slice-acceptance.md#slice-11--f32f38-facts-capacity--realization-freshness-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F32/F38 rows; hashes **unchanged**) |

**Slice 11 locks:** F32 update-without-growth, deterministic fact eviction, unknown-not-false, pinned exhaustion without partial, degraded recover, episode eviction order, pinned reject; F38 frozen bundle, equal facts pass, alias immutable, changed/missing stale, malformed rejected, hashes recorded; machine projection still matches frozen expectations; gap inventory **30/44** wired, **14** unwired.


## #278 vertical-slice context/prompt runtime (Slice 12)

**Status:** offline F18/F33 drivers on branch `cursor/vertical-slice-context-prompt-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_context_prompt_runtime.py`](../../../tests/test_vertical_slice_context_prompt_runtime.py) (**4** tests: **2** parametrized machine projection + F18/F33 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **32/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 12](../../v2.0.0/vertical-slice-acceptance.md#slice-12--f18f33-context-cut--prompt-freedom-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F18/F33 rows; hashes **unchanged**) |

**Slice 12 locks:** F18 apply-88, mismatch reject, no old-view lookup, no batch merge, apply-89 one director; F33 closed profiles, least-permissive, tight baseline, safe promotion, canonical seed, card-or-fatigue, failure-never-widens; machine projection still matches frozen expectations; gap inventory **32/44** wired, **12** unwired.


## #278 vertical-slice playback/replace runtime (Slice 13)

**Status:** offline F14/F35 drivers on branch `cursor/vertical-slice-playback-replace-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_playback_replace_runtime.py`](../../../tests/test_vertical_slice_playback_replace_runtime.py) (**4** tests: **2** parametrized machine projection + F14/F35 runtime drivers) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **34/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 13](../../v2.0.0/vertical-slice-acceptance.md#slice-13--f14f35-playback-race--planning-replace-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F14/F35 rows; hashes **unchanged**) |

**Slice 13 locks:** F14 reset-then-stale-accept unconsumed, accept-then-reset interrupt, reducer-sequence authority; F35 replace-without-suppression, close70, new_cycle71_attempt1, one alternative, lower-event no replace, accepted-event only; machine projection still matches frozen expectations; gap inventory **34/44** wired, **10** unwired.


## #278 vertical-slice feature-order runtime (Slice 14)

**Status:** offline F28 drivers on branch `cursor/vertical-slice-feature-order-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_feature_order_runtime.py`](../../../tests/test_vertical_slice_feature_order_runtime.py) (**2** tests: **1** parametrized machine projection + F28 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **35/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 14](../../v2.0.0/vertical-slice-acceptance.md#slice-14--f28-feature-order--bucket-coverage-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F28 row; hashes **unchanged**) |

**Slice 14 locks:** F28 reduce 10→12, older/duplicate noop, lone-sample coverage capped/invalid for trend, OLS three buckets, identity match; FeatureEngine stays free of NarrativeRuntime/DetectorBank imports; machine projection still matches frozen expectations; gap inventory **35/44** wired, **9** unwired.

## #278 vertical-slice disable/re-enable runtime (Slice 15)

**Status:** offline F16 drivers on branch `cursor/vertical-slice-disable-config-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_disable_reenable_runtime.py`](../../../tests/test_vertical_slice_disable_reenable_runtime.py) (**2** tests: **1** parametrized machine projection + F16 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **36/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 15](../../v2.0.0/vertical-slice-acceptance.md#slice-15--f16-disablere-enable-within-broadcast-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F16 row; hashes **unchanged**) |

**Slice 15 locks:** F16 close run 3, commentary disabled, complete trailer, manual independence, allocate run 4, incomplete history, one enabled mid-stream, no state leak; machine projection still matches frozen expectations; gap inventory **36/44** wired, **8** unwired.

## #278 vertical-slice TTS timeout runtime (Slice 16)

**Status:** offline F26 drivers on branch `cursor/vertical-slice-tts-timeout-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_tts_timeout_runtime.py`](../../../tests/test_vertical_slice_tts_timeout_runtime.py) (**2** tests: **1** parametrized machine projection + F26 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **37/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 16](../../v2.0.0/vertical-slice-acceptance.md#slice-16--f26-unresponsive-tts-lane-watchdog-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F26 row; hashes **unchanged**) |

**Slice 16 locks:** F26 start-timeout unconsumed, playback-timeout consumed, stop-timeout quarantine, admission blocked, late no-op, higher-generation restore; machine projection still matches frozen expectations; gap inventory **37/44** wired, **7** unwired.

## #278 vertical-slice TTS auto-resolution runtime (Slice 17)

**Status:** offline F30 drivers on branch `cursor/vertical-slice-tts-auto-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_tts_auto_runtime.py`](../../../tests/test_vertical_slice_tts_auto_runtime.py) (**2** tests: **1** parametrized machine projection + F30 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **38/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 17](../../v2.0.0/vertical-slice-acceptance.md#slice-17--f30-tts-auto-resolution-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F30 row; hashes **unchanged**) |

**Slice 17 locks:** F30 auto snapshots SAPI, no same-text failover, later generation only, SuperTonic explicit-only; machine projection still matches frozen expectations; gap inventory **38/44** wired, **6** unwired.

## #278 vertical-slice TTS request/callback protocol runtime (Slice 18)

**Status:** offline F39 drivers on branch `cursor/vertical-slice-tts-protocol-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_tts_protocol_runtime.py`](../../../tests/test_vertical_slice_tts_protocol_runtime.py) (**2** tests: **1** parametrized machine projection + F39 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **39/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 18](../../v2.0.0/vertical-slice-acceptance.md#slice-18--f39-tts-requestcallback-protocol-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F39 row; hashes **unchanged**) |

**Slice 18 locks:** F39 immutable utterance, callback sequence, consume-once, protocol quarantine, reset consumption rules, one restore, late no-op, manual new token; machine projection still matches frozen expectations; gap inventory **39/44** wired, **5** unwired.

## #278 vertical-slice TTS software-boundary runtime (Slice 19)

**Status:** offline F41 drivers on branch `cursor/vertical-slice-tts-boundaries-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_tts_boundaries_runtime.py`](../../../tests/test_vertical_slice_tts_boundaries_runtime.py) (**2** tests: **1** parametrized machine projection + F41 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **40/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 19](../../v2.0.0/vertical-slice-acceptance.md#slice-19--f41-tts-software-boundary-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F41 row; hashes **unchanged**) |

**Slice 19 locks:** F41 exact software boundaries, no early consumption, ordered callbacks, protocol quarantine, watchdog authority, no backend retry; machine projection still matches frozen expectations; gap inventory **40/44** wired, **4** unwired.

## #278 vertical-slice tape-channel funnel runtime (Slice 20)

**Status:** offline F43 drivers on branch `cursor/vertical-slice-tape-funnel-278-cad3` — **does not** claim live Windows §24.9 GO.

| Contract | Value |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_tape_funnel_runtime.py`](../../../tests/test_vertical_slice_tape_funnel_runtime.py) (**2** tests: **1** parametrized machine projection + F43 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **41/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 20](../../v2.0.0/vertical-slice-acceptance.md#slice-20--f43-tape-channel-funnel-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F43 row; hashes **unchanged**) |

**Slice 20 locks:** F43 FunnelLink identity/exact links, once-only counts, terminal stages, live counters without tape, incomplete-gap rates, valid denominators; machine projection still matches frozen expectations; gap inventory **41/44** wired, **3** unwired.



## #278 vertical-slice Qwen authority runtime (Slice 21)

**Status:** offline F40 drivers on branch `cursor/vertical-slice-qwen-authority-278-cad3` — **does not** claim live Windows §24.9 GO.

| Artifact | Path |
| --- | --- |
| Pytest module | [`tests/test_vertical_slice_qwen_authority_runtime.py`](../../../tests/test_vertical_slice_qwen_authority_runtime.py) (**2** tests: **1** parametrized machine projection + F40 runtime driver) |
| Slice 1 harness | [`tests/test_vertical_slice_fixtures.py`](../../../tests/test_vertical_slice_fixtures.py) (inventory row updated to **42/44** wired) |
| Acceptance doc | [vertical-slice-acceptance.md § Slice 21](../../v2.0.0/vertical-slice-acceptance.md#slice-21--f40-qwen-requeststreamdeadline-authority-runtime-drivers) |
| Frozen projection | `docs/v2.0.0/machine/vertical-slice-fixtures.json` (F40 row; hashes **unchanged**) |

**Slice 21 locks:** F40 exact prompt projection, one terminal result, fail-closed SSE, deadline authority, protected deadline under mailbox pressure, no request queue, duplicate protocol, warmup without retry, exact metrics; machine projection still matches frozen expectations; gap inventory **42/44** wired, **2** unwired.
