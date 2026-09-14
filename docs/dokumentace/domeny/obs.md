# OBS (`src/irswitch/obs/`)

Tenký obs-websocket v5 client: scény, stream start/stop, volume (duck).

`get_stream_status` error/unknown and empty `datain` keep last known `output_active` (not a stop). Start/stop + diagnostic voice need 3 matching polls or ≥5 s; a 2 s flap does not reset the STREAM_START epoch. Duration drop or a confirmed stop does.

## Boundaries

Žádná policy „která scéna“. Žádný commentary text. YouTube VOD patch je side-effect po konci streamu, ne scene switch.

## Key files

`client.py`, `stream_status_refresh.py`, `youtube_vod.py`.

## Tests

`tests/test_obs_*.py`, `tests/test_youtube_vod.py` (podle prefixu).

## Related

[logic](logic.md) volá `set_scene`. [oauth-youtube](oauth-youtube.md) title.
