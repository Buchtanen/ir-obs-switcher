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
