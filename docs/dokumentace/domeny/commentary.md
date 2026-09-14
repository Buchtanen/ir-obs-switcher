# Commentary / TTS (`src/irswitch/commentary/`)

Director: accepted envelope → sequence graph → TTS. Peer consumer (N12), ne renderer HUD.

Polish vocative/hero rewrite is in `speech_hero.py` / `polish.py`. `commentary.polish_skeleton_fallback` (default true) speaks a grounded skeleton after `retry_exhausted` for OVERTAKE / POSITION_* / FINISH / SESSION_FLAG — not TRACK_EXCURSION. Scheduler `dynamic_ttl_s` (default 4) is for HUNTING/HUNTED/BATTLE/OVERTAKE/POSITION_*; `llm_timeout_s` default is 4.0.

## Boundaries

- `headlineToken` / overlay i18n sem nepatří.
- Scene switcher sem nepatří.
- Open work: [inflight/commentary-architecture.md](../inflight/commentary-architecture.md). I3 publisher is shipped (`ScenarioEngine` → TRACK_EXCURSION).

## Key files

`director.py`, `graph.py`, `graph_runtime.py`, `consumer.py`, `scheduler.py`, `tts.py`, `supertonic_backend.py`, `polish.py`, `composer.py`, `microplan.py`, `prepared_filler.py`, `llm_lane.py`, `style_cards.py`, `speech_hero.py`, `story_identity.py`, `replay_eval.py`, `http.py`, `validator.py`, `data/sequence_graph.json`.

## Tests

`tests/test_commentary_*.py`.

## Related

[COMMENTARY_ENGINE.md](../../../COMMENTARY_ENGINE.md), [commentary_product_suite.md](../../commentary_product_suite.md), [commentary_stateful_sequence_graph_spec.md](../../commentary_stateful_sequence_graph_spec.md).
