# Current-fact commentary and remote M1

**Status (2026-09-25):** implementation on `feat/remote-commentary-microplan`, based on `master@a381307`. This is an opt-in test path, not evidence of a successful OBS/iRacing stream or TTS listening test. The server's model ID is an alias; an OpenAI-compatible wire format does not establish the server's model implementation or operator.

**Wording-policy extension:** `feat/remote-free-wording` adds an explicit remote-only `experimental_free` option. The requested live test uses a three-second timeout; this document records its configuration and limits, not a completed deployment or test result. Missing `wording_policy` remains `strict`.

## Runtime boundary

`narrative_shadow_adapter.py` projects an accepted event and its coherent context into an immutable `Microplan` (`commentary_microplan.py`). The selected plan carries event/session identity, revision, actors, input facts, a digest and expiry. The event's original monotonic timestamp sets a five-second TTL; arrival time does not renew it. Missing or unsupported input produces silence.

Initial supported inputs are named-driver `PERSONAL_BEST` and `LAP_COMPLETE` with a finite positive `lapTime`, plus `HUNTING` (front), `HUNTED` (rear), `APPROACH` (front), `ATTACK_RANGE` (front) and `SIDE_BY_SIDE` with distinct named actors. Other families are not promoted by this change. This narrow allowlist also limits authored fallback on the new live path.

`commentary_model.py` owns cancellable async aiohttp requests. It uses one active request and no waiting queue, one generation attempt per bundle, bounded response bytes and at most 100 diagnostic attempt records. There is no synchronous network call in construction. Optional asynchronous preflight uses the same endpoint, authentication and ordinary timeout. The old 45-second cold-load and first-call eight-second allowances do not apply to this path.

Remote `M1/1` uses the measured M1 system prompt with current facts only: `temperature=0.3`, `top_p=1`, `max_tokens=192`, `reasoning_effort=none`, `n=1`, `stream=false`. The response is prompt-requested JSON containing one candidate; no `response_format`, Ollama `options` or untested server extension is sent. Local `tight/1` uses `temperature=0.2`, `top_p=0.8` and configured `max_tokens`. Public `max_profile` cannot promote a family or change the fixed M1 profile.

Before any request, the application derives a finite set of allowed complete sentences from input facts. Under the default `strict` wording policy, whitespace/case normalization is allowed; extra claims, actor swaps, changed numbers and unreviewed paraphrases are rejected. Model-reported fact IDs are checked for shape/provenance but are not semantic proof. This intentionally rejects some factually correct M1 paraphrases. Shadow records help identify concrete additions to the audited grammar.

Remote `experimental_free` records the grammar result but does not let either whole-sentence membership check block generated wording. It still requires the response shape and one sentence of at most 200 characters and 32 words. This allows model paraphrases outside the audited grammar and also allows factual mistakes that grammar enforcement would have blocked. It provides no guarantee that actors, numbers or facts are correct. Local generation remains effectively `strict`, regardless of the configured policy. The seven supported input families, M1 prompt and sampling parameters remain unchanged.

The new path supplies an input-derived verification frame rather than interpreting model output as its own authority. Wording policy is frozen before I/O and included in the configuration signature; an old completion cannot acquire permission from a later policy change. The current source session/correlation revision, configuration signature (including the global commentary kill switch) and expiry are checked before speech commitment under both policies. Cancellation and deadlines also remain enforced. A failed live attempt may use an authored sentence from the same still-current bundle; otherwise it is silent. Rejected or shadow candidates never enter TTS or spoken exposure history. An accepted model candidate in diagnostics is not proof that playback occurred or that free wording is factually correct.

## Configuration and migration

New optional keys under `[commentary.llm]`:

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `local` | `local` retains local/LAN address policy; `remote` explicitly permits a remote HTTPS endpoint. |
| `mode` | `live` | `live` can supply validated speech; `shadow` evaluates asynchronously while the current valid authored sentence is available immediately. |
| `api_key_env` | `IRSWITCH_LLM_API_KEY` | Environment variable containing the remote Bearer token; this setting is its name, never its value. |
| `wording_policy` | `strict` | `strict` enforces the input-derived sentence grammar; remote-only `experimental_free` observes it without blocking generated wording. Local effective policy is always strict. |

`enabled=false` disables model requests and uses the supported authored path. Existing local configurations need no new keys, but live realization now fails closed for unsupported inputs; test coverage and audible coverage are separate concerns. Cold local models may miss the ordinary timeout and require an external warmup before a stream. `max_tokens` configures local `tight/1`; remote `M1/1` fixes its measured budget at 192.

Remote URLs require HTTPS, no userinfo/query/fragment, and exactly `/v1` (an optional trailing slash is normalized). Nested paths such as `/api/v1` are not remote endpoints in this contract. Redirects and environment proxies are disabled; the credential is sent only in the Authorization header. Missing/invalid credentials cause a bounded failure. Do not put tokens in INI, command-line arguments, issue comments or recordings.

