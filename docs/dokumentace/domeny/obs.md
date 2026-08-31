# OBS (`src/irswitch/obs/`)

**Účel:** tenký klient obs-websocket v5 (`obsws-python`). Connect, scény, stream, volume.

**Nepatří sem:** kdy přepnout scénu, debounce, „jaký mód je to“. To je `logic/` + `main_loop`.

## `ObsClient` (`client.py`)

- URL/heslo z `[obs] ws_url`, `password`
- `connect` s retry + exponential backoff; main loop při fail **pokračuje**
- Cache: current scene (~500 ms), profile (~2 s), stream info (dokud se nezmění výběr)
- `set_scene`, `get_scene_list`, `get_current_scene`
- Stream: start/stop, `is_streaming`, YouTube service selection helpers
- Volume lock pro commentary duck (`commentary/duck.py` volá client, policy duck je v commentary)
- Rate-limit ERROR logů když OBS pořád leží

`required_profile` v config: switcher smí pracovat jen na daném OBS profilu (kontrola v main loop / policy použití — client jen umí přečíst profil).

## YouTube vedle websocketu

Client drží odkaz na `OAuthManager` (`set_oauth_manager`). Title/description: YouTube Data API, ne OBS. Quota / missing key flagy, ať se neloguje dokola.

- `stream_status_refresh.py` — hrana OBS streaming on/off → refresh liveBroadcast
- `youtube_vod.py` — zápis kapitol do VOD description (`[stream_chapters] youtube_vod`)

Scene switcher **nepotřebuje** OAuth. Bez tokenu stream stejně startuje; dashboard nemá titulek.

## Config / docs

`[obs]` — [CONFIG.md](../../../CONFIG.md). Setup: [README.md](../../../README.md), [YOUTUBE_API_SETUP.md](../../../YOUTUBE_API_SETUP.md). Skill: `.cursor/skills/youtube-oauth/SKILL.md`.

## Testy

`tests/test_obs_client.py`, `tests/test_stream_status_refresh.py`, `tests/test_youtube_chapters.py`, `tests/test_stream_chapters.py`.

## In-flight

#179/#181 nemění OBS client jako jádro. Stream-start commentary (#181 N8) čte OBS streaming edge přes bridge, ne přes novou policy v `obs/`.
