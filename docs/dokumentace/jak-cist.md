# Jak číst tuhle dokumentaci

## Pravda má vrstvy

| Vrstva | Kde | Kdy platí |
| --- | --- | --- |
| Runtime kód na aktuální větvi | `src/irswitch/` | Implementace, kterou služba dělá |
| Tento index | `docs/dokumentace/` | Kam jít; hranice; odkazy |
| Kontrakty | `CONFIG.md`, `API.md`, `config.example.ini` | Klíče, payloady, defaulty |
| In-flight | [inflight/](inflight/README.md) | Návrh / kód **mimo** `master` |
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
