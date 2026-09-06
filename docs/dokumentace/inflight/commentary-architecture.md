# In-flight: změna architektury komentáře (po cutoff)

**Status:** otevřené issues na `master` baseline (N12 consumers už shipped).
**Shipped:** #225 finish episodes / stream outro / stale-call revision → PR #226.
**Nesahá sem:** nový druhý director / druhá TTS fronta na čistém master bez stacku na tyto issues.

## Cíl

Commentary má zůstat peer consumer eventu (ne HUD renderer). Další práce je obsah, kontinuita graphu, finish/outros a LLM profily — ne přepis scene switcheru.

## Otevřené issues (běžící)

| Issue | Téma |
| --- | --- |
| [#220](https://github.com/Buchtanen/ir-obs-switcher/issues/220) | Session-aware race stories, telemetry, sequence graph continuity |
| [#217](https://github.com/Buchtanen/ir-obs-switcher/issues/217) | Prepared commentary graph contract |
| [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216) | Deterministic Track Excursion scenario engine |
| [#223](https://github.com/Buchtanen/ir-obs-switcher/issues/223) | Continuous multi-sentence commentary on one duck |
| [#222](https://github.com/Buchtanen/ir-obs-switcher/issues/222) | Dynamic LLM prompt profiles |
| [#219](https://github.com/Buchtanen/ir-obs-switcher/issues/219) | Capture LLM polish pairs / datasets |
| [#224](https://github.com/Buchtanen/ir-obs-switcher/issues/224) | Operator diagnostic SAPI |

## Kde číst shipped baseline

- [domeny/commentary.md](../domeny/commentary.md)
- [COMMENTARY_ENGINE.md](../../../COMMENTARY_ENGINE.md)
- [commentary_product_suite.md](../../commentary_product_suite.md)
- [commentary_stateful_sequence_graph_spec.md](../../commentary_stateful_sequence_graph_spec.md)

## Hranice

- HUD copy zůstává v `overlay/i18n.py` (skill `overlay-hud-copy`).
- Scene switcher (`logic/`) se kvůli commentary nemění.
- Spec `live_data_channels_sampling_spec.md` je samostatné in-flight (#212), ne součást tohoto listu.
