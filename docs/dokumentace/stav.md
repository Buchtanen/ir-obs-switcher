# Stav: co je na `master` a co jen v PR

Tento index popisuje **`master`** (checkout, ze kterého dokumentace vznikla), plus **otevřené PR** jako in-flight. Datum snapshotu větví: 2026-08-31.

## `master` (aktuální runtime)

- Scene switcher: `logic/` + `main_loop`
- Overlay Event Engine + `EventManagerV2` (flag `event_engine.v2_payload`)
- Commentary: `CommentaryDirector` napojený **uvnitř** `OverlayRuntime._observe_commentary` (ne peer fan-out)
- Race: `RaceContextAnalyzer` (1 ahead + 1 behind pro HUD), timing store
- **Není tu:** `events/fanout.py`, `commentary/scheduler.py`, `race/observer.py`, `race/aftermath.py`, `race/flags.py`

Poslední merge na `master` v době zápisu: overlay raw copy tokens + ACTIVE hold (#165).

## Otevřené PR (povinně zohlednit)

Plný popis: [inflight/README.md](inflight/README.md).

| PR | Base | Větev | Stav | Dopad na dokumentaci |
| --- | --- | --- | --- | --- |
| [#179](https://github.com/Buchtanen/ir-obs-switcher/pull/179) | `master` | `feat/observers-decoupling-joint-test` | draft, **joint test blocker** | Nové moduly race observer, fan-out, SpeechScheduler. Po merge přepsat [events](domeny/events.md), [commentary](domeny/commentary.md), [race](domeny/race.md). |
| [#181](https://github.com/Buchtanen/ir-obs-switcher/pull/181) | **#179 větev**, ne `master` | `cursor/narrative-observers-epic-4749` | draft stacked | Flags, opener mutex, incident classify, pace hunt. **Nemerguje se do master.** |
| [#162](https://github.com/Buchtanen/ir-obs-switcher/pull/162) | `master` | Dependabot `actions/upload-artifact` 6→7 | open | Jen CI workflow; runtime kód beze změny |

Stacked PRs P0–P5 (#167, #169, #171, #174, #176, #178) jsou **zavřené** — kód žije v #179. Starší #173 nahrazené #181.

## Jak psát kód, dokud #179 visí

- Nová práce na scene switcher / overlay HUD na `master` je OK, pokud **nebojuje** o stejné soubory jako #179 (`overlay/runtime.py`, `commentary/director.py`, `race/opponents.py`, `config.py`).
- Nová práce na race story / TTS frontě / fan-out: **stackuj na #179**, nebo počkej na merge. Nepiš druhý `RaceObserver` na `master`.
- Dokumentace domén níže = **master**. Delta je vždy v `inflight/` a v sekci „In-flight“ na stránce domény.

## Plány v `docs/` mimo tuto složku

Soubory jako `docs/observers_decoupling_plan.md` a `docs/narrative_observers_epic.md` **na master nejsou** (jsou na větvích #179/#181). Až se mergnou, prolinkuj je sem. Do té doby je cituj jen z [inflight](inflight/README.md).
