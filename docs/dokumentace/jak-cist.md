# Jak číst tuhle dokumentaci

## Pravda má vrstvy

| Vrstva | Kde | Kdy platí |
| --- | --- | --- |
| Runtime kód na `master` | `src/irswitch/` | Implementace, kterou služba teď dělá |
| Tento index | `docs/dokumentace/` | Kam jít; hranice vrstev; odkazy |
| Kontrakty | `CONFIG.md`, `API.md`, `config/config.example.ini` | Klíče, payloady, defaulty |
| In-flight | [inflight/](inflight/README.md) + otevřené PR | Návrh / kód **mimo** `master` |
| Spec / plán | `docs/*_spec.md`, `docs/*_plan.md`, `EVENT_ENGINE_V4_*.md` | Záměr; neříká, že to v binárce je |

Konflikt: **kód na aktuální větvi vyhrává**. Když index a kód nesedí, oprav index (nebo označ in-flight). Nesnaž se „opravit“ kód podle starého plánu.

## Co sem nepatří

- Celý výpis INI klíčů (to je `CONFIG.md`)
- Kompletní HTTP schémata (to je `API.md`)
- Copy-paste celých funkcí
- Aspirace bez statusu (`Status: not on master`)

## Pravidla pro agenty

1. Otevři [README.md](README.md) → lookup tabulku.
2. Přečti **jednu** doménu + [architektura.md](architektura.md), pokud saháš na tok dat.
3. Pokud práce může kolidovat s observers / commentary / race story, přečti [inflight/README.md](inflight/README.md) **před** editací.
4. Grep až když víš balík (`iracing/`, `logic/`, …). Hledej v tom balíku, ne v celém `src/` napoprvé.
5. Scene switch a overlay jsou **dva pipeline**. Nemíchej je.

## Údržba (každý task)

Index je živý kontrakt, ne jednorázový dump.

Po změně kódu aktualizuj matching `domeny/*.md` (mapa v `.cursor/rules/docs-map.mdc`). Nový soubor / tok → `mapa-souboru.md` + `architektura.md`. Jen na otevřeném PR → [inflight/](inflight/README.md). Jinak v PR napiš `Docs: no change (reason …)`.

Tohle hlídá skill `dokumentace`, `/docs-keeper` ve `/flow`, PR checklist a (opt-in) Cursor stop hook. **Nespoléhej na hook** — na Windows jsou Cursor hooks často vypnuté.

## Hranice vrstev (neměnit bez explicitního zadání)

Převzato z `.cursor/rules/py-architecture-layers.mdc`:

- `iracing/` — jen extraction (shared memory, parse). **Žádná business logika.**
- `obs/` — tenký client. **Žádná policy, žádné rozhodování scén.**
- `logic/` — state machine + mapování mód → scéna. **Jediná cesta scene switch.**
- `server/` — HTTP/WS glue. **Nesmí sám hnát logiku přepínání.**
- Overlay / events / commentary — druhý pipeline (HUD + hlas). **Nepřepíná OBS scény.**

## Čas a selhání

- Cooldown / debounce / override: **monotonic** (`util/clock.py`, `time.monotonic`).
- iRacing disconnected = **normální stav**, ne výjimka.
- OBS drop → retry; **main loop nesmí spadnout**.
- Background tasky jen přes `TaskRegistry` (vlastnictví + cancel).
