# Web UI (`src/irswitch/web/`)

Statika servírovaná z `server/` + `overlay/http.py`.

| Cesta | Účel |
| --- | --- |
| `web/admin/` | `/admin` |
| `web/overlay/` | HUD V3/V4 |
| `web/commentary/` | TTS test |
| `web/themes/` | V3 raster (legacy) |
| `web/themes-v4/` | V4 + Pit Wall |

HUD JS cluster (`display-v4.js`, `overlay.js`, `index.html`) jen sekvenčně. Není TUI. Není VR widget.
