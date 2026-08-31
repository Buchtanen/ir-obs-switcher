# PR #179 — observers decoupling (P0–P5)

- URL: https://github.com/Buchtanen/ir-obs-switcher/pull/179
- Větev: `feat/observers-decoupling-joint-test`
- Base: `master`
- Stav: **draft**. Autoři: nemergovat, dokud neprojde joint / manual test (`defer_enabled`, session briefs, battle→attack_range, pit stop).
- Label: `semver:minor`
- Squash P0–P5 (uzavřené stacked PR #167–#178)

## Proč existuje

Na master je commentary **za** overlay orchestrátorem (`_observe_commentary`). Cíl: **fan-out** — overlay, commentary (a derived observer) jako peer consumers stejných accepted envelopes. Navíc paměť příběhu (RaceObserver) a TTS fronta když je sink busy.

## Nové moduly (jen na větvi)

| Modul | Účel |
| --- | --- |
| `events/fanout.py` | `EventFanout` + protocol `EventConsumer`; fail-soft per consumer |
| `commentary/consumer.py` | Napojení directoru na fan-out |
| `commentary/scheduler.py` | `SpeechScheduler`: max 1 parked utterance, TTL, drop lower prio, optional hard interrupt INCIDENT (ne přes FINISH/FINAL_LAP) |
| `race/observer.py` | `RaceObserver` 2+2 near field, weather/field fillers |
| `race/story.py` | Stream/session memory |
| `race/aftermath.py` | Incident aftermath FSM (stalled/rolling, back under way) |
| `race/narrative.py` | SESSION_WRAP / SESSION_PREVIEW |

Graf: nové uzly ATTACK_RANGE, PIT_STOPPED (P5). `opponents.py` umí near-field N.

## Cílový tok (na větvi, ne master)

```text
TelemetrySnapshot → RaceContextAnalyzer → RaceState
        ├─ EventEngine (HUD emittery)
        └─ RaceObserver (derived envelopes)
                ↓
        Shared arbitration → EventEnvelope[]
                ↓
        EventFanout
        ├─ OverlaySink (HUD)
        ├─ Commentary (Director + SpeechScheduler)
        └─ Tape/debug
```

## Config (větve)

`[commentary.scheduler]` — defaulty **off** / bezpečné. Přesné klíče: CONFIG.md **na větvi #179**, ne na master.

## Docs na větvi

`docs/observers_decoupling_plan.md`, `docs/scenario_coverage_matrix.md`, `docs/commentary_speech_queue_followup.md`.

## Co dělat teď

- Číst tenhle soubor místo grepování `RaceObserver` na master.
- Nová práce na P0–P5: commitovat **na tuto větev** / follow-up stacked PR, ne duplicitně na master.
- Po merge #179: přesunout tuto stránku do „shipped“ a aktualizovat [events](../domeny/events.md), [commentary](../domeny/commentary.md), [race](../domeny/race.md), [architektura](../architektura.md).
