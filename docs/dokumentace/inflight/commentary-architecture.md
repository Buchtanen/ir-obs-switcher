# In-flight: změna architektury komentáře (po cutoff)

**Status:** otevřené issues na `master` baseline (N12 consumers už shipped).
**Shipped:** #225/#226 finish episodes / stream outro / stale-call revision; #217 prepared graph contract; #224 diagnostic SAPI (`util/diagnostic_voice.py`); #228 INFO `llm_polish` tape capture. Native excursion detector je na masteru; I3 engine-as-publisher je na této větvi.
**Nesahá sem:** nový druhý director / druhá TTS fronta na čistém master bez stacku na tyto issues.

## Cíl

Commentary má zůstat peer consumer eventu (ne HUD renderer). Další práce je obsah, kontinuita graphu, multi-sentence a LLM profily — ne přepis scene switcheru. Excursion I3 je samostatné in-flight.

## Otevřené issues (běžící)

| Issue | Téma |
| --- | --- |
| [#220](https://github.com/Buchtanen/ir-obs-switcher/issues/220) | Session-aware race stories, telemetry, sequence graph continuity |
| [#216](https://github.com/Buchtanen/ir-obs-switcher/issues/216) | Track Excursion I3 publisher — [scenario-engine-publisher.md](scenario-engine-publisher.md); taxonomie příčin jinde; live listen není gate |
| [#223](https://github.com/Buchtanen/ir-obs-switcher/issues/223) | Continuous multi-sentence commentary on one duck |
| [#222](https://github.com/Buchtanen/ir-obs-switcher/issues/222) | Dynamic LLM prompt profiles |
| [#219](https://github.com/Buchtanen/ir-obs-switcher/issues/219) | Dataset compile/export do `ir-commentary-lora` (INFO capture už shipped #228) |

## Kde číst shipped baseline

- [domeny/commentary.md](../domeny/commentary.md)
- [COMMENTARY_ENGINE.md](../../../COMMENTARY_ENGINE.md)
- [commentary_product_suite.md](../../commentary_product_suite.md)
- [commentary_stateful_sequence_graph_spec.md](../../commentary_stateful_sequence_graph_spec.md)

## Hranice

- HUD copy zůstává v `overlay/i18n.py` (skill `overlay-hud-copy`).
- Scene switcher (`logic/`) se kvůli commentary nemění.
- Spec `live_data_channels_sampling_spec.md` je samostatné in-flight (#212), ne součást tohoto listu.
