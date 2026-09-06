# OBS (`src/irswitch/obs/`)

Tenký obs-websocket v5 client: scény, stream start/stop, volume (duck).

## Boundaries

Žádná policy „která scéna“. Žádný commentary text. YouTube VOD patch je side-effect po konci streamu, ne scene switch.

## Key files

`client.py`, `stream_status_refresh.py`, `youtube_vod.py`.

## Tests

`tests/test_obs_*.py`, `tests/test_youtube_vod.py` (podle prefixu).

## Related

[logic](logic.md) volá `set_scene`. [oauth-youtube](oauth-youtube.md) title.
