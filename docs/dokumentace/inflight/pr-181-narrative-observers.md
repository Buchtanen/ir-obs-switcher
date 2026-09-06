# PR #181 — narrative observers (N1–N11A, N6, N3, N5)

- URL: https://github.com/Buchtanen/ir-obs-switcher/pull/181
- Větev: `cursor/narrative-observers-epic-4749`
- Base: **`feat/observers-decoupling-joint-test` (#179), ne `master`**
- Stav: **draft**. Stop pro live listen. N7 recap, N11 B–D, N9 cover, N10 public API **odložené**.
- Label: `semver:none` (nesmí se tvářit jako PR do master)
- Nahrazuje uzavřené #173

## Závislost

Bez #179 tato větev nedává smysl. Merge do master **přes #179** (ne cherry-pick N-tasků na čistý master).

Epic text na větvi: `docs/narrative_observers_epic.md` + `docs/tasks/n1_*.md` … `n11_*.md`.

## Landing order (už v PR zaškrtnuté v AC, live listen ne)

N1 iRSDK dynamics/flags → N2 graph `modes`/`branch` → N4 finish semantics → N8 stream start mutex → N11 A copy → N6a/N6b pace → N3 incident classify → N5 session flags.

N2 **musí** být před novými `event_types` v JSON (unknown type zabije parse graphu = ticho celého commentary).

## Nové / zásadní soubory na větvi

| Soubor | Účel |
| --- | --- |
| `iracing/session_flags.py` | Decode `SessionFlags` bitů, extraction only |
| `race/flags.py` | `SessionFlagFsm` yellow/green/checkered; start lights drop; 12 s cooldown; ne FINISH/WRAP |
| `race/timing_hunt.py` | PACE_HUNT z `CarIdxBestLapTime`; all-unset → silence |
| `commentary/opener.py` | Mutex stream/intro/in-car/preview, hold 120 s; STREAM_START vyhrává |
| `commentary/stream_context.py` | Bridge `obs_stream_started` |

Úpravy: `RaceState` + Speed / lap times / flag bits (N1); tři booleany checkered/finished/mute (N4); aftermath Speed jako motion uvnitř stalled, ne reclassify off-track (N3).

## Config (větve, default off)

- `commentary.stream_start` = false
- `commentary.gap_hunt_tts_in_practice` / `gap_hunt_tts_in_qualifying` = false
- `race_observer.leader_pace_cooldown_s` = 300
- `race_observer.incident_classify` = false
- `race_observer.flags` = false

`events.incident_min_delta` zůstává 2. Checkered **bit** se neneOR-uje se `SessionState==5`.

## Co nedělat

- Nemergovat #181 do `master`
- Nedělat N9 overlay cover „bokem“ na master
- Nedělat N10 API, dokud to epic znovu neotevře
- N7 race-start recap až po live listen
