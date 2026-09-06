# In-flight: otevřené PR

Snapshot **2026-08-31**. Před prací v `race/`, `events/`, `commentary/`, `overlay/runtime.py` tuhle stránku otevři.

Tyto změny **nejsou v `master`**. Grep na čistém master je nenajde — to je správně.

## Mapa PR

```text
master
  ├── #162 dependabot upload-artifact v7     (CI only)
  └── #179 feat/observers-decoupling-joint-test   [draft → master]
          └── #181 cursor/narrative-observers-epic-4749   [draft → #179, NE master]
```

| PR | URL | Base | Merge? |
| --- | --- | --- | --- |
| **#179** P0–P5 joint test | https://github.com/Buchtanen/ir-obs-switcher/pull/179 | `master` | Až po joint/manual testu na stream PC |
| **#181** N1–N11A, N6, N3, N5 | https://github.com/Buchtanen/ir-obs-switcher/pull/181 | větev #179 | Ne do master; live listen + review |
| **#162** upload-artifact 7 | https://github.com/Buchtanen/ir-obs-switcher/pull/162 | `master` | CI chore |

Zavřené, kód squasnutý do #179: #167 P0, #169 P1, #171 P2, #174 P3, #176 P4, #178 P5. #173 nahrazené #181.

## Konfliktní soubory (needitovat na master „stejně“)

#179 už sahá na mimo jiné:

- `src/irswitch/overlay/runtime.py`
- `src/irswitch/commentary/director.py`, `tts.py`, `graph.py`, `polish.py`
- `src/irswitch/race/opponents.py`
- `src/irswitch/config.py`, `config_reload.py`, `overlay/settings.py`
- `config/config.example.ini`, `CONFIG.md`

#181 navíc: `main.py`, `iracing/reader.py`, `events/incident.py`, `events/session*.py`, nové `race/flags.py`, `commentary/opener.py`.

## Kam dál

- [pr-179-observers-decoupling.md](pr-179-observers-decoupling.md) — fan-out, scheduler, RaceObserver
- [pr-181-narrative-observers.md](pr-181-narrative-observers.md) — flags, opener, classify, pace
- [pr-162-dependabot.md](pr-162-dependabot.md) — CI

Plány **na těch větvích** (na master chybí): `docs/observers_decoupling_plan.md`, `docs/scenario_coverage_matrix.md`, `docs/narrative_observers_epic.md`, `docs/tasks/n1_*.md` … `n11_*.md`.
