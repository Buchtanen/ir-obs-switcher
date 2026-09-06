# Commentary / TTS (`src/irswitch/commentary/`)

**Účel:** po přijetí `EventEnvelope` vybrat uzel sequence graphu a říct větu (SAPI). Volitelně LLM polish a OBS duck.

**Nepatří sem:** HUD layout, scene switch, čtení iRSDK (kromě dat, která už jsou v envelope/RaceState sidecar).

Produktový kontrakt textů/grafu: [COMMENTARY_ENGINE.md](../../../COMMENTARY_ENGINE.md). Plány v `docs/commentary_*` jsou vlny obsahu, ne nutně shipped.

## Na master: řetěz z overlay

`OverlayRuntime._observe_commentary` → `CommentaryDirector.observe`.

Director (`director.py`):

1. Filtr fází (`ENTER`, `RESULT`, `EXIT`; sektory a session briefs zvlášť)
2. Graph `sequence_graph.json` — node + edges
3. Anti-repeat (`anti_repeat.py`)
4. Slot format (`slot_format.py`) + `validator.py` (max utterance)
5. `TtsSink` (`tts.py`) — `ProcessTtsSink` (PowerShell SAPI) nebo null
6. Duck (`duck.py`) — stáhne overlay/application audio v OBS po dobu řeči
7. `SpeakDecision` log (spoken/skipped + reason) — admin/commentary UI

Broken JSON graph → director = `None`, overlay **běží dál**.

Sidecary (nejsou EventEngine):

- `in_car.py` — vstup do auta
- `session_briefs.py` — SESSION_INTRO_*, SOF_BRIEF, WEATHER_BRIEF (flag `commentary.session_briefs`)

`bridge.py` — legacy `RaceEvent` jména → speech envelope, když V2 adapter nic nedá.

`polish.py` — volitelný LLM framing; tape jen DEBUG.

HTTP: `http.py` — `/commentary` test, speak/validate, CSRF. Routes registruje overlay HTTP.

## Graph

`graph.py` + `data/sequence_graph.json`. Neznámý `event_type` v JSON na in-flight větvích **shodí parse** a vypne celé commentary (`from_defaults` exception). Proto #181 musí landnout N2 (modes/branch) **před** novými event_types.

## Config

`[commentary]`, `[tts]` — [CONFIG.md](../../../CONFIG.md). Defaulty bezpečné (často off).

## Testy

`tests/test_commentary_*.py`.

## In-flight — čti před změnami commentary

[#179](../inflight/pr-179-observers-decoupling.md):

- `SpeechScheduler` — park 1 utterance když TTS busy; TTL; optional hard interrupt INCIDENT vs FINISH
- `consumer.py` — `EventConsumer` pro fan-out
- `[commentary.scheduler]` INI (default off)

[#181](../inflight/pr-181-narrative-observers.md):

- `OpenerMutex` — stream start / intro / in-car / preview, hold 120 s
- `stream_context.py` — `obs_stream_started` bridge
- `commentary.stream_start` default **false**
- Graph modes/branch, COMMENTARY_ONLY typy (`STREAM_START`, `SESSION_FLAG`, `PACE_HUNT`)
- Gap-hunt TTS v P/Q default off

Nepiš na master druhou TTS frontu. Stackuj na #179 nebo čekej merge.
