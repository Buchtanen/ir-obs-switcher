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

Canonical skill: `.cursor/skills/restart-irswitch/SKILL.md` (keep in sync).

# Restart irswitch (Windows)

Long-running service. Default: `http://127.0.0.1:17321`. Config: `config/config.ini`.

## When to use which path

| Intent | How |
|--------|-----|
| Already running, no code/install change | `POST /restart` (sets `IRSWITCH_RESTARTING=1`) |
| Dead / never started | `start_app.ps1` or `.venv/Scripts/irswitchd.exe --config config/config.ini` |
| Code just changed and you need a new process | stop if needed, then start as above |
| New EXE / `dist/` | rebuild; do not expect `POST /restart` to pick up a different binary |

Spawn **`irswitchd.exe`**, never pass the console_scripts shim (`Scripts/irswitchd` without `.exe`) to `python.exe`.

## Overlay cache bump (OBS CEF)

OBS Browser Source keeps `overlay.js` / `display-v4.js` / CSS until the query string changes. **Restart alone does not reload HUD JS.**

**Bump when** this restart follows overlay HUD work (`src/irswitch/web/overlay/**` HTML/JS/CSS dirty or edited this session), or the user says cache bump / overlay still looks old. Skip for backend-only restarts (no overlay files touched).

This token is **not** the package version. Do **not** bump `pyproject.toml`.

### How

1. Read current `OVERLAY_ASSET_VER` in `src/irswitch/web/overlay/js/overlay.js` (today like `1.2.16`).
2. Increment the last numeric segment (`1.2.16` → `1.2.17`). Keep the `x.y.z` shape.
3. Write the **same** string in all lockstep places:

| File | What |
|------|------|
| `src/irswitch/web/overlay/js/overlay.js` | `const OVERLAY_ASSET_VER = "…"` (dynamic `import(…?v=${OVERLAY_ASSET_VER})`) |
| `src/irswitch/web/overlay/index.html` | `?v=` on `overlay.css`, `display-v4.css`, `overlay.js` |
| `src/irswitch/web/overlay/js/demo-v4.js` | static `import` `?v=` on `display.js` and `display-v4.js` |

Do not leave mixed versions. Theme CSS in `index.html` has no `?v=` — if only a theme file changed, still bump the three `index.html` links so CEF refetches the document.

4. Then restart the service (below).
5. Tell the user: OBS Browser Source on the overlay URL → **Refresh cache** (or hide/show the source). Service restart + `?v=` is not enough if CEF still holds `index.html`.

## Checklist

1. **Cache bump** if overlay HUD assets changed this session (section above). Skip and say so when it is backend-only.
2. **SSLKEYLOGFILE**: if set to an unusable Volume GUID path, `import aiohttp` dies with `PermissionError`. Clear it in the shell (`Remove-Item Env:SSLKEYLOGFILE`) or rely on `start_app.ps1` which already drops a bad value.
3. **Single instance**: second process on `:17321` is rejected. If start fails, find the listener, then `POST /shutdown` (wait ~2s) and only then kill leftover `irswitchd` if still bound.
4. **Do not** start a second instance to “fix” a hung dashboard.
5. After spawn, wait until `GET /health` responds (a few seconds). `POST /restart` returns immediately; the successor needs handoff time.
6. Report: process alive, `health.status`, `checks.obs`, `checks.iracing`, **version**, and **overlay `?v=`** if bumped.
7. If app version is wrong, read `runtime-version-identity.mdc` — do not bump `pyproject.toml` in a normal PR.
8. If running pytest that binds `17321` while the service is up, that failure is environment, not a product regression (`tests-policy.mdc`).

## Stop

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:17321/shutdown
```

Then wait; force-kill `irswitchd` only if the port is still held.

## Verify

- GR: `http://127.0.0.1:17321/gr-status`
- VR: `http://127.0.0.1:17321/vr-status`
- Overlay (after bump): `http://127.0.0.1:17321/overlay/` — HTML/JS query must match the new token
- OAuth (optional): `GET /oauth/status` — see skill `youtube-oauth`
