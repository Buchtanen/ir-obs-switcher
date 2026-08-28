---
name: youtube-oauth
description: Diagnoses and operates optional YouTube OAuth used only for stream title/description in the GR dashboard. Use when the user mentions YouTube, OAuth, stream title, broadcast id, youtube oauth not configured, /oauth/initiate, invalid_grant, or fetch stream info.
---

# YouTube OAuth (optional)

OAuth is **not** required for iRacing → OBS scene switching. OBS websocket does **not** expose the YouTube stream title. Title/description come from YouTube Data API v3 only.

If OAuth is missing, the switcher must still run. Do not treat `oauth_not_configured` as a startup failure.

## What it is for

- Stream **title** / **description** on GR dashboard
- `liveBroadcasts` needs OAuth (API key gets 401 on that endpoint)
- Auto refresh of access token; revoked refresh token → `invalid_grant` → interactive reauth (`/oauth/initiate`, cooldown 300s)

## Credentials (never commit)

Prefer `config/config.ini` `[oauth]` (`client_id`, `client_secret`) or env `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`. Token file: `data/youtube_oauth_token.json` (gitignored).

User setup: `YOUTUBE_API_SETUP.md`.

## Endpoints

- `GET /oauth/status` — configured / pending / active / expired
- `GET /oauth/initiate` — starts consent (opens browser; redirect `http://localhost:17321/oauth/callback`)
- Dashboard: GR OAuth button; `POST /stream/reinit` when the user created a **new** YouTube/OBS broadcast

## Debug fetch stream info

1. Scene switching OK + OAuth warning → expected without credentials; ask if they care about title.
2. Credentials set but fetch fails → `/oauth/status`, token file present, `invalid_grant` in logs, then `/oauth/initiate`.
3. Do not scrape title from OBS as a substitute; that API is not there. Do not add an OBS plugin unless the user explicitly asks (previously declined).
