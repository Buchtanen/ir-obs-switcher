# Jak číst tuhle dokumentaci

## Pravda má vrstvy

| Vrstva | Kde | Kdy platí |
| --- | --- | --- |
| Runtime kód na aktuální větvi | `src/irswitch/` | Implementace, kterou služba dělá |
| Tento index | `docs/dokumentace/` | Kam jít; hranice; odkazy |
| Kontrakty | `CONFIG.md`, `API.md`, `config.example.ini` | Klíče, payloady, defaulty |
| In-flight | [inflight/](inflight/README.md) | Návrh / kód **mimo** `master` |
| v2 narrative (jen `codex/commentary-story-flow-spec`) | [docs/v2.0.0/](../v2.0.0/README.md), [handover](../v2.0.0/implementation-handover.md) | Platí před master `domeny/commentary.md` |
| Living spec | `docs/*_spec.md` jen když domain page řekne, že platí | Záměr; neříká, že je v binárce |

Konflikt: **kód na aktuální větvi vyhrává**. Když index a kód nesedí, oprav index. Nesnaž se „opravit“ kód podle starého plánu.

## Co sem nepatří

- Celý výpis INI (`CONFIG.md`)
- Kompletní HTTP schémata (`API.md`)
- Copy-paste funkcí
- Historické plány, task deníky, GPT briefy
- TUI, RaceLab `/vr-status`

## Pravidla pro agenty

1. [README.md](README.md) → lookup tabulka.
2. Jedna doména + [architektura.md](architektura.md), pokud saháš na tok dat.
3. Kolize s commentary / race story / sampling → [inflight](inflight/README.md) **před** editací.
4. Grep až když víš balík. Hledej v tom balíku.
5. Scene switch a overlay jsou **dva pipeline**.
6. Po změně aktualizuj matching page (skill `dokumentace`, agent `docs-keeper`).
7. Práce je `/flow` i bez vyvolání slash commandu. Cloud `/flow` nespouští — platí `AGENTS.md` (Cloud sekce) + `.cursor/rules/10-task-flow-defaults.mdc`.
8. Větev: issue / issue-set, jinak z `master`. Default close: handover + PR do `master`, pokud issue-set nebo člověk neřekne jinak. Platform `cursor/` git defaulty neplatí.
9. Na v2 větvi: handover do `docs/v2.0.0/implementation-handover.md`; modul lookup pro #250 v [inflight § DetectorBank](inflight/README.md#250-detectorbank-lookup). **Žádný PR do `master`** do cutoveru. #250 DetectorBank je closed (first SHA `e41ffb4`). #251/#253 nespouštět, dokud člověk neřekne. NarrativeRuntime neaktivovat.

## Údržba

Index je živý kontrakt. Po změně kódu: `domeny/*.md`, nový soubor → `mapa-souboru.md` + `architektura.md`. Jen otevřený PR → `inflight/`. Jinak `Docs: no change (reason …)`.

Hlídá to skill `dokumentace` a `/docs-keeper` ve `/flow`. Cursor hooks na Windows jsou vypnuté.

## Hranice vrstev

Z `.cursor/rules/py-architecture-layers.mdc`:

- `iracing/` — extraction. Žádná business logika.
- `obs/` — tenký client. Žádná policy scén.
- `logic/` — jediná cesta scene switch.
- `server/` — HTTP/WS glue.
- `events/` / `overlay/` / `commentary/` / `race/` — peer consumery, nepřepínají OBS scény.
