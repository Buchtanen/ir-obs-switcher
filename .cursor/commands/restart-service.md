# Restart Service

Start / stop / restart lokální irswitch a ověř `/health` + verzi.

## Pravidla
- Použij skill `restart-irswitch` (Windows, `irswitchd.exe`, port 17321, `SSLKEYLOGFILE`, overlay cache bump).
- Nesahaj na `pyproject.toml` verzi. Špatná verze v dashboardu → `runtime-version-identity.mdc`.
- Druhá instance na `:17321` se nespouští.

## Postup
1) Zjisti, jestli už něco poslouchá `http://127.0.0.1:17321`.
1b) Overlay HUD (`src/irswitch/web/overlay/**`) se měnil → bump `OVERLAY_ASSET_VER` / `?v=` lockstep (skill). Backend-only → přeskoč. Po bump: v OBS Browser Source **Refresh cache**.
2) Podle intentu:
   - běží a stačí respawn → `POST /restart`
   - neběží → `start_app.ps1` nebo `.venv/Scripts/irswitchd.exe --config config/config.ini`
   - stop → `POST /shutdown`, počkej, kill jen když port visí
3) Počkej na `GET /health`.
4) Vrať: health, obs, iracing, version, overlay `?v=` (bumped / skipped), URL GR/VR.

## Výstup
- **status**: running / restarted / stopped / failed
- **health**: ...
- **version**: ...
- **overlay_v**: bumped to … / skipped (backend-only)
- **notes**: SSLKEYLOGFILE / occupied port / iRacing disconnected (normal) / OBS Refresh cache
