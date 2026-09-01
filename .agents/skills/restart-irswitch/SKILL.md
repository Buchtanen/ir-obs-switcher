---
name: restart-irswitch
description: >-
  Starts, stops, or restarts the local irswitch Windows service (irswitchd.exe),
  handles SSLKEYLOGFILE and port 17321, verifies /health plus displayed version, and
  bumps overlay HUD cache (?v= / OVERLAY_ASSET_VER) so OBS CEF does not keep stale JS.
  Use when the user asks to start, stop, restart, or nastartuj/restartuj the app/service,
  mentions dashboard version mismatch, overlay still showing old widgets, OBS Browser
  Source cache, cache bump/bust, port 17321 already in use, or SSLKEYLOGFILE / aiohttp PermissionError.
---

Canonical copy: `.cursor/skills/restart-irswitch/SKILL.md`.

Read that file and follow it. Do not maintain a second full procedure here.
