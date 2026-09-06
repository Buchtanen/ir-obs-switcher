# Stav: co je na `master`

Snapshot k dokumentačnímu úklidu. Runtime verze: `1.3.0` (`pyproject.toml`). Hosting: `Buchtanen/ir-obs-switcher`.

## Shipped na master

- Scene switcher: `logic/` + `main_loop`
- Overlay Event Engine + `EventManagerV2`
- N12: `AsyncEventFanout`, `OverlayConsumer`, `CommentaryConsumer` (`race/runtime.py`)
- Race observer + narrative landing (flags, aftermath, timing hunt, grid story, stream start)
- Commentary: sequence graph, director, TTS (SAPI / SuperTonic), optional LLM polish
- Prepared commentary graph contract (#217)
- Finish episodes, stream outro, MiniStory stale-call revision (#226)
- Track Excursion current-signal subset (`events/scenarios/`, `[race_scenarios] mode=active`)
- Operator diagnostic SAPI (`util/diagnostic_voice.py`, `[diagnostics]`)
- INFO `llm_polish` tape capture (`session_tape_llm=true`, #228)
- Admin Slice 1.2 (`/admin`)
- V4 overlay renderer + Pit Wall themes + golden fixtures
- **Není:** TUI, `/vr-status` / RaceLab widget

## Otevřené (ne jako shipped runtime)

Viz [inflight/README.md](inflight/README.md).

| Téma | Issue / PR | Docs |
| --- | --- | --- |
| Commentary architecture (graph continuity, excursion remainder, multi-sentence, prompt profiles, dataset export) | #220, #216, #223, #222, #219 | [commentary-architecture](inflight/commentary-architecture.md) |
| Live data channels / adaptive sampling | #212 (spec #213) | [live_data_channels_sampling_spec.md](../live_data_channels_sampling_spec.md) |
| Dependabot `upload-artifact` v7 | #162 | [pr-162](inflight/pr-162-dependabot.md) |
| Admin Slice 2–3, LHM canonical bus, SoF overlay cards | specs v `docs/` | domain pages |

## Co sem nepatří

Historické plány (`EVENT_ENGINE_V4_*_PLAN`, N-tasky, GPT briefy, cleanup/status z ledna 2026) jsou smazané. Pravda je tento index + kontrakty.
