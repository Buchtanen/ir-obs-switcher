# N8 — Stream start welcome + in-car session flavor

**Epic:** [narrative_observers_epic.md](../narrative_observers_epic.md) §5  
**Depends on:** P1 merged (`overlay/runtime.py` / director busy), N2 for long `tts` caps + mode nodes  
**Related product suite:** commentary P3 stream start  
**Branch hint:** `feat/stream-start-incar`

## Context

When the **OBS stream starts**, TTS should get real context and a **longer** welcome. When the driver **gets in the car** (often still in pit), TTS should be session-specific: next practice attempt, why quali matters, race start — not the same generic `in_car` line.

Session briefs (track / SoF / weather) stay a separate once-per-session pack.

## Owns / must not touch

- **Owns:** COMMENTARY_ONLY `STREAM_START`, hook from existing `obs_stream_started` path (`main.py` / overlay runtime glue), `StreamStartContext` snapshot, in-car **mode** selection (detector stays once-per-stint), graph node caps, tests  
- **Must not:** overlay cover UI (N9), RaceObserver FSMs, OBS scene table  

## Acceptance criteria

- [ ] On `obs_stream_started`, if `commentary.enabled` and `commentary.stream_start`: one envelope with slots that exist (track, session, field_size, sof, weather one-liner) — all optional; at least one fully bound line with no slots  
- [ ] Fail-soft if overlay/commentary not ready (stream still starts)  
- [ ] Node TTS limits allow a long welcome (e.g. max_seconds ≥ 15, max_chars ≥ 240) — validator must allow that node  
- [ ] `ENTER_CAR` lines selected by `overlay_mode` (N2): practice = next run; quali = stakes; race = start. Pit vs on-track does not block speak  
- [ ] Stream start does not consume in-car; both can fire (scheduler orders them)  
- [ ] Default `commentary.stream_start=false`  
- [ ] Once per OBS streaming session (rising edge), not every overlay tick  

## Test plan

- [ ] Unit: stream edge → one envelope; second tick no repeat  
- [ ] Unit: missing SoF still speaks slot-free variant  
- [ ] Unit: ENTER_CAR + PRACTICE binds practice node when N2 present  
- [ ] Existing in_car / session_briefs tests pass  

## Docs impact

- [ ] `COMMENTARY_ENGINE.md` STREAM_START  
- [ ] `CONFIG.md` + example.ini  
- [ ] `docs/commentary_product_suite.md` P3 pointer  
- [ ] API.md only if we expose a test trigger (prefer existing `/commentary` speak)  

## Config impact

- `commentary.stream_start` default `false`  
