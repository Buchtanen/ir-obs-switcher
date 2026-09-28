# Remote M1 implementation verification — 2026-09-25

Branch: `feat/remote-commentary-microplan`, from `master@a381307611a5aaf633f61ed048c9bee066b77a24`.

## Automated evidence

- 386 passed, 2 deselected in the focused 21-file regression suite. The two excluded existing symlink tests require a Windows privilege unavailable on this host; no production workaround was added.
- Ruff, Black and mypy (9 changed source files, `--follow-imports=silent`) passed. Independent verifier: GREEN for this implementation and shadow testing, not live promotion.
- Real adapter/director/freshness/verifier/TTS-boundary integration, cancellation, deadline heartbeat, global/commentary-model disable, configuration change, restart and no-input failure are covered.
- Wire tests exercise redirect policy, proxy policy, response byte limit and malformed JSON with a fake aiohttp session. No OBS/iRacing or real audio is used by unit tests.

## Actual endpoint integration probes

27 additional synthetic requests used the implemented ModelClient, its real aiohttp transport, actual approved authentication and exact M1 prompt. Each run used a **3.0-second** diagnostic timeout; the example production deadline is **1.5 seconds**. Acceptance counts below are semantic acceptance before TTS, not played remote sentences. Values exceeding 1.5 seconds would time out under the example configuration.

| Run | Requests | Accepted | Median ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: |
| initial | 9 | 0 | 617.0 | 2868.0 |
| expanded_grammar | 9 | 6 | 644.5 | 770.0 |
| heldout | 9 | 5 | 680.0 | 2222.2 |

The first run found that the initial whole-sentence grammar rejected all outputs, including correct phrasing. Input-derived grammar expansions cover natural lap-time phrasing, digit-by-digit spoken lap times, current side-by-side wording and explicit current gap clauses. The final held-out set changed driver names, lap time and gap. It accepted 5/9; two closing-gap phrasings and two side-by-side phrasings remain rejected. No claim of universal semantic validation or live readiness is made. The three runs use different intermediate grammar revisions and must not be pooled as one final-profile acceptance rate.

Raw sanitized evidence: [27 request results](evidence/remote-m1-2026-09-25.json). No headers or credentials are retained.

## Remaining operational gate

Use [the operator guide](remote-commentary-microplan.md) for at least 100 eligible shadow situations and review all outputs. The live model currently supports only named PB/completed laps and the documented directional battle families; other inputs fail closed. No replay A/B preference test, live OBS/iRacing performance measurement or TTS listening was completed. Config.ini and the running original checkout were not changed.