The live adapter reads the current validated configuration for requests and compares its signature again before speech. Changes to provider, mode, wording policy or credential-variable name apply on the next request and invalidate old-config completions. Existing ConfigLedger boundaries remain documented in [public contracts](public-contracts.md). Environment changes must reach the running process: a value set in a new PowerShell window is not inherited by an already running service. Restart the relevant process after changing its environment.

This `commentary.llm.mode=shadow` is a new model-evaluation setting. It does not restore the removed legacy commentary runtime values `legacy|shadow|active`.

### Start with remote shadow

In the shell that will launch the application, supply your credential without echoing it:

```powershell
$credential = Read-Host 'Remote model Bearer token' -AsSecureString
$env:IRSWITCH_LLM_API_KEY = [System.Net.NetworkCredential]::new('', $credential).Password
```

Set the following in your existing configuration, retaining the rest of the commentary/TTS settings:

```ini
[commentary.llm]
enabled = true
provider = remote
mode = shadow
wording_policy = strict
api_key_env = IRSWITCH_LLM_API_KEY
base_url = https://llm.buchtovo.cz/v1
model = openai/gpt-oss-120b
timeout_s = 1.5
max_tokens = 192
max_profile = tight
warmup = true
```

Launch the application from that environment using your existing launch method. For a service, configure its own environment and restart it. The implementation task does not edit the operator's `config.ini` or activate remote live speech.

Inspect `GET /api/commentary/runtime` → `loop.supervisors.commentary_model`. Confirm provider, mode, model, profile and preflight; inspect attempt reasons and latency. `recentAttempts` and `recentSelections` are bounded in-memory diagnostic windows (100 entries each). `recentSelections` records the chosen text source (`remote`, `local` or `authored`) and marks `played` only on PLAYBACK_ACCEPTED; `totalAttempts` is a lifetime count. These windows are not a durable benchmark dataset. Export snapshots regularly for review; the endpoint includes bounded generated text but no token or endpoint. No request is made for unsupported/missing facts, and a busy shadow worker drops the extra evaluation rather than queueing stale text.

After reviewing shadow evidence, set `mode=live` for an audible test of the supported families. Immediate rollback is `enabled=false`; returning to local also requires `provider=local` plus your original local URL/model. Keep TTS voice and settings fixed for comparisons.

### Experimental free wording live test

For the requested experiment, retain the existing remote endpoint, model, credential
environment and TTS settings, and change these keys under `[commentary.llm]`:

```ini
provider = remote
mode = live
wording_policy = experimental_free
timeout_s = 3.0
```

This is the intended test configuration, not a claim that it has been deployed.
The three-second transport budget is still limited by the original event expiry;
it does not renew the five-second TTL. Before evaluating results, confirm the
running build in Studio and `wordingPolicy` in model diagnostics. Free generated
text records `semanticCheck=not_enforced` and `strictWouldAccept`. A candidate
accepted with `strictWouldAccept=false` measures grammar exclusion; it does not
prove that the wording is accurate or better. Review actors, facts, numbers,
latency and actual playback separately.

Set `wording_policy=strict` to restore grammar enforcement for subsequent requests,
or `enabled=false` to stop model generation and return to the supported authored
path. A policy/config change rejects old-config completions. This experiment
does not expand input coverage or replace the outstanding stream-quality review.

## Verification and stream gates

Focused regression tests live in `tests/test_remote_commentary_microplan.py`, `tests/test_remote_commentary_runtime.py` and `tests/test_remote_commentary_transport.py`: fact projection and independent semantics, config/endpoint policy, async transport failure/cancellation, stale context/config, and shadow isolation. Run with the project's pytest environment; the implementation handover records commands and measured results. Legacy frozen transport/actor tests remain regression evidence, not proof that the live path uses fixture prompts.

Before a live stream test:

1. Verify the running commit, effective mode/model, selected TTS voice and rollback. Compare identical replay situations when claiming A/B results.
2. Run 30–45 minutes of remote shadow, aiming for at least 100 eligible situations. Report the actual count, supported-family coverage, semantic rejection, transport failure and fallback shares separately.
3. Review every candidate against its input facts. Observe switcher heartbeat, iRacing frame time and OBS render/encoding lag. Target generation p95 ≤1.5 seconds; it is a target, not a demonstrated property. Earlier standalone tests had tails around 2.8 seconds.
4. Only after review, run a limited audible trial: aim for at least 50 actually played remote sentences over 30–60 minutes. Record timestamps and classify factual, stale, repetition, language, pronunciation and silence issues. Candidate acceptance alone does not count as played speech.
5. Roll back immediately for an invented pass, reversed actors, stale-session speech or loop blockage. For repeated transport errors, disable remote and verify preflight before retrying. An automatic circuit breaker is not part of this initial implementation.

Unfinished promotion gates include real replay/shadow coverage, TTS listening, fair preference comparisons and family-specific grammar expansion. The earlier 661 standalone generations informed M1 selection; they do not validate this new runtime end to end.


[Implementation verification and 27 real endpoint probes](remote-commentary-verification.md). The held-out strict grammar acceptance was 5/9; that is historical strict-policy evidence, not a quality score or acceptance result for experimental free wording.
