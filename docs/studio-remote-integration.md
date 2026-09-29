# Studio and remote commentary integration — 2026-09-28

The user authorized combining Studio `8bff2de` with remote commentary `4401d0c`,
merging the verified result to master, and deploying an audible live test.
The separate supervisor planning branch is not part of this merge.

The previous Studio executable did not contain the remote configuration contract.
It rejected provider/mode/api_key_env and never started the commentary actor.
The shared source now includes both Studio runtime catalogs and fact-bound remote
realization. Custom Studio definitions do not expand the supported remote event
families; unsupported inputs remain silent.

## Configuration and operation

### Grounded-input follow-up — #389

Topic `feat/commentary-grounded-input` replaces the remote prompt profile with
`M2/1`: readable fact claims gain typed values/units, event identity and expiry,
plus up to three same-session commentary entries from the last 60 seconds that
reached `PLAYBACK_ACCEPTED`. A valid model skip deliberately stays silent.
`INCIDENT`, `PIT_ENTRY` and `PIT_EXIT` join the seven existing input families.
The experimental wording path adds a partial grounding guard and diagnostic
reasons; passing it does not prove factual correctness. There are no new INI keys
or sampling changes. This topic has no live validation yet. See the
[current input contract](v2.0.0/remote-commentary-microplan.md#runtime-boundary).

The configuration and free-wording notes below record the earlier M1 deployment
and experiment; their unchanged-family/prompt statements describe that earlier slice.

Remote provider, mode and api_key_env are INI settings, not Studio overlay Settings
fields. Use `[commentary.llm]` with provider=remote, mode=live,
base_url=https://llm.buchtovo.cz/v1 and model=openai/gpt-oss-120b for this test.
The provider's model identifier is not an OpenAI origin claim. Supply the bearer
credential only through IRSWITCH_LLM_API_KEY in the launched process environment.
Never copy it into INI, a build, logs, or version control. A new launcher must
also supply the environment; changing another shell does not update a live process.

Inspect `/api/commentary/runtime` → `loop.supervisors.commentary_model` for actual
provider, mode, preflight, attempts and selections. Browser voice settings do not
configure the server's Supertonic voice. Manual server speech checks the sound
path, not model generation. `played` indicates acceptance by the sink; check the
terminal speech result and audio logs for completion.

### Planned free-wording live experiment

The `feat/remote-free-wording` extension adds `[commentary.llm] wording_policy`:
`strict` by default, or `experimental_free` for remote generation only. The requested
next test uses `mode=live`, `wording_policy=experimental_free`, `timeout_s=3.0`.
This is a planned configuration, not a deployment result. Local providers remain
strict. The seven input families and M1 prompt/sampling remain unchanged.

Free wording keeps shape/length and freshness/config/cancellation/deadline checks,
but neither whole-sentence grammar check blocks generated text. Diagnostics record
`wordingPolicy`, `semanticCheck=not_enforced` and `strictWouldAccept`; acceptance
does not establish factual accuracy. Restore `wording_policy=strict` for grammar
enforcement or disable model generation for authored fallback. See the
[test contract and review steps](v2.0.0/remote-commentary-microplan.md#experimental-free-wording-live-test).

## Packaged deployment

Install the project's `.[supertonic]` extra and PyInstaller in the build interpreter.
Run `scripts/build_commentary_exe.ps1 -PythonExecutable <venv-python>` from the
verified combined checkout. It uses that checkout's src, collects the optional
CPU/audio dependencies and writes a staged EXE plus SHA256/commit build-info.json.
It does not write or replace the operator's INI. Models use Supertonic's user cache;
an uncached first startup needs its automatic model download. Node is build-only.

Verify the EXE with `scripts/qa_studio_package.py` on disposable ports/configs,
then check remote configuration/preflight and a real Supertonic playback in the
deployed executable. Confirm its process path and SHA256; package version alone
does not distinguish these builds. Preserve the previous binary/config for rollback.
TDD exception: build-script wiring is verified by the actual artifact and package
smoke, not a text-matching unit test. Risk: omitted native dependencies; mitigation:
packaged startup and actual CPU synthesis/playback.

The live test still must establish performance and commentary quality during an
actual iRacing session. Automated/mock speech tests and a manual audio test do not
substitute for that acceptance. Preserve model attempts, fallback selections,
rejections and speech results with telemetry for subsequent evaluation.

## Verification checkpoint

### Running build identity — 2026-09-29

Studio Overview shows the running service's short commit, with the full commit in
its detail. The top-level `build` object in `GET /api/admin/status` contains nullable
`commit`, `shortCommit` and `dirty`, plus `source=embedded|source|unknown`.
Frozen executables use only their
embedded `build-identity.json`; they never derive identity from Git in the launch
directory. Source execution captures its package repository identity once at module
import with bounded Git calls. Missing or invalid metadata remains unknown, and a
later checkout does not change an already running process's identity.

Use this card to confirm which implementation is serving Studio after deployment.
Retained data is marked stale when refresh fails; stale identity does not confirm
the current process. Continue retaining artifact SHA256 evidence for binary-level
verification. This addition does not establish a new live commentary acceptance result.

### Combined deployment evidence

- Combined full local suite: 2741 passed, two Windows symlink-privilege exclusions;
  independent 255 integration tests, 31 frontend tests and selected static checks GREEN.
- Packaged Studio QA passed (assets, custom definitions, three isolated starts).
- Real model pipeline probe exposed two equivalent completed-lap phrasings rejected
  by the bounded grammar. Added input-derived article/completion variants and the
  already supported spoken-time conversion to completed laps. Regression rejects
  changed time, changed driver and added personal-best claims; 15 focused tests pass.
- Repeated real approved endpoint probe after correction: 3/3 model candidates
  accepted and delivered through the runtime to a null audio sink. This uses synthetic
  lap data and does not establish live iRacing coverage or physical audio delivery.
- Final CI and deployed-process results are recorded in PR #371 and the local operator
  test output. Keep the user-requested live mode for the next audible test.
