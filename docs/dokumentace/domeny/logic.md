# Logic / scene switcher (`src/irswitch/logic/`)

**Účel:** jediná rozhodovací cesta **mód → OBS scéna**. Explicitní, testovatelné přechody.

**Nepatří sem:** iRSDK parse, HUD eventy, TTS, HTTP.

## `Policy` (`policy.py`)

Mapa `DrivingMode → scene name` + `safe_scene`. Chybějící mód → safe scene. Hot-reload: `apply_scenes`.

Názvy musí **přesně** sedět na OBS (case-sensitive). Validace při connect v `run_service`.

## `StateMachine` (`state_machine.py`)

Vstup ticku: aktuální `SwitchState`, `iracing_mode`, `obs_current_scene`, `is_loading`.

Chování:

- **Debounce:** mód musí vydržet `switching.debounce_ms` (monotonic).
- **Cooldown:** min. mezera `cooldown_ms` mezi přepnutími.
- **Override:** dočasná scéna (`override_seconds` / API `POST /override`); po expiraci reset debounce.
- **Autoswitch off:** nemění scénu (reason v state).
- **Priorita módů:** CONNECTING > LOADING > RESTART > QUIT > LOBBY/GARAGE/RACE/REPLAY.
- **Grace 3000 ms** po LOADING/CONNECTING: první LOBBY/GARAGE se nebere hned (false stall flicker). Stabilní GARAGE po celém okně → garage scéna. RACE/REPLAY jen debounce, bez extra delay.
- Reason string (`grace_period_ignore:…`, `mode:RACE (debounced)`, `cooldown`, …) — loguj **proč**.

Symptom regrese: po loadu nejdřív garage scéna (`Back`) a za ~3 s lobby (`VR`). Viz `iracing-sdk-semantics.mdc`.

`apply_runtime_config` — hot-reload bez resetu debounce (volá config reload).

## Stream chapters (`stream_chapters.py`, `youtube_chapters.py`)

In-memory markery pro WS/status (`[stream_chapters]`). Zápis do YouTube VOD je v `obs/youtube_vod.py` z API vrstvy, ne ze state machine.

## Config

`[switching]`, `[scenes]`, `[hotkeys]`, `[stream_chapters]` — [CONFIG.md](../../../CONFIG.md).

## Testy

`tests/test_state_machine.py`, `tests/test_policy.py`, `tests/test_stream_chapters.py`, `tests/test_youtube_chapters.py`.

## In-flight

Observers PRs **nemění** scene switcher. Nesahej na `state_machine.py` kvůli TTS/flagům.
