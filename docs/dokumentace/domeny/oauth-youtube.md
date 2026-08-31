# YouTube OAuth (`oauth.py`)

**Účel:** titulek/popis liveBroadcast a volitelně VOD kapitoly. **Nepřepíná scény, nespouští stream.**

Skill: `.cursor/skills/youtube-oauth/SKILL.md`. Setup: [YOUTUBE_API_SETUP.md](../../../YOUTUBE_API_SETUP.md).

## Tok

- Client id/secret z config nebo env
- Redirect `http://localhost:{http_port}/oauth/callback`
- Scope default `youtube` (write kvůli VOD chapters); staré readonly tokeny fungují na title do re-auth
- Token soubor mimo git; `invalid_grant` → clear + browser reauth (`oauth_reauth_watchdog` v `main.py`)
- Start bez tokenu: browser `/oauth/initiate`, timeout → služba běží bez API

API: `/oauth/initiate`, `/oauth/callback`, `/oauth/status`, `/oauth/revoke`.

OBS client volá YouTube až když je stream selected + authenticated. Quota exceeded → přestat spamovat.

## Nepatří sem

OBS websocket password, scene names, commentary TTS.

## Testy

`tests/test_oauth.py`.
