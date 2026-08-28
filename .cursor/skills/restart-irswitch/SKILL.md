---
name: restart-irswitch
description: Starts, stops, or restarts the local irswitch Windows service (irswitchd.exe), handles SSLKEYLOGFILE and port 17321, and verifies /health plus displayed version. Use when the user asks to start, stop, restart, or nastartuj/restartuj the app/service, or mentions dashboard version mismatch, port 17321 already in use, or SSLKEYLOGFILE / aiohttp PermissionError.
---

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

## Checklist

1. **SSLKEYLOGFILE**: if set to an unusable Volume GUID path, `import aiohttp` dies with `PermissionError`. Clear it in the shell (`Remove-Item Env:SSLKEYLOGFILE`) or rely on `start_app.ps1` which already drops a bad value.
2. **Single instance**: second process on `:17321` is rejected. If start fails, find the listener, then `POST /shutdown` (wait ~2s) and only then kill leftover `irswitchd` if still bound.
3. **Do not** start a second instance to “fix” a hung dashboard.
4. After spawn, wait until `GET /health` responds (a few seconds). `POST /restart` returns immediately; the successor needs handoff time.
5. Report: process alive, `health.status`, `checks.obs`, `checks.iracing`, **version**. iRacing disconnected is normal (`degraded`).
6. If version is wrong, read `runtime-version-identity.mdc` — do not bump `pyproject.toml` in a normal PR.
7. If running pytest that binds `17321` while the service is up, that failure is environment, not a product regression (`tests-policy.mdc`).

## Stop

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:17321/shutdown
```

Then wait; force-kill `irswitchd` only if the port is still held.

## Verify

- GR: `http://127.0.0.1:17321/gr-status`
- VR: `http://127.0.0.1:17321/vr-status`
- OAuth (optional): `GET /oauth/status` — see skill `youtube-oauth`
