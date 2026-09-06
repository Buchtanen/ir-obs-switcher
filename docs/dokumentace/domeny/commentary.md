# Commentary / TTS (`src/irswitch/commentary/`)

Director: accepted envelope → sequence graph → TTS. Peer consumer (N12), ne renderer HUD.

## Boundaries

- `headlineToken` / overlay i18n sem nepatří.
- Scene switcher sem nepatří.
- Open work: [inflight/commentary-architecture.md](../inflight/commentary-architecture.md).

## Key files

`director.py`, `graph.py`, `graph_runtime.py`, `consumer.py`, `scheduler.py`, `tts.py`, `supertonic_backend.py`, `polish.py`, `composer.py`, `microplan.py`, `prepared_filler.py`, `llm_lane.py`, `style_cards.py`, `speech_hero.py`, `story_identity.py`, `replay_eval.py`, `http.py`, `validator.py`, `data/sequence_graph.json`.

## Tests

`tests/test_commentary_*.py`.

## Related

[COMMENTARY_ENGINE.md](../../../COMMENTARY_ENGINE.md), [commentary_product_suite.md](../../commentary_product_suite.md), [commentary_stateful_sequence_graph_spec.md](../../commentary_stateful_sequence_graph_spec.md).
