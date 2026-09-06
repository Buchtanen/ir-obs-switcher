# Status projektu

Živý snapshot. Detaily a lookup: [docs/dokumentace/](docs/dokumentace/README.md). Historie releasů: [CHANGELOG.md](CHANGELOG.md).

## Runtime (`master`, 1.3.0)

- iRacing → OBS scene switcher (`logic/` + `main_loop`)
- Overlay HUD V4 + Event Engine + Pit Wall themes
- Commentary TTS (graph + director + N12 peer consumers; prepared graph default active)
- Track Excursion current-signal subset (`events/scenarios/`)
- Operator diagnostic SAPI (`[diagnostics] voice`)
- Race observer (flags, aftermath, hunt, grid, stream start)
- Admin `/admin` Slice 1.2
- Operator UI: `/gr-status` + `/admin`. Overlay: `/overlay/`
- **Není:** TUI, `/vr-status` / RaceLab widget

## Otevřené

[docs/dokumentace/inflight/](docs/dokumentace/inflight/README.md) — commentary architecture, sampling spec #212, CI #162.

## Kontrakty

`CONFIG.md`, `API.md`, `RELEASE_POLICY.md`, `BUILD_AND_DEPLOY.md`. Cursor rules/skills **jsou v gitu**.
